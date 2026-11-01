from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mailer
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.i18n import t
from app.core.security import (
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_dummy_password,
    verify_password,
)
from app.models.user import PasswordResetToken, User

SUPPORTED_LANGS = ("ru", "tg")
SUPPORTED_THEMES = ("light", "dark")
RESET_TOKEN_TTL = timedelta(hours=1)


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    language: str | None = None,
    theme: str | None = None,
) -> User:
    normalized_email = email.strip().lower()
    existing = await session.scalar(
        select(User).where(User.email == normalized_email)
    )
    if existing is not None:
        raise AppError("email_taken", status_code=409)

    resolved_lang = language if language in SUPPORTED_LANGS else "ru"
    resolved_theme = theme if theme in SUPPORTED_THEMES else "light"

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        language=resolved_lang,
        theme=resolved_theme,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    normalized_email = email.strip().lower()
    user = await session.scalar(
        select(User).where(User.email == normalized_email)
    )
    if user is None:
        verify_dummy_password(password)
        raise AppError("invalid_credentials", status_code=401)

    if not verify_password(password, user.password_hash):
        raise AppError("invalid_credentials", status_code=401)

    return user


async def request_password_reset(
    session: AsyncSession,
    *,
    email: str,
) -> None:
    normalized_email = email.strip().lower()
    user = await session.scalar(
        select(User).where(User.email == normalized_email)
    )
    if user is None:
        return

    now = datetime.now(UTC)
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    raw_token = generate_reset_token()
    token_record = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(raw_token),
        expires_at=now + RESET_TOKEN_TTL,
    )
    session.add(token_record)
    await session.flush()

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    reset_link = f"{base_url}/reset-password?token={raw_token}"
    subject = t("mail.reset.subject", user.language)
    body = t("mail.reset.body", user.language, link=reset_link)
    await mailer.send_email(user.email, subject, body)


async def reset_password(
    session: AsyncSession,
    *,
    token: str,
    new_password: str,
) -> None:
    token_hash = hash_reset_token(token)
    record = await session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
    )
    now = datetime.now(UTC)
    if (
        record is None
        or record.used_at is not None
        or record.expires_at <= now
    ):
        raise AppError("invalid_or_expired_token", status_code=400)

    user = await session.get(User, record.user_id)
    if user is None:
        raise AppError("invalid_or_expired_token", status_code=400)

    user.password_hash = hash_password(new_password)
    record.used_at = now
    await session.flush()


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AppError("wrong_current_password", status_code=400)

    user.password_hash = hash_password(new_password)
    await session.flush()


async def update_profile(
    session: AsyncSession,
    *,
    user: User,
    first_name: str,
    last_name: str,
) -> User:
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    await session.flush()
    return user


async def update_preferences(
    session: AsyncSession,
    *,
    user: User,
    language: str | None = None,
    theme: str | None = None,
) -> User:
    if language is not None:
        user.language = language
    if theme is not None:
        user.theme = theme
    await session.flush()
    return user
