import math
import threading
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import get_current_user
from app.core.exceptions import error_response
from app.core.i18n import get_lang, t
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PreferencesUpdateRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    StatusResponse,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/api", tags=["auth"])

LOGIN_PAIR_LIMIT = 10
LOGIN_IP_LIMIT = 30
LOGIN_WINDOW_SECONDS = 15 * 60

REGISTER_IP_LIMIT = 5
REGISTER_WINDOW_SECONDS = 60 * 60

PASSWORD_RESET_IP_LIMIT = 5
PASSWORD_RESET_WINDOW_SECONDS = 15 * 60


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, list[float]]] = {}
        self._last_cleanup = 0.0

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 60.0 and len(self._buckets) < 1000:
            return
        self._last_cleanup = now
        expired_keys: list[str] = []
        for key, (window, timestamps) in self._buckets.items():
            cutoff = now - window
            kept = [ts for ts in timestamps if ts > cutoff]
            if kept:
                self._buckets[key] = (window, kept)
            else:
                expired_keys.append(key)
        for key in expired_keys:
            del self._buckets[key]

    def check_and_record(
        self,
        rules: list[tuple[str, int, int]],
    ) -> int | None:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            max_retry_after = 0
            pruned_by_key: dict[str, tuple[int, list[float]]] = {}
            for key, limit, window in rules:
                cutoff = now - window
                existing = self._buckets.get(key)
                timestamps = (
                    [ts for ts in existing[1] if ts > cutoff]
                    if existing is not None
                    else []
                )
                if timestamps:
                    self._buckets[key] = (window, timestamps)
                else:
                    self._buckets.pop(key, None)
                pruned_by_key[key] = (window, timestamps)
                if len(timestamps) >= limit:
                    retry = max(1, math.ceil((timestamps[0] + window) - now))
                    if retry > max_retry_after:
                        max_retry_after = retry

            if max_retry_after > 0:
                return max_retry_after

            for key, _limit, window in rules:
                _, timestamps = pruned_by_key[key]
                timestamps.append(now)
                self._buckets[key] = (window, timestamps)
            return None

    def reset_key(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._last_cleanup = 0.0


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    app_settings = getattr(request.app.state, "settings", settings)
    if app_settings.ENV == "prod" or settings.ENV == "prod":
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if first_ip:
                return first_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limit_response(request: Request, retry_after: int) -> JSONResponse:
    lang = get_lang(request)
    response = error_response(
        "too_many_requests",
        status_code=429,
        details={
            "message": t("errors.too_many_requests", lang),
            "retry_after": retry_after,
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    return response


@router.post("/auth/register", response_model=UserResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | JSONResponse:
    ip = get_client_ip(request)
    retry_after = rate_limiter.check_and_record(
        [(f"register:ip:{ip}", REGISTER_IP_LIMIT, REGISTER_WINDOW_SECONDS)]
    )
    if retry_after is not None:
        return _rate_limit_response(request, retry_after)

    user = await auth_service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        language=request.cookies.get("lang"),
        theme=request.cookies.get("theme"),
    )
    request.session.clear()
    request.session["user_id"] = user.id
    return user


@router.post("/auth/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | JSONResponse:
    ip = get_client_ip(request)
    normalized_email = payload.email.strip().lower()
    pair_key = f"login:pair:{ip}:{normalized_email}"
    ip_key = f"login:ip:{ip}"
    retry_after = rate_limiter.check_and_record(
        [
            (pair_key, LOGIN_PAIR_LIMIT, LOGIN_WINDOW_SECONDS),
            (ip_key, LOGIN_IP_LIMIT, LOGIN_WINDOW_SECONDS),
        ]
    )
    if retry_after is not None:
        return _rate_limit_response(request, retry_after)

    user = await auth_service.authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )
    rate_limiter.reset_key(pair_key)
    request.session.clear()
    request.session["user_id"] = user.id
    return user


@router.post("/auth/logout", response_model=StatusResponse)
async def logout(
    request: Request,
    _user: Annotated[User, Depends(get_current_user)],
) -> StatusResponse:
    request.session.clear()
    return StatusResponse()


@router.post("/auth/forgot-password", response_model=StatusResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse | JSONResponse:
    ip = get_client_ip(request)
    retry_after = rate_limiter.check_and_record(
        [(f"forgot:ip:{ip}", PASSWORD_RESET_IP_LIMIT, PASSWORD_RESET_WINDOW_SECONDS)]
    )
    if retry_after is not None:
        return _rate_limit_response(request, retry_after)

    await auth_service.request_password_reset(session, email=payload.email)
    return StatusResponse()


@router.post("/auth/reset-password", response_model=StatusResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse | JSONResponse:
    ip = get_client_ip(request)
    retry_after = rate_limiter.check_and_record(
        [(f"reset:ip:{ip}", PASSWORD_RESET_IP_LIMIT, PASSWORD_RESET_WINDOW_SECONDS)]
    )
    if retry_after is not None:
        return _rate_limit_response(request, retry_after)

    await auth_service.reset_password(
        session,
        token=payload.token,
        new_password=payload.new_password,
    )
    return StatusResponse()


@router.post("/auth/change-password", response_model=StatusResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    await auth_service.change_password(
        session,
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return StatusResponse()


@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    return user


@router.patch("/me/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    return await auth_service.update_profile(
        session,
        user=user,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )


@router.patch("/me/preferences", response_model=UserResponse)
async def update_preferences(
    payload: PreferencesUpdateRequest,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    updated = await auth_service.update_preferences(
        session,
        user=user,
        language=payload.language,
        theme=payload.theme,
    )
    if payload.language is not None:
        response.set_cookie(
            "lang",
            updated.language,
            max_age=31536000,
            samesite="lax",
            path="/",
        )
    if payload.theme is not None:
        response.set_cookie(
            "theme",
            updated.theme,
            max_age=31536000,
            samesite="lax",
            path="/",
        )
    return updated
