import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.user import User
from app.schemas.auth import StatusResponse
from app.schemas.group import (
    GroupDetailResponse,
    GroupListItem,
    GroupParseResponse,
    GroupUpdateRequest,
)
from app.services import group_service
from app.services.excel.reader import MAX_FILE_SIZE_BYTES

router = APIRouter(prefix="/api", tags=["groups"])


async def _read_upload_limited(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_FILE_SIZE_BYTES + 1)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise AppError("file_too_large", status_code=413)
    return data


def _parse_columns_json(raw_columns: str) -> list[int]:
    try:
        parsed = json.loads(raw_columns)
    except json.JSONDecodeError as exc:
        raise AppError("invalid_columns", status_code=422) from exc

    if not isinstance(parsed, list):
        raise AppError("invalid_columns", status_code=422)

    result: list[int] = []
    for item in parsed:
        if not isinstance(item, int) or isinstance(item, bool):
            raise AppError("invalid_columns", status_code=422)
        result.append(item)
    return result


@router.post("/groups/parse", response_model=GroupParseResponse)
async def parse_group(
    _user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    header_row: Annotated[int | None, Form()] = None,
) -> dict[str, Any]:
    data = await _read_upload_limited(file)
    preview = await group_service.parse_group_excel(
        data=data,
        filename=file.filename or "",
        header_row=header_row,
    )
    return dict(preview)


@router.post("/groups", response_model=GroupDetailResponse)
async def create_group(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
    header_row: Annotated[int, Form()],
    columns: Annotated[str, Form()],
    number: Annotated[str, Form()],
    course: Annotated[int, Form(ge=1, le=6)],
) -> dict[str, Any]:
    trimmed_number = number.strip()
    if not (1 <= len(trimmed_number) <= 50):
        raise AppError("validation_error", status_code=422)

    data = await _read_upload_limited(file)
    column_indices = _parse_columns_json(columns)

    return await group_service.create_group_from_excel(
        session,
        owner_id=user.id,
        data=data,
        filename=file.filename or "",
        header_row=header_row,
        columns=column_indices,
        number=trimmed_number,
        course=course,
    )


@router.get("/groups", response_model=list[GroupListItem])
async def list_groups(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    course: Annotated[int | None, Query(ge=1, le=6)] = None,
) -> list[dict[str, Any]]:
    return await group_service.list_groups(
        session,
        owner_id=user.id,
        course=course,
    )


@router.get("/groups/{group_id}", response_model=GroupDetailResponse)
async def get_group(
    group_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await group_service.get_group_detail(
        session,
        group_id=group_id,
        owner_id=user.id,
    )


@router.patch("/groups/{group_id}", response_model=GroupDetailResponse)
async def update_group(
    group_id: int,
    payload: GroupUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await group_service.update_group(
        session,
        group_id=group_id,
        owner_id=user.id,
        number=payload.number,
        course=payload.course,
        columns_order=payload.columns_order,
    )


@router.delete("/groups/{group_id}", response_model=StatusResponse)
async def delete_group(
    group_id: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    await group_service.delete_group(
        session,
        group_id=group_id,
        owner_id=user.id,
    )
    return StatusResponse()
