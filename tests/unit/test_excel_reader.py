from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from app.core.exceptions import AppError
from app.services.excel.reader import MAX_FILE_SIZE_BYTES, read_workbook

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _save_xlsx(
    tmp_path: Path,
    rows: list[list[Any]],
    filename: str = "test.xlsx",
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    file_path = tmp_path / filename
    wb.save(file_path)
    return file_path.read_bytes()


def test_read_clean_table_and_trimming(tmp_path: Path) -> None:
    data = _save_xlsx(
        tmp_path,
        [
            [None, None, None],
            [None, "  №  ", " ФИО ", None, " Группа "],
            [None, 1, " Иванов И.И. ", None, "ИС-21"],
            [None, None, None],
            [None, 2, " Петрова А.С. ", None, "ИС-21"],
        ],
    )
    parsed = read_workbook(data, "group.xlsx")
    assert parsed.row_count == 3
    assert parsed.column_count == 3
    assert parsed.rows == [
        ["№", "ФИО", "Группа"],
        ["1", "Иванов И.И.", "ИС-21"],
        ["2", "Петрова А.С.", "ИС-21"],
    ]


def test_formatting_numbers_and_dates(tmp_path: Path) -> None:
    data = _save_xlsx(
        tmp_path,
        [
            ["№", "Оценка", "Средний балл", "Дата", "Время", "Телефон"],
            [
                5.0,
                4,
                4.75,
                date(2026, 10, 31),
                datetime(2026, 5, 9, 14, 30),
                992900123456.0,
            ],
        ],
    )
    parsed = read_workbook(data, "fmt.xlsx")
    assert parsed.rows[1] == [
        "5",
        "4",
        "4.75",
        "31.10.2026",
        "09.05.2026",
        "992900123456",
    ]


def test_first_sheet_empty_reads_second_sheet(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    first = wb.active
    assert first is not None
    first.title = "Empty"
    first.append([None, "   ", None])

    second = wb.create_sheet("Students")
    second.append(["№", "ФИО"])
    second.append([1, "Раҳмонов А."])

    path = tmp_path / "two_sheets.xlsx"
    wb.save(path)

    parsed = read_workbook(path.read_bytes(), "two_sheets.xlsx")
    assert parsed.rows == [["№", "ФИО"], ["1", "Раҳмонов А."]]


def test_students_with_empty_cells_padded_to_width(tmp_path: Path) -> None:
    data = _save_xlsx(
        tmp_path,
        [
            ["№", "ФИО", "Телефон", "Примечание"],
            [1, "Иванов И.", None, "Староста"],
            [2, "Петрова А.", "992900111222", None],
        ],
    )
    parsed = read_workbook(data, "sparse_students.xlsx")
    assert parsed.column_count == 4
    assert parsed.rows[1] == ["1", "Иванов И.", "", "Староста"]
    assert parsed.rows[2] == ["2", "Петрова А.", "992900111222", ""]


def test_invalid_extension(tmp_path: Path) -> None:
    data = _save_xlsx(tmp_path, [["ФИО"], ["Иванов И."]])
    with pytest.raises(AppError) as exc_info:
        read_workbook(data, "students.csv")
    assert exc_info.value.status_code == 415
    assert exc_info.value.code == "invalid_file_type"


def test_xlsx_renamed_to_xls_rejected(tmp_path: Path) -> None:
    data = _save_xlsx(tmp_path, [["ФИО"], ["Иванов И."]])
    with pytest.raises(AppError) as exc_info:
        read_workbook(data, "renamed.xls")
    assert exc_info.value.status_code == 415
    assert exc_info.value.code == "invalid_file_type"


def test_text_file_named_xlsx_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        read_workbook(b"not an excel file", "fake.xlsx")
    assert exc_info.value.status_code == 415
    assert exc_info.value.code == "invalid_file_type"


def test_file_too_large_rejected() -> None:
    huge = b"0" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(AppError) as exc_info:
        read_workbook(huge, "huge.xlsx")
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "file_too_large"


def test_empty_file_and_empty_workbook(tmp_path: Path) -> None:
    with pytest.raises(AppError) as exc_info:
        read_workbook(b"", "empty.xlsx")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "excel_empty"

    data = _save_xlsx(tmp_path, [[None, "  "], [None, None]])
    with pytest.raises(AppError) as exc_info2:
        read_workbook(data, "blank.xlsx")
    assert exc_info2.value.status_code == 422
    assert exc_info2.value.code == "excel_empty"


def test_more_than_2000_rows_rejected(tmp_path: Path) -> None:
    rows: list[list[Any]] = [["№", "ФИО"]] + [
        [i, f"Студент {i}"] for i in range(1, 2001)
    ]
    data = _save_xlsx(tmp_path, rows, "too_many_rows.xlsx")
    with pytest.raises(AppError) as exc_info:
        read_workbook(data, "too_many_rows.xlsx")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "excel_too_large"


def test_more_than_50_columns_rejected(tmp_path: Path) -> None:
    rows = [[f"Col {i}" for i in range(51)], [f"Val {i}" for i in range(51)]]
    data = _save_xlsx(tmp_path, rows, "too_many_cols.xlsx")
    with pytest.raises(AppError) as exc_info:
        read_workbook(data, "too_many_cols.xlsx")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "excel_too_large"


def test_read_sample_old_xls_if_present() -> None:
    xls_path = FIXTURES_DIR / "sample_old.xls"
    if not xls_path.exists():
        pytest.skip("tests/fixtures/sample_old.xls is not present")
    parsed = read_workbook(xls_path.read_bytes(), xls_path.name)
    assert parsed.row_count > 0
    assert parsed.column_count > 0
