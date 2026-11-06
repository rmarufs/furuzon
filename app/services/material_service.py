import html
import io
import re
import uuid
import xml.etree.ElementTree as ET
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
    group_ids: list[int] | None = None,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    unique_group_ids = list(dict.fromkeys(group_ids or []))
    clean_name, content_type = validate_material_file(data, filename)

    if unique_group_ids:
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

    files_by_course: dict[int, list[dict[str, Any]]] = {c: [] for c in range(1, 7)}
    for material in materials:
        if not group_ids_by_file.get(material.id):
            files_by_course.setdefault(material.course, []).append(
                serialized_by_id[material.id]
            )

    courses = [
        {
            "course": course,
            "groups": groups_by_course[course],
            "files": files_by_course[course],
        }
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


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    if ":" in tag:
        return tag.rsplit(":", 1)[1]
    return tag


def _attr_val(elem: ET.Element, local_name: str) -> str:
    for key, val in elem.attrib.items():
        if _local_tag(key) == local_name:
            return val
    return ""


def _has_flag(rpr: ET.Element | None, tag_name: str) -> bool:
    if rpr is None:
        return False
    for child in rpr:
        if _local_tag(child.tag) == tag_name:
            val = _attr_val(child, "val").lower()
            return val not in ("0", "false", "none")
    return False


def _render_run(run_elem: ET.Element) -> str:
    rpr = None
    parts: list[str] = []
    for child in run_elem:
        cname = _local_tag(child.tag)
        if cname == "rPr":
            rpr = child
        elif cname == "t" and child.text:
            parts.append(html.escape(child.text, quote=True))
        elif cname in ("br", "cr"):
            parts.append("<br>")
        elif cname == "tab":
            parts.append(" ")
    if run_elem.text:
        parts.insert(0, html.escape(run_elem.text, quote=True))
    inner = "".join(parts)
    if not inner:
        return ""
    if _has_flag(rpr, "u"):
        inner = f"<u>{inner}</u>"
    if _has_flag(rpr, "i"):
        inner = f"<em>{inner}</em>"
    if _has_flag(rpr, "b"):
        inner = f"<strong>{inner}</strong>"
    return inner


def _render_paragraph(p_elem: ET.Element) -> tuple[str, bool]:
    style_val = ""
    is_list_item = False
    chunks: list[str] = []
    if p_elem.text:
        chunks.append(html.escape(p_elem.text, quote=True))

    for child in p_elem:
        cname = _local_tag(child.tag)
        if cname == "pPr":
            for pchild in child:
                pname = _local_tag(pchild.tag)
                if pname == "pStyle":
                    style_val = _attr_val(pchild, "val").lower()
                elif pname == "numPr":
                    is_list_item = True
        elif cname == "r":
            chunks.append(_render_run(child))
        elif cname == "hyperlink":
            for hchild in child:
                if _local_tag(hchild.tag) == "r":
                    chunks.append(_render_run(hchild))
        elif cname in ("br", "cr"):
            chunks.append("<br>")

    content = "".join(chunks).strip()
    if not content:
        return "", False

    if is_list_item:
        return f"<li>{content}</li>", True

    if style_val.startswith("heading") or style_val in ("title", "subtitle"):
        level = "h2" if style_val in ("heading1", "title") else "h3"
        return f"<{level}>{content}</{level}>", False

    return f"<p>{content}</p>", False


def _render_table(tbl_elem: ET.Element) -> str:
    rows_html: list[str] = []
    for child in tbl_elem:
        if _local_tag(child.tag) != "tr":
            continue
        cells_html: list[str] = []
        for cell in child:
            if _local_tag(cell.tag) != "tc":
                continue
            cell_parts: list[str] = []
            for p in cell:
                if _local_tag(p.tag) == "p":
                    rendered, _ = _render_paragraph(p)
                    if rendered:
                        cell_parts.append(rendered)
            cells_html.append(f"<td>{''.join(cell_parts)}</td>")
        if cells_html:
            rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
    if not rows_html:
        return ""
    return f"<table><tbody>{''.join(rows_html)}</tbody></table>"


def render_docx_html(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            raw_xml = archive.read(DOCX_DOCUMENT_ENTRY).decode(
                "utf-8", errors="replace"
            )
    except (KeyError, zipfile.BadZipFile) as exc:
        raise AppError("invalid_material_type", status_code=415) from exc

    if "xmlns:w=" not in raw_xml:
        raw_xml = re.sub(
            r"<w:document\b",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
            raw_xml,
            count=1,
        )

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise AppError("invalid_material_type", status_code=415) from exc

    body = next(
        (child for child in root if _local_tag(child.tag) == "body"),
        root,
    )

    blocks: list[str] = []
    list_buffer: list[str] = []

    def _flush_list() -> None:
        if list_buffer:
            blocks.append(f"<ul>{''.join(list_buffer)}</ul>")
            list_buffer.clear()

    for elem in body:
        ename = _local_tag(elem.tag)
        if ename == "p":
            rendered, is_list = _render_paragraph(elem)
            if not rendered:
                continue
            if is_list:
                list_buffer.append(rendered)
            else:
                _flush_list()
                blocks.append(rendered)
        elif ename == "tbl":
            _flush_list()
            table_html = _render_table(elem)
            if table_html:
                blocks.append(table_html)

    _flush_list()
    return "".join(blocks)


async def get_material_file_bytes(
    session: AsyncSession,
    storage: Storage,
    *,
    material_id: int,
    owner_id: int,
) -> tuple[Material, bytes]:
    material = await get_owned_material_or_404(
        session,
        material_id=material_id,
        owner_id=owner_id,
    )
    try:
        file_bytes = await storage.read(material.storage_key)
    except FileNotFoundError as exc:
        raise AppError("material_not_found", status_code=404) from exc
    return material, file_bytes


async def get_material_preview(
    session: AsyncSession,
    storage: Storage,
    *,
    material_id: int,
    owner_id: int,
) -> dict[str, Any]:
    material, file_bytes = await get_material_file_bytes(
        session,
        storage,
        material_id=material_id,
        owner_id=owner_id,
    )
    ext = Path(material.original_name).suffix.lower()
    download_url = f"/api/materials/{material.id}/file?download=1"

    if ext == ".docx":
        html_content = render_docx_html(file_bytes)
        return {
            "id": material.id,
            "original_name": material.original_name,
            "content_type": material.content_type,
            "mode": "docx",
            "html": html_content,
            "file_url": None,
            "download_url": download_url,
        }

    if ext == ".pdf":
        return {
            "id": material.id,
            "original_name": material.original_name,
            "content_type": material.content_type,
            "mode": "pdf",
            "html": None,
            "file_url": f"/api/materials/{material.id}/file",
            "download_url": download_url,
        }

    return {
        "id": material.id,
        "original_name": material.original_name,
        "content_type": material.content_type,
        "mode": "unsupported",
        "html": None,
        "file_url": None,
        "download_url": download_url,
    }
