import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.group import Group, Student
from app.services.excel.reader import read_workbook
from app.services.excel.table import PreviewData, build_preview, build_table


async def get_owned_group_or_404(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
) -> Group:
    group = await session.scalar(
        select(Group).where(
            Group.id == group_id,
            Group.owner_id == owner_id,
        )
    )
    if group is None:
        raise AppError("group_not_found", status_code=404)
    return group


async def parse_group_excel(
    *,
    data: bytes,
    filename: str,
    header_row: int | None = None,
) -> PreviewData:
    def _sync_parse() -> PreviewData:
        parsed = read_workbook(data, filename)
        return build_preview(parsed, header_row=header_row)

    return await asyncio.to_thread(_sync_parse)


def _extract_group_table(
    data: bytes,
    filename: str,
    header_row: int,
    columns: list[int],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    parsed = read_workbook(data, filename)
    raw_columns, data_rows = build_table(parsed, header_row)

    if not columns or len(set(columns)) != len(columns):
        raise AppError("invalid_columns", status_code=422)

    col_count = len(raw_columns)
    for col_idx in columns:
        if not isinstance(col_idx, int) or isinstance(col_idx, bool):
            raise AppError("invalid_columns", status_code=422)
        if col_idx < 0 or col_idx >= col_count:
            raise AppError("invalid_columns", status_code=422)

    group_columns: list[dict[str, str]] = []
    for pos, src_idx in enumerate(columns, start=1):
        key = f"c{pos}"
        title = raw_columns[src_idx]["title"]
        group_columns.append({"key": key, "title": title})

    students_data: list[dict[str, str]] = []
    for row in data_rows:
        student_cells: dict[str, str] = {}
        for pos, src_idx in enumerate(columns, start=1):
            key = f"c{pos}"
            val = row[src_idx] if src_idx < len(row) else ""
            student_cells[key] = val.strip() if isinstance(val, str) else str(val)
        if all(val == "" for val in student_cells.values()):
            continue
        students_data.append(student_cells)

    return group_columns, students_data


async def create_group_from_excel(
    session: AsyncSession,
    *,
    owner_id: int,
    data: bytes,
    filename: str,
    header_row: int,
    columns: list[int],
    number: str,
    course: int,
) -> dict[str, Any]:
    group_columns, students_data = await asyncio.to_thread(
        _extract_group_table,
        data,
        filename,
        header_row,
        columns,
    )

    group = Group(
        owner_id=owner_id,
        number=number,
        course=course,
        columns=group_columns,
    )
    session.add(group)
    await session.flush()

    student_models: list[Student] = []
    for idx, cell_map in enumerate(students_data):
        student = Student(
            group_id=group.id,
            position=idx,
            data=cell_map,
        )
        session.add(student)
        student_models.append(student)

    await session.flush()
    await session.refresh(group)
    for student in student_models:
        await session.refresh(student)

    return {
        "id": group.id,
        "number": group.number,
        "course": group.course,
        "columns": group.columns,
        "students": student_models,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


async def list_groups(
    session: AsyncSession,
    *,
    owner_id: int,
    course: int | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            Group.id,
            Group.number,
            Group.course,
            Group.updated_at,
            func.count(Student.id).label("students_count"),
        )
        .outerjoin(Student, Student.group_id == Group.id)
        .where(Group.owner_id == owner_id)
    )
    if course is not None:
        stmt = stmt.where(Group.course == course)

    stmt = stmt.group_by(Group.id).order_by(Group.number.asc(), Group.id.asc())
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "number": row.number,
            "course": row.course,
            "students_count": int(row.students_count),
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


async def get_group_detail(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
) -> dict[str, Any]:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )
    students_stmt = (
        select(Student)
        .where(Student.group_id == group.id)
        .order_by(Student.position.asc(), Student.id.asc())
    )
    students = list((await session.scalars(students_stmt)).all())
    return {
        "id": group.id,
        "number": group.number,
        "course": group.course,
        "columns": group.columns,
        "students": students,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


async def update_group(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
    number: str | None = None,
    course: int | None = None,
    columns_order: list[str] | None = None,
) -> dict[str, Any]:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )

    if columns_order is not None:
        existing_by_key = {col["key"]: col for col in group.columns}
        if (
            len(columns_order) != len(existing_by_key)
            or set(columns_order) != set(existing_by_key.keys())
        ):
            raise AppError("invalid_columns", status_code=422)
        group.columns = [existing_by_key[key] for key in columns_order]

    if number is not None:
        group.number = number

    if course is not None:
        group.course = course

    group.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(group)

    students_stmt = (
        select(Student)
        .where(Student.group_id == group.id)
        .order_by(Student.position.asc(), Student.id.asc())
    )
    students = list((await session.scalars(students_stmt)).all())
    return {
        "id": group.id,
        "number": group.number,
        "course": group.course,
        "columns": group.columns,
        "students": students,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


async def delete_group(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
) -> None:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )
    await session.delete(group)
    await session.flush()
