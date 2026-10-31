from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import AppError
from app.models.user import User


async def get_current_user_optional(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return None
    return await session.get(User, user_id)


async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise AppError("not_authenticated", status_code=401)
    return user
