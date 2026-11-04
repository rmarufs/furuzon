import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.group import Group
from app.models.material import FileGroup, Material
from app.services import activity_service, qr_service
from app.storage.base import Storage

MAX_MATERIAL_SIZE_BYTES = 10 * 1024 * 1024
MAX_DOCX_UNPACKED_BYTES = 50 * 1024 * 1024

PDF_SIGNATURE = b"%PDF-"
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
ZIP_SIGNATURE = b"PK\x03\x04"
DOCX_DOCUMENT_ENTRY = "word/document.xml"

CONTENT_TYPES_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document"
    ),
}


def validate_material_file(data: bytes, filename: str) -> tuple[str, str]:
    clean_name = Path(filename or "").name.strip()
    ext = Path(clean_name).suffix.lower()
    if ext not in CONTENT_TYPES_BY_EXT or not clean_name:
        raise AppError("invalid_material_type", status_code=415)

    if len(data) > MAX_MATERIAL_SIZE_BYTES:
        raise AppError("file_too_large", status_code=413)

    if len(data) == 0:
        raise AppError("invalid_material_type", status_code=415)

    if ext == ".pdf":
        if not data.startswith(PDF_SIGNATURE):
            raise AppError("invalid_material_type", status_code=415)
    elif ext == ".doc":
        if not data.startswith(OLE_SIGNATURE):
            raise AppError("invalid_material_type", status_code=415)
    elif ext == ".docx":
        if not data.startswith(ZIP_SIGNATURE):
            raise AppError("invalid_material_type", status_code=415)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if DOCX_DOCUMENT_ENTRY not in names:
                    raise AppError("invalid_material_type", status_code=415)
                total_unpacked = sum(
                    info.file_size for info in archive.infolist()
                )
                if total_unpacked > MAX_DOCX_UNPACKED_BYTES:
                    raise AppError("file_too_large", status_code=413)
        except zipfile.BadZipFile as exc:
            raise AppError("invalid_material_type", status_code=415) from exc

    return clean_name[:255], CONTENT_TYPES_BY_EXT[ext]


