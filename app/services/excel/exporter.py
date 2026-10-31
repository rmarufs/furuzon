import io
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

import openpyxl
from openpyxl.cell.cell import TYPE_STRING
from openpyxl.styles import Font

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def sanitize_group_filename(group_number: str) -> str:
    cleaned = _UNSAFE_FILENAME_RE.sub("_", group_number).strip().strip(".")
    if not cleaned:
        cleaned = "group"
    return f"{cleaned}.xlsx"


def build_content_disposition(filename: str) -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fallback or ascii_fallback == ".xlsx":
        ascii_fallback = "group.xlsx"
    ascii_fallback = ascii_fallback.replace('"', "").replace("\\", "_")
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def export_group_to_xlsx(
    columns: Sequence[dict[str, str]],
    students: Sequence[Any],
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None

    bold_font = Font(bold=True)
    for col_idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.value = str(col.get("title", ""))
        cell.data_type = TYPE_STRING
        cell.font = bold_font

    ordered_students = sorted(
        students,
        key=lambda s: getattr(s, "position", 0),
    )
    for row_idx, student in enumerate(ordered_students, start=2):
        data: dict[str, Any] = getattr(student, "data", {}) or {}
        for col_idx, col in enumerate(columns, start=1):
            key = col["key"]
            raw_val = data.get(key, "")
            str_val = "" if raw_val is None else str(raw_val)
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.value = str_val
            cell.data_type = TYPE_STRING

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
