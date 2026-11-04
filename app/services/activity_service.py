from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity


async def record_activity(
    session: AsyncSession,
    *,
    owner_id: int,
    action_type: str,
    object_type: str,
    object_id: int | None,
    object_title: str,
) -> Activity:
    stmt = select(Activity).where(
        Activity.owner_id == owner_id,
        Activity.type == action_type,
        Activity.object_type == object_type,
    )
    if object_id is not None:
        stmt = stmt.where(Activity.object_id == object_id)
    else:
        stmt = stmt.where(
            Activity.object_id.is_(None),
            Activity.object_title == object_title,
        )

    existing = await session.scalar(stmt.order_by(Activity.created_at.desc()))
    now = datetime.now(UTC)
    if existing is not None:
        existing.object_title = object_title
        existing.created_at = now
        await session.flush()
        await session.refresh(existing)
        return existing

    item = Activity(
        owner_id=owner_id,
        type=action_type,
        object_type=object_type,
        object_id=object_id,
        object_title=object_title,
        created_at=now,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


async def delete_group_activity(
    session: AsyncSession,
    *,
    owner_id: int,
    group_id: int,
) -> None:
    await session.execute(
        delete(Activity).where(
            Activity.owner_id == owner_id,
            Activity.object_type == "group",
            Activity.object_id == group_id,
        )
    )
    await session.flush()


async def list_recent_activity(
    session: AsyncSession,
    *,
    owner_id: int,
    limit: int = 4,
) -> list[Activity]:
    stmt = (
        select(Activity)
        .where(Activity.owner_id == owner_id)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())
