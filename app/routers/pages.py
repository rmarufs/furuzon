from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.i18n import get_lang, get_messages

router = APIRouter()

THEMES = ("light", "dark")
DEFAULT_THEME = "light"


def base_context(request: Request, active_nav: str | None = None) -> dict[str, Any]:
    lang = get_lang(request)
    theme = request.cookies.get("theme")
    return {
        "lang": lang,
        "messages": get_messages(lang),
        "theme": theme if theme in THEMES else DEFAULT_THEME,
        "active_nav": active_nav,
    }


@router.get("/_ui", response_class=HTMLResponse)
async def ui_showcase(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "ui.html", base_context(request))
