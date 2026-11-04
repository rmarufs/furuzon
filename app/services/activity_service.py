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
    now = datetime.now(UTC)

    # Events without an object (e.g. a deleted file) are never collapsed:
    # DEF-2 collapses repeats only for the same existing object.
    if object_id is None:
        item = Activity(
            owner_id=owner_id,
            type=action_type,
            object_type=object_type,
            object_id=None,
            object_title=object_title,
            created_at=now,
        )
        session.add(item)
        await session.flush()
        await session.refresh(item)
        return item

    stmt = select(Activity).where(
        Activity.owner_id == owner_id,
        Activity.type == action_type,
        Activity.object_type == object_type,
        Activity.object_id == object_id,
    )

    existing = await session.scalar(stmt.order_by(Activity.created_at.desc()))
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
