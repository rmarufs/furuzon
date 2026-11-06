import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.user import User
from app.routers.public_files import build_attachment_disposition
from app.schemas.auth import StatusResponse
from app.schemas.material import (
    MaterialItem,
    MaterialPreviewResponse,
    MaterialTreeResponse,
)
from app.services import material_service, qr_service
from app.services.material_service import MAX_MATERIAL_SIZE_BYTES
from app.storage import Storage, get_storage

router = APIRouter(prefix="/api", tags=["materials"])


async def _read_material_upload(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_MATERIAL_SIZE_BYTES + 1)
    if len(data) > MAX_MATERIAL_SIZE_BYTES:
        raise AppError("file_too_large", status_code=413)
    return data


def _parse_group_ids(raw_values: list[str] | None) -> list[int]:
    if not raw_values:
        return []

    result: list[int] = []
    for raw in raw_values:
        text = raw.strip()
        if not text:
            continue
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AppError("validation_error", status_code=422) from exc
            if not isinstance(parsed, list):
                raise AppError("validation_error", status_code=422)
            for item in parsed:
                if isinstance(item, bool) or not isinstance(item, int):
                    raise AppError("validation_error", status_code=422)
                result.append(item)
        else:
            for part in text.split(","):
                piece = part.strip()
                if not piece:
                    continue
                try:
                    val = int(piece)
                except ValueError as exc:
                    raise AppError("validation_error", status_code=422) from exc
                result.append(val)

    if any(gid <= 0 for gid in result):
        raise AppError("validation_error", status_code=422)
    return result


@router.get("/materials/tree", response_model=MaterialTreeResponse)
async def get_materials_tree(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await material_service.get_materials_tree(
        session,
        owner_id=user.id,
    )


@router.post("/materials", response_model=MaterialItem)
async def upload_material(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    file: Annotated[UploadFile, File()],
    course: Annotated[int, Form(ge=1, le=6)],
    group_ids: Annotated[list[str] | None, Form()] = None,
) -> dict[str, Any]:
    parsed_group_ids = _parse_group_ids(group_ids)
    data = await _read_material_upload(file)
    return await material_service.upload_material(
        session,
        storage,
        owner_id=user.id,
        course=course,
        group_ids=parsed_group_ids,
        filename=file.filename or "",
        data=data,
    )


@router.put("/materials/{material_id}/file", response_model=MaterialItem)
async def replace_material_file(
    material_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    data = await _read_material_upload(file)
    return await material_service.replace_material_file(
        session,
        storage,
        material_id=material_id,
        owner_id=user.id,
        filename=file.filename or "",
        data=data,
    )


@router.delete("/materials/{material_id}", response_model=StatusResponse)
async def delete_material(
    material_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> StatusResponse:
    await material_service.delete_material(
        session,
        storage,
        material_id=material_id,
        owner_id=user.id,
    )
    return StatusResponse()


@router.delete(
    "/materials/{material_id}/groups/{group_id}",
    response_model=StatusResponse,
)
async def remove_material_from_group(
    material_id: int,
    group_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> StatusResponse:
    await material_service.remove_material_from_group(
        session,
        storage,
        material_id=material_id,
        group_id=group_id,
        owner_id=user.id,
    )
    return StatusResponse()


@router.get("/materials/{material_id}/qr.svg")
async def get_material_qr_svg(
    material_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    material = await material_service.get_owned_material_or_404(
        session,
        material_id=material_id,
        owner_id=user.id,
    )
    url = qr_service.build_public_url(material.public_token)
    svg_bytes = qr_service.generate_qr_svg(url)
    return Response(
        content=svg_bytes,
        media_type="image/svg+xml",
    )


@router.get(
    "/materials/{material_id}/preview",
    response_model=MaterialPreviewResponse,
)
async def get_material_preview(
    material_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> dict[str, Any]:
    return await material_service.get_material_preview(
        session,
        storage,
        material_id=material_id,
        owner_id=user.id,
    )


@router.get("/materials/{material_id}/file")
async def get_material_file(
    material_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    download: bool = False,
) -> Response:
    material, file_bytes = await material_service.get_material_file_bytes(
        session,
        storage,
        material_id=material_id,
        owner_id=user.id,
    )
    disposition = build_attachment_disposition(material.original_name)
    if not download and material.content_type == "application/pdf":
        disposition = disposition.replace("attachment;", "inline;", 1)
    return Response(
        content=file_bytes,
        media_type=material.content_type,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )
