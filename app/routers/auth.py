from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
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


@router.post("/auth/register", response_model=UserResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
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
) -> User:
    user = await auth_service.authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )
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
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
    await auth_service.request_password_reset(session, email=payload.email)
    return StatusResponse()


@router.post("/auth/reset-password", response_model=StatusResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusResponse:
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
