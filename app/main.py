from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import Settings, settings
from app.core.database import get_session
from app.core.exceptions import error_response, register_exception_handlers
from app.core.i18n import install_jinja
from app.routers import activity, auth, groups, materials, pages, public_files

BASE_DIR = Path(__file__).resolve().parent

CSRF_CHECKED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _normalize_host_port(host_port: str, scheme: str = "") -> str:
    val = host_port.strip().lower()
    if scheme == "http" and val.endswith(":80"):
        return val[:-3]
    if scheme == "https" and val.endswith(":443"):
        return val[:-4]
    return val


def _is_same_origin(origin: str, host: str) -> bool:
    clean_host = host.strip().lower()
    if not clean_host:
        return False
    parsed = urlsplit(origin.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    origin_netloc = parsed.netloc.strip().lower()
    if origin_netloc == clean_host:
        return True
    return _normalize_host_port(origin_netloc, parsed.scheme) == _normalize_host_port(
        clean_host, parsed.scheme
    )


def create_app(app_settings: Settings = settings) -> FastAPI:
    is_prod = app_settings.ENV == "prod"
    application = FastAPI(
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    application.state.settings = app_settings
    register_exception_handlers(application)
    application.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.SECRET_KEY,
        same_site="lax",
        https_only=app_settings.COOKIE_SECURE,
        max_age=app_settings.SESSION_MAX_AGE_DAYS * 86400,
    )

    @application.middleware("http")
    async def security_and_csrf_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in CSRF_CHECKED_METHODS and (
            request.url.path == "/api" or request.url.path.startswith("/api/")
        ):
            origin = request.headers.get("origin")
            if origin is not None and not _is_same_origin(
                origin, request.headers.get("host", "")
            ):
                csrf_resp: Response = error_response("csrf_failed", status_code=403)
                for header_name, header_value in SECURITY_HEADERS.items():
                    csrf_resp.headers[header_name] = header_value
                return csrf_resp

        response = await call_next(request)
        for header_name, header_value in SECURITY_HEADERS.items():
            response.headers[header_name] = header_value
        return response

    application.mount(
        "/static",
        StaticFiles(directory=str(BASE_DIR / "static")),
        name="static",
    )
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    install_jinja(templates.env)
    application.state.templates = templates

    application.include_router(auth.router)
    application.include_router(groups.router)
    application.include_router(materials.router)
    application.include_router(activity.router)
    application.include_router(public_files.router)
    application.include_router(pages.router)

    @application.get("/health")
    async def health(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return application


app = create_app()
