from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.core.deps import get_current_user_optional
from app.core.i18n import get_lang, get_messages, normalize_lang
from app.models.user import User

router = APIRouter()

THEMES = ("light", "dark")
DEFAULT_THEME = "light"


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
        base_context(request),
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
    return templates.TemplateResponse(
        request,
        "ui.html",
        base_context(request, user=user),
    )
