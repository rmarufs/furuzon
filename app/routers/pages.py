from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import get_current_user_optional
from app.core.exceptions import AppError
from app.core.i18n import get_lang, get_messages, normalize_lang
from app.models.user import User
from app.services import activity_service
from app.services.group_service import get_owned_group_or_404

router = APIRouter()

THEMES = ("light", "dark")
DEFAULT_THEME = "light"


def display_name(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    full = f"{first} {last}".strip()
    return full if full else user.email


def user_initials(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    letters = "".join(part[0].upper() for part in (first, last) if part)
    if letters:
        return letters
    email = (user.email or "").strip()
    return email[0].upper() if email else ""


def base_context(
    request: Request,
    user: User | None = None,
    active_nav: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if user is not None:
        lang = normalize_lang(user.language)
        theme = user.theme if user.theme in THEMES else DEFAULT_THEME
    else:
        lang = get_lang(request)
        cookie_theme = request.cookies.get("theme")
        theme = cookie_theme if cookie_theme in THEMES else DEFAULT_THEME

    context: dict[str, Any] = {
        "user": user,
        "display_name": display_name(user) if user is not None else "",
        "user_initials": user_initials(user) if user is not None else "",
        "lang": lang,
        "messages": get_messages(lang),
        "theme": theme,
        "active_nav": active_nav,
    }
    context.update(extra)
    return context


@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "home/index.html",
        base_context(request, user=user, active_nav="home"),
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        base_context(request),
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "auth/register.html",
        base_context(request),
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "auth/forgot_password.html",
        base_context(request, smtp_configured=settings.is_smtp_configured),
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    token: str = "",
) -> Response:
    if user is not None:
        return RedirectResponse(url="/", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        base_context(request, reset_token=token),
    )


@router.get("/groups", response_class=HTMLResponse)
async def groups_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "groups/index.html",
        base_context(request, user=user, active_nav="groups"),
    )


@router.get("/groups/new", response_class=HTMLResponse)
async def group_upload_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "groups/upload.html",
        base_context(request, user=user, active_nav="groups"),
    )


@router.get("/groups/{group_id}", response_class=HTMLResponse)
async def group_detail_page(
    group_id: int,
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    try:
        group = await get_owned_group_or_404(
            session,
            group_id=group_id,
            owner_id=user.id,
        )
    except AppError:
        return templates.TemplateResponse(
            request,
            "errors/404.html",
            base_context(request, user=user, active_nav="groups"),
            status_code=404,
        )
    await activity_service.record_activity(
        session,
        owner_id=user.id,
        action_type="group_viewed",
        object_type="group",
        object_id=group.id,
        object_title=group.number,
    )
    return templates.TemplateResponse(
        request,
        "groups/detail.html",
        base_context(
            request,
            user=user,
            active_nav="groups",
            group=group,
        ),
    )


@router.get("/materials", response_class=HTMLResponse)
async def materials_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "materials/index.html",
        base_context(
            request,
            user=user,
            active_nav="materials",
        ),
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> Response:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "auth/settings.html",
        base_context(request, user=user),
    )


@router.get("/_ui", response_class=HTMLResponse)
async def ui_showcase(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> HTMLResponse:
    templates = request.app.state.templates
    app_settings = getattr(request.app.state, "settings", settings)
    if app_settings.ENV == "prod" or settings.ENV == "prod":
        return templates.TemplateResponse(
            request,
            "errors/404.html",
            base_context(request, user=user),
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "ui.html",
        base_context(request, user=user),
    )
