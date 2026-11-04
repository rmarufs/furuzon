import io
import secrets

import segno

from app.core.config import settings


def generate_public_token() -> str:
    return secrets.token_urlsafe(24)


def build_public_url(token: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/f/{token}"


def generate_qr_svg(url: str) -> bytes:
    qr = segno.make(url, error="m")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        scale=6,
        border=2,
        dark="#000000",
        light="#ffffff",
    )
    return buf.getvalue()
