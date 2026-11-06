import io
import math
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import xlrd

from app.core.exceptions import AppError

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_SIZE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 2000
MAX_COLUMNS = 50
MAX_RAW_SCAN_ROWS = 10000
MAX_RAW_SCAN_COLUMNS = 500

ZIP_SIGNATURE = b"PK\x03\x04"
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
XLSX_WORKBOOK_ENTRY = "xl/workbook.xml"


@dataclass(slots=True)
class ParsedSheet:
    rows: list[list[str]]
    row_count: int
    column_count: int


def _format_number(value: int | float | Decimal) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        if value.is_integer():
            return str(int(round(value)))
        dec = Decimal(str(value))
    elif isinstance(value, Decimal):
        if not value.is_finite():
            return ""
        if value == value.to_integral_value():
            return str(int(value))
        dec = value
    else:
        return str(value)

    formatted = format(dec.normalize(), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def format_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, datetime | date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, int | float | Decimal):
        return _format_number(value)
    return str(value).strip()


def _validate_and_detect_format(data: bytes, filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise AppError("invalid_file_type", status_code=415)

    if len(data) > MAX_FILE_SIZE_BYTES:
        raise AppError("file_too_large", status_code=413)

    if len(data) == 0:
        raise AppError("excel_empty", status_code=422)

    if ext == ".xlsx":
        if not data.startswith(ZIP_SIGNATURE):
            raise AppError("invalid_file_type", status_code=415)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if XLSX_WORKBOOK_ENTRY not in names:
                    raise AppError("invalid_file_type", status_code=415)
                total_unpacked = sum(info.file_size for info in archive.infolist())
                if total_unpacked > MAX_UNPACKED_SIZE_BYTES:
                    raise AppError("file_too_large", status_code=413)
        except zipfile.BadZipFile as exc:
            raise AppError("invalid_file_type", status_code=415) from exc
        return "xlsx"

    if not data.startswith(OLE_SIGNATURE):
        raise AppError("invalid_file_type", status_code=415)
    return "xls"


def _normalize_sheet_rows(raw_rows: list[list[str]]) -> ParsedSheet | None:
    non_empty_rows = [
        row for row in raw_rows if any(cell != "" for cell in row)
    ]
    if not non_empty_rows:
        return None

    if len(non_empty_rows) > MAX_ROWS:
        raise AppError("excel_too_large", status_code=422)

    max_cols = max(len(row) for row in non_empty_rows)
    active_cols = [
        col_idx
        for col_idx in range(max_cols)
        if any(
            col_idx < len(row) and row[col_idx] != ""
            for row in non_empty_rows
        )
    ]
    if not active_cols:
        return None

    if len(active_cols) > MAX_COLUMNS:
        raise AppError("excel_too_large", status_code=422)

    normalized = [
        [row[col_idx] if col_idx < len(row) else "" for col_idx in active_cols]
        for row in non_empty_rows
    ]
    return ParsedSheet(
        rows=normalized,
        row_count=len(normalized),
        column_count=len(active_cols),
    )


def _read_xlsx(data: bytes) -> ParsedSheet:
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(data),
            read_only=True,
            data_only=True,
        )
    except Exception as exc:
        raise AppError("invalid_file_type", status_code=415) from exc

    try:
        for sheet in workbook.worksheets:
            raw_rows: list[list[str]] = []
            for raw_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                if raw_idx >= MAX_RAW_SCAN_ROWS:
                    raise AppError("excel_too_large", status_code=422)
                if len(row) > MAX_RAW_SCAN_COLUMNS:
                    non_empty_in_row = sum(
                        1 for cell in row if format_cell_value(cell) != ""
                    )
                    if non_empty_in_row > MAX_COLUMNS:
                        raise AppError("excel_too_large", status_code=422)

                formatted = [format_cell_value(cell) for cell in row]
                while formatted and formatted[-1] == "":
                    formatted.pop()
                if formatted:
                    raw_rows.append(formatted)
                    if len(raw_rows) > MAX_ROWS:
                        raise AppError("excel_too_large", status_code=422)

            parsed = _normalize_sheet_rows(raw_rows)
            if parsed is not None:
                return parsed
    finally:
        workbook.close()

    raise AppError("excel_empty", status_code=422)


def _format_xls_cell(cell: xlrd.sheet.Cell, datemode: int) -> str:
    ctype = cell.ctype
    value = cell.value
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return ""
    if ctype == xlrd.XL_CELL_DATE:
        try:
            dt = xlrd.xldate_as_datetime(value, datemode)
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return format_cell_value(value)
    if ctype == xlrd.XL_CELL_BOOLEAN:
        return str(bool(value))
    return format_cell_value(value)


def _read_xls(data: bytes) -> ParsedSheet:
    try:
        workbook = xlrd.open_workbook(file_contents=data)
    except Exception as exc:
        raise AppError("invalid_file_type", status_code=415) from exc

    for sheet in workbook.sheets():
        if sheet.nrows == 0 or sheet.ncols == 0:
            continue
        if sheet.ncols > MAX_RAW_SCAN_COLUMNS:
            raise AppError("excel_too_large", status_code=422)
        raw_rows: list[list[str]] = []
        for row_idx in range(sheet.nrows):
            if row_idx >= MAX_RAW_SCAN_ROWS:
                raise AppError("excel_too_large", status_code=422)
            formatted = [
                _format_xls_cell(sheet.cell(row_idx, col_idx), workbook.datemode)
                for col_idx in range(sheet.ncols)
            ]
            while formatted and formatted[-1] == "":
                formatted.pop()
            if formatted:
                raw_rows.append(formatted)
                if len(raw_rows) > MAX_ROWS:
                    raise AppError("excel_too_large", status_code=422)

        parsed = _normalize_sheet_rows(raw_rows)
        if parsed is not None:
            return parsed

    raise AppError("excel_empty", status_code=422)


def read_workbook(data: bytes, filename: str) -> ParsedSheet:
    fmt = _validate_and_detect_format(data, filename)
    if fmt == "xlsx":
        return _read_xlsx(data)
    return _read_xls(data)
