import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, pass_context
from starlette.requests import Request

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED_LANGS = ("ru", "tg")
DEFAULT_LANG = "ru"
LANG_COOKIE = "lang"

_messages: dict[str, dict[str, str]] = {
    lang: json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    for lang in SUPPORTED_LANGS
}


def normalize_lang(value: str | None) -> str:
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def get_lang(request: Request) -> str:
    return normalize_lang(request.cookies.get(LANG_COOKIE))


def get_messages(lang: str) -> dict[str, str]:
    return _messages[normalize_lang(lang)]


def t(key: str, lang: str = DEFAULT_LANG, **params: Any) -> str:
    text = get_messages(lang).get(key, key)
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


@pass_context
def _jinja_t(context: Any, key: str, **params: Any) -> str:
    return t(key, context.get("lang", DEFAULT_LANG), **params)


def install_jinja(env: Environment) -> None:
    env.globals["t"] = _jinja_t
