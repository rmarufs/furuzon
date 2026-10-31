from pathlib import Path
from typing import Any

import openpyxl
import pytest

from app.services.excel.header_detect import detect_header_row
from app.services.excel.reader import read_workbook
from app.services.excel.table import build_preview, build_table

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _make_xlsx(tmp_path: Path, rows: list[list[Any]], name: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    path = tmp_path / name
    wb.save(path)
    return path.read_bytes()


def test_header_clean_table(tmp_path: Path) -> None:
    data = _make_xlsx(
        tmp_path,
        [
            ["№", "ФИО", "Зачётная книжка"],
            [1, "Иванов Иван Иванович", "21001"],
            [2, "Петрова Анна Сергеевна", "21002"],
        ],
        "clean.xlsx",
    )
    parsed = read_workbook(data, "clean.xlsx")
    assert detect_header_row(parsed.rows) == 0


@pytest.mark.parametrize("title_count", [1, 2, 3, 4, 5])
def test_header_with_1_to_5_title_rows(
    tmp_path: Path,
    title_count: int,
) -> None:
    titles: list[list[Any]] = [
        [f"Титульная строка {i + 1}", None, None, None]
        for i in range(title_count)
    ]
    rows: list[list[Any]] = [
        *titles,
        ["№", "ФИО", "Группа", "Примечание"],
        [1, "Раҳмонов А.", "ИС-21", "Староста"],
        [2, "Ҷалилова М.", "ИС-21", ""],
        [3, "Ҳакимов Қ.", "ИС-21", ""],
    ]
    data = _make_xlsx(tmp_path, rows, f"titles_{title_count}.xlsx")
    parsed = read_workbook(data, f"titles_{title_count}.xlsx")
    assert detect_header_row(parsed.rows) == title_count


def test_header_with_empty_rows_on_top_and_merged_title_cells(
    tmp_path: Path,
) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None

    # Empty rows at the very top
    ws.append([None, None, None])
    ws.append([None, None, None])
    # Title rows with merged cells across A3:C3 and A4:C4
    ws["A3"] = "Министерство образования и науки"
    ws.merge_cells("A3:C3")
    ws["A4"] = "Список студентов группы ИС-21"
    ws.merge_cells("A4:C4")
    # Blank row between title and table
    ws.append([None, None, None])
    # Header row
    ws.append(["№", "ФИО", "Телефон"])
    ws.append([1, "Иванов И.И.", "992900111222"])
    ws.append([2, "Петрова А.А.", "992900333444"])

    path = tmp_path / "merged.xlsx"
    wb.save(path)

    parsed = read_workbook(path.read_bytes(), "merged.xlsx")
    header_idx = detect_header_row(parsed.rows)
    assert header_idx == 2
    assert parsed.rows[header_idx] == ["№", "ФИО", "Телефон"]


def test_header_with_empty_cells_and_table_builder(tmp_path: Path) -> None:
    data = _make_xlsx(
        tmp_path,
        [
            ["Ведомость группы ИС-21", None, None, None],
            ["№", "ФИО", None, "Примечание"],
            [1, "Иванов И.", "бюджет", ""],
            [2, "Петрова А.", "договор", "староста"],
        ],
        "empty_header_cell.xlsx",
    )
    parsed = read_workbook(data, "empty_header_cell.xlsx")
    header_idx = detect_header_row(parsed.rows)
    assert header_idx == 1

    columns, data_rows = build_table(parsed, header_idx)
    assert columns == [
        {"index": 0, "title": "№"},
        {"index": 1, "title": "ФИО"},
        {"index": 2, "title": "#3"},
        {"index": 3, "title": "Примечание"},
    ]
    assert len(data_rows) == 2

    preview = build_preview(parsed)
    assert preview.header_row == 1
    assert preview.data_rows_count == 2
    assert preview.columns[2]["title"] == "#3"


def test_single_column_student_list(tmp_path: Path) -> None:
    data = _make_xlsx(
        tmp_path,
        [
            ["ФИО"],
            ["Иванов Иван Иванович"],
            ["Петрова Анна Сергеевна"],
            ["Сидоров Кирилл Олегович"],
        ],
        "one_col.xlsx",
    )
    parsed = read_workbook(data, "one_col.xlsx")
    assert detect_header_row(parsed.rows) == 0

    data_with_title = _make_xlsx(
        tmp_path,
        [
            ["Группа ИС-21"],
            ["ФИО"],
            ["Иванов Иван Иванович"],
            ["Петрова Анна Сергеевна"],
        ],
        "one_col_titled.xlsx",
    )
    parsed_titled = read_workbook(data_with_title, "one_col_titled.xlsx")
    assert detect_header_row(parsed_titled.rows) == 1


def test_numeric_first_column_under_text_header(tmp_path: Path) -> None:
    data = _make_xlsx(
        tmp_path,
        [
            ["Факультет ИТ", "2 курс"],
            ["№", "ФИО"],
            [1, "Иванов И.И."],
            [2, "Петрова А.А."],
            [3, "Сидоров К.О."],
        ],
        "num_col.xlsx",
    )
    parsed = read_workbook(data, "num_col.xlsx")
    assert detect_header_row(parsed.rows) == 1


def test_preview_limits_to_30_rows(tmp_path: Path) -> None:
    rows: list[list[Any]] = [["№", "ФИО"]] + [
        [i, f"Студент {i}"] for i in range(1, 45)
    ]
    data = _make_xlsx(tmp_path, rows, "forty_five.xlsx")
    parsed = read_workbook(data, "forty_five.xlsx")
    preview = build_preview(parsed)
    assert len(preview.rows) == 30
    assert preview.header_row == 0
    assert preview.data_rows_count == 44


def test_private_fixtures_if_present() -> None:
    private_dir = FIXTURES_DIR / "private"
    if not private_dir.exists():
        pytest.skip("tests/fixtures/private/ does not exist")
    files = [
        p
        for p in sorted(private_dir.iterdir())
        if p.suffix.lower() in (".xlsx", ".xls")
    ]
    if not files:
        pytest.skip("No Excel files in tests/fixtures/private/")

    for file_path in files:
        parsed = read_workbook(file_path.read_bytes(), file_path.name)
        header_idx = detect_header_row(parsed.rows)
        assert 0 <= header_idx < parsed.row_count, file_path.name