def _generate_storage_key(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


async def _serialize_material(
    session: AsyncSession,
    material: Material,
) -> dict[str, Any]:
    group_ids_stmt = (
        select(FileGroup.group_id)
        .where(FileGroup.file_id == material.id)
        .order_by(FileGroup.group_id.asc())
    )
    group_ids = list((await session.scalars(group_ids_stmt)).all())
    return {
        "id": material.id,
        "course": material.course,
        "original_name": material.original_name,
        "size_bytes": material.size_bytes,
        "content_type": material.content_type,
        "public_token": material.public_token,
        "public_url": qr_service.build_public_url(material.public_token),
        "group_ids": group_ids,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }


async def get_owned_material_or_404(
    session: AsyncSession,
    *,
    material_id: int,
    owner_id: int,
) -> Material:
    material = await session.scalar(
        select(Material).where(
            Material.id == material_id,
            Material.owner_id == owner_id,
        )
    )
    if material is None:
        raise AppError("material_not_found", status_code=404)
    return material


async def get_material_by_token(
    session: AsyncSession,
    *,
    token: str,
) -> Material | None:
    if not token:
        return None
    return await session.scalar(
        select(Material).where(Material.public_token == token)
    )


async def upload_material(
    session: AsyncSession,
    storage: Storage,
    *,
    owner_id: int,
    course: int,
    group_ids: list[int],
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    unique_group_ids = list(dict.fromkeys(group_ids))
    if not unique_group_ids:
        raise AppError("validation_error", status_code=422)

    clean_name, content_type = validate_material_file(data, filename)

    groups_stmt = select(Group).where(
        Group.id.in_(unique_group_ids),
        Group.owner_id == owner_id,
    )
    groups = list((await session.scalars(groups_stmt)).all())
    if len(groups) != len(unique_group_ids):
        raise AppError("group_not_found", status_code=404)

    for group in groups:
        if group.course != course:
            raise AppError("validation_error", status_code=422)

    storage_key = _generate_storage_key(clean_name)
    public_token = qr_service.generate_public_token()

    await storage.save(storage_key, data, content_type)

    try:
        material = Material(
            owner_id=owner_id,
            course=course,
            original_name=clean_name,
            storage_key=storage_key,
            size_bytes=len(data),
            content_type=content_type,
            public_token=public_token,
        )
        session.add(material)
        await session.flush()

        for gid in unique_group_ids:
            session.add(FileGroup(file_id=material.id, group_id=gid))
        await session.flush()

        await activity_service.record_activity(
            session,
            owner_id=owner_id,
            action_type="file_uploaded",
            object_type="file",
            object_id=material.id,
            object_title=material.original_name,
        )
        await session.refresh(material)
    except Exception:
        await storage.delete(storage_key)
        raise

    return await _serialize_material(session, material)


async def get_materials_tree(
    session: AsyncSession,
    *,
    owner_id: int,
) -> dict[str, Any]:
    groups_stmt = (
        select(Group)
        .where(Group.owner_id == owner_id)
        .order_by(Group.course.asc(), Group.number.asc(), Group.id.asc())
    )
    groups = list((await session.scalars(groups_stmt)).all())

    files_stmt = (
        select(Material)
        .where(Material.owner_id == owner_id)
        .order_by(Material.created_at.desc(), Material.id.desc())
    )
    materials = list((await session.scalars(files_stmt)).all())
    materials_by_id = {m.id: m for m in materials}

    links: list[FileGroup] = []
    if materials_by_id:
        links_stmt = (
            select(FileGroup)
            .where(FileGroup.file_id.in_(materials_by_id.keys()))
            .order_by(FileGroup.group_id.asc(), FileGroup.file_id.asc())
        )
        links = list((await session.scalars(links_stmt)).all())

    group_ids_by_file: dict[int, list[int]] = {m_id: [] for m_id in materials_by_id}
    files_by_group: dict[int, list[Material]] = {g.id: [] for g in groups}

    for link in links:
        if link.file_id in group_ids_by_file:
            group_ids_by_file[link.file_id].append(link.group_id)

    for material in materials:
        for gid in group_ids_by_file.get(material.id, []):
            if gid in files_by_group:
                files_by_group[gid].append(material)

    serialized_by_id: dict[int, dict[str, Any]] = {}
    for m_id, material in materials_by_id.items():
        serialized_by_id[m_id] = {
            "id": material.id,
            "course": material.course,
            "original_name": material.original_name,
            "size_bytes": material.size_bytes,
            "content_type": material.content_type,
            "public_token": material.public_token,
            "public_url": qr_service.build_public_url(material.public_token),
            "group_ids": group_ids_by_file.get(m_id, []),
            "created_at": material.created_at,
            "updated_at": material.updated_at,
        }

    groups_by_course: dict[int, list[dict[str, Any]]] = {c: [] for c in range(1, 7)}
    for group in groups:
        group_files = [
            serialized_by_id[m.id] for m in files_by_group.get(group.id, [])
        ]
        groups_by_course.setdefault(group.course, []).append(
            {
                "id": group.id,
                "number": group.number,
                "files": group_files,
            }
        )

    courses = [
        {"course": course, "groups": groups_by_course[course]}
        for course in range(1, 7)
    ]
    return {"courses": courses}


async def replace_material_file(
    session: AsyncSession,
    storage: Storage,
    *,
    material_id: int,
    owner_id: int,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    material = await get_owned_material_or_404(
        session,
        material_id=material_id,
        owner_id=owner_id,
    )
    clean_name, content_type = validate_material_file(data, filename)

    old_storage_key = material.storage_key
    new_storage_key = _generate_storage_key(clean_name)
    new_public_token = qr_service.generate_public_token()

    await storage.save(new_storage_key, data, content_type)
    try:
        material.original_name = clean_name
        material.storage_key = new_storage_key
        material.size_bytes = len(data)
        material.content_type = content_type
        material.public_token = new_public_token
        material.updated_at = datetime.now(UTC)
        await session.flush()

        await activity_service.record_activity(
            session,
            owner_id=owner_id,
            action_type="file_uploaded",
            object_type="file",
            object_id=material.id,
            object_title=material.original_name,
        )
        await session.refresh(material)
    except Exception:
        await storage.delete(new_storage_key)
        raise

    await storage.delete(old_storage_key)
    return await _serialize_material(session, material)


async def delete_material(
    session: AsyncSession,
    storage: Storage,
    *,
    material_id: int,
    owner_id: int,
) -> None:
    material = await get_owned_material_or_404(
        session,
        material_id=material_id,
        owner_id=owner_id,
    )
    storage_key = material.storage_key
    title = material.original_name

    await session.delete(material)
    await session.flush()

    await activity_service.record_activity(
        session,
        owner_id=owner_id,
        action_type="file_deleted",
        object_type="file",
        object_id=None,
        object_title=title,
    )
    await storage.delete(storage_key)


async def remove_material_from_group(
    session: AsyncSession,
    storage: Storage,
    *,
    material_id: int,
    group_id: int,
    owner_id: int,
) -> None:
    material = await get_owned_material_or_404(
        session,
        material_id=material_id,
        owner_id=owner_id,
    )
    group = await session.scalar(
        select(Group).where(
            Group.id == group_id,
            Group.owner_id == owner_id,
        )
    )
    if group is None:
        raise AppError("group_not_found", status_code=404)

    link = await session.scalar(
        select(FileGroup).where(
            FileGroup.file_id == material.id,
            FileGroup.group_id == group.id,
        )
    )
    if link is None:
        raise AppError("material_not_found", status_code=404)

    await session.execute(
        delete(FileGroup).where(
            FileGroup.file_id == material.id,
            FileGroup.group_id == group.id,
        )
    )
    await session.flush()

    remaining_count = await session.scalar(
        select(func.count())
        .select_from(FileGroup)
        .where(FileGroup.file_id == material.id)
    )
    if not remaining_count:
        storage_key = material.storage_key
        title = material.original_name
        await session.delete(material)
        await session.flush()
        await activity_service.record_activity(
            session,
            owner_id=owner_id,
            action_type="file_deleted",
            object_type="file",
            object_id=None,
            object_title=title,
        )
        await storage.delete(storage_key)


async def cleanup_orphan_files_for_ids(
    session: AsyncSession,
    storage: Storage,
    *,
    owner_id: int,
    candidate_file_ids: list[int],
) -> None:
    if not candidate_file_ids:
        return

    materials = list(
        (
            await session.scalars(
                select(Material).where(
                    Material.id.in_(candidate_file_ids),
                    Material.owner_id == owner_id,
                )
            )
        ).all()
    )
    for material in materials:
        remaining = await session.scalar(
            select(func.count())
            .select_from(FileGroup)
            .where(FileGroup.file_id == material.id)
        )
        if not remaining:
            key = material.storage_key
            await session.delete(material)
            await session.flush()
            await storage.delete(key)
