from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActivityItem
from app.services import activity_service

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity", response_model=list[ActivityItem])
async def get_recent_activity(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=20)] = 4,
) -> list[Activity]:
    return await activity_service.list_recent_activity(
        session,
        owner_id=user.id,
        limit=limit,
    )
