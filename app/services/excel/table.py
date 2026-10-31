from typing import Any

from app.core.exceptions import AppError
from app.services.excel.header_detect import detect_header_row
from app.services.excel.reader import ParsedSheet

PREVIEW_MAX_ROWS = 30


class PreviewData(dict[str, Any]):
    """Dictionary with attribute access for preview properties."""

    @property
    def rows(self) -> list[list[str]]:
        return self["rows"]

    @property
    def header_row(self) -> int:
        return self["header_row"]

    @property
    def columns(self) -> list[dict[str, Any]]:
        return self["columns"]

    @property
    def data_rows_count(self) -> int:
        return self["data_rows_count"]


def build_table(
    parsed: ParsedSheet,
    header_row: int,
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    if not parsed.rows or header_row < 0 or header_row >= len(parsed.rows):
        raise AppError("invalid_header_row", status_code=422)

    raw_header = parsed.rows[header_row]
    columns: list[dict[str, Any]] = []
    for idx, cell in enumerate(raw_header):
        cleaned = cell.strip()
        title = cleaned if cleaned else f"#{idx + 1}"
        columns.append({"index": idx, "title": title})

    data_rows = [list(row) for row in parsed.rows[header_row + 1 :]]
    return columns, data_rows


def build_preview(
    parsed: ParsedSheet,
    header_row: int | None = None,
) -> PreviewData:
    resolved_header = (
        detect_header_row(parsed.rows) if header_row is None else header_row
    )
    columns, data_rows = build_table(parsed, resolved_header)
    return PreviewData(
        rows=[list(row) for row in parsed.rows[:PREVIEW_MAX_ROWS]],
        header_row=resolved_header,
        columns=columns,
        data_rows_count=len(data_rows),
    )
