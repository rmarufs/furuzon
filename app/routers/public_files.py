from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.i18n import t
from app.routers.pages import base_context
from app.services import material_service
from app.storage import Storage, get_storage

router = APIRouter(tags=["public_files"])


def build_attachment_disposition(filename: str) -> str:
    ext = Path(filename).suffix or ""
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fallback or ascii_fallback == ext:
        ascii_fallback = f"file{ext}"
    ascii_fallback = ascii_fallback.replace('"', "").replace("\\", "_")
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _render_file_not_found(request: Request) -> Response:
    templates = request.app.state.templates
    context = base_context(
        request,
        title_ru=t("public_file.not_found.title", "ru"),
        text_ru=t("public_file.not_found.text", "ru"),
        title_tg=t("public_file.not_found.title", "tg"),
        text_tg=t("public_file.not_found.text", "tg"),
    )
    return templates.TemplateResponse(
        request,
        "errors/file_not_found.html",
        context,
        status_code=404,
    )


@router.get("/f/{token}")
async def download_public_file(
    token: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> Response:
    material = await material_service.get_material_by_token(
        session,
        token=token,
    )
    if material is None:
        return _render_file_not_found(request)

    try:
        file_bytes = await storage.read(material.storage_key)
    except FileNotFoundError:
        return _render_file_not_found(request)

    return Response(
        content=file_bytes,
        media_type=material.content_type,
        headers={
            "Content-Disposition": build_attachment_disposition(
                material.original_name
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
