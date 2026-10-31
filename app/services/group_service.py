import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.group import Group, Student
from app.services import student_search
from app.services.excel.exporter import export_group_to_xlsx, sanitize_group_filename
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


async def _get_group_student_or_404(
    session: AsyncSession,
    *,
    group_id: int,
    student_id: int,
) -> Student:
    student = await session.scalar(
        select(Student).where(
            Student.id == student_id,
            Student.group_id == group_id,
        )
    )
    if student is None:
        raise AppError("student_not_found", status_code=404)
    return student


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


async def add_student(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
    data: dict[str, Any],
) -> Student:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )

    allowed_keys = {col["key"] for col in group.columns}
    if not set(data.keys()).issubset(allowed_keys):
        raise AppError("invalid_columns", status_code=422)

    cleaned_data: dict[str, str] = {}
    for col in group.columns:
        key = col["key"]
        raw_val = data.get(key, "")
        if raw_val is None:
            raw_val = ""
        if not isinstance(raw_val, str):
            raise AppError("validation_error", status_code=422)
        trimmed = raw_val.strip()
        if len(trimmed) > 500:
            raise AppError("validation_error", status_code=422)
        cleaned_data[key] = trimmed

    if all(val == "" for val in cleaned_data.values()):
        raise AppError("student_empty", status_code=422)

    max_pos = await session.scalar(
        select(func.max(Student.position)).where(Student.group_id == group.id)
    )
    next_pos = 0 if max_pos is None else int(max_pos) + 1

    student = Student(
        group_id=group.id,
        position=next_pos,
        data=cleaned_data,
    )
    session.add(student)
    group.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(student)
    return student


async def update_student_cell(
    session: AsyncSession,
    *,
    group_id: int,
    student_id: int,
    owner_id: int,
    key: str,
    value: str,
) -> Student:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )
    allowed_keys = {col["key"] for col in group.columns}
    if key not in allowed_keys:
        raise AppError("invalid_columns", status_code=422)

    student = await _get_group_student_or_404(
        session,
        group_id=group.id,
        student_id=student_id,
    )

    new_data = dict(student.data)
    new_data[key] = value
    student.data = new_data
    group.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(student)
    return student


async def delete_student(
    session: AsyncSession,
    *,
    group_id: int,
    student_id: int,
    owner_id: int,
) -> None:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )
    student = await _get_group_student_or_404(
        session,
        group_id=group.id,
        student_id=student_id,
    )
    await session.delete(student)
    group.updated_at = datetime.now(UTC)
    await session.flush()


async def delete_group_column(
    session: AsyncSession,
    *,
    group_id: int,
    column_key: str,
    owner_id: int,
) -> dict[str, Any]:
    group = await get_owned_group_or_404(
        session,
        group_id=group_id,
        owner_id=owner_id,
    )

    existing_keys = [col["key"] for col in group.columns]
    if column_key not in existing_keys:
        raise AppError("column_not_found", status_code=404)

    if len(group.columns) <= 1:
        raise AppError("cannot_delete_last_column", status_code=409)

    group.columns = [
        col for col in group.columns if col["key"] != column_key
    ]
    group.updated_at = datetime.now(UTC)

    await session.execute(
        update(Student)
        .where(Student.group_id == group.id)
        .values(data=Student.data.op("-")(column_key))
        .execution_options(synchronize_session="fetch")
    )
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


async def search_group_students(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
    query: str | None = None,
) -> list[Student]:
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
    return student_search.search_students(students, query)


async def export_group(
    session: AsyncSession,
    *,
    group_id: int,
    owner_id: int,
) -> tuple[bytes, str]:
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
    xlsx_bytes = await asyncio.to_thread(
        export_group_to_xlsx,
        group.columns,
        students,
    )
    filename = sanitize_group_filename(group.number)
    return xlsx_bytes, filename
