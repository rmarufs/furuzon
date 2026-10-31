import math
import re

MAX_HEADER_SCAN_ROWS = 15
TITLE_SPARSE_CELLS = 1
TITLE_MAX_FILLED_CELLS = 2
MIN_HEADER_FILL_RATIO = 0.6
MIN_HEADER_TEXT_RATIO = 0.6

HEADER_KEYWORDS = frozenset(
    {
        "№",
        "#",
        "n",
        "no",
        "п/п",
        "№ п/п",
        "фио",
        "ф.и.о",
        "ф.и.о.",
        "фамилия",
        "имя",
        "отчество",
        "фамилия имя отчество",
        "студент",
        "студенты",
        "обучающийся",
        "группа",
        "курс",
        "телефон",
        "примечание",
        "зачетка",
        "зачётная книжка",
        "шифр",
        "ному насаб",
        "ном",
        "насаб",
        "донишҷӯ",
        "донишҷӯён",
        "гурӯҳ",
    }
)

_DATE_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$")
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_PHONE_RE = re.compile(r"^[+()0-9\s-]{6,}$")


def _normalize(cell: str) -> str:
    return " ".join(cell.strip().lower().split())


def is_numeric_or_date(cell: str) -> bool:
    val = cell.strip()
    if not val:
        return False
    return bool(
        _NUMBER_RE.match(val) or _DATE_RE.match(val) or _PHONE_RE.match(val)
    )


def is_text_cell(cell: str) -> bool:
    val = cell.strip()
    if not val:
        return False
    if val in ("№", "#"):
        return True
    if is_numeric_or_date(val):
        return False
    return any(ch.isalpha() for ch in val)


def _has_header_keyword(row: list[str]) -> bool:
    for cell in row:
        norm = _normalize(cell).rstrip(":.")
        if not norm:
            continue
        if norm in HEADER_KEYWORDS or f"{norm}." in HEADER_KEYWORDS:
            return True
    return False


def _has_text_to_number_transition(
    candidate: list[str],
    next_row: list[str],
) -> bool:
    limit = min(len(candidate), len(next_row))
    for col_idx in range(limit):
        if is_text_cell(candidate[col_idx]) and is_numeric_or_date(
            next_row[col_idx]
        ):
            return True
    return False


def _row_stats(row: list[str]) -> tuple[int, float]:
    non_empty = [cell.strip() for cell in row if cell.strip() != ""]
    filled = len(non_empty)
    if filled == 0:
        return 0, 0.0
    text_cells = sum(1 for cell in non_empty if is_text_cell(cell))
    return filled, text_cells / filled


def _typical_filled_count(fill_counts: list[int]) -> int:
    sample = sorted(fill_counts[1:] if len(fill_counts) > 1 else fill_counts)
    non_sparse = [count for count in sample if count > TITLE_SPARSE_CELLS]
    target = non_sparse if non_sparse else sample
    idx = int((len(target) - 1) * 0.6)
    return target[idx]


def detect_header_row(rows: list[list[str]]) -> int:
    if len(rows) <= 1:
        return 0

    stats = [_row_stats(row) for row in rows]
    fill_counts = [filled for filled, _ in stats]
    max_filled = max(fill_counts, default=0)
    if max_filled == 0:
        return 0

    scan_limit = min(len(rows) - 1, MAX_HEADER_SCAN_ROWS)

    # Single-column list (e.g. only student names)
    if max_filled == 1:
        for idx in range(scan_limit):
            if _has_header_keyword(rows[idx]):
                return idx
        return 0

    typical_filled = _typical_filled_count(fill_counts)
    min_header_filled = max(
        2,
        math.ceil(typical_filled * MIN_HEADER_FILL_RATIO),
    )

    # Find the last sparse (1-cell) title row before the dense table body
    start_idx = 0
    for idx in range(scan_limit):
        if fill_counts[idx] <= TITLE_SPARSE_CELLS:
            below_dense = sum(
                1
                for after in fill_counts[idx + 1 : idx + 4]
                if after >= min_header_filled
            )
            if below_dense >= 1:
                start_idx = idx + 1

    for idx in range(start_idx, scan_limit):
        filled, text_ratio = stats[idx]
        if filled < min_header_filled or text_ratio < MIN_HEADER_TEXT_RATIO:
            continue

        next_filled, next_text_ratio = stats[idx + 1]

        # If the next row is also header-like and still has data rows below it,
        # skip the current row when it is a title row above the real header.
        if (
            next_filled >= min_header_filled
            and next_text_ratio >= MIN_HEADER_TEXT_RATIO
            and idx + 1 < len(rows) - 1
            and not _has_text_to_number_transition(rows[idx], rows[idx + 1])
            and (
                (
                    filled <= TITLE_MAX_FILLED_CELLS
                    and next_filled > filled
                    and not _has_header_keyword(rows[idx])
                )
                or _has_text_to_number_transition(
                    rows[idx + 1],
                    rows[idx + 2],
                )
                or (
                    not _has_header_keyword(rows[idx])
                    and _has_header_keyword(rows[idx + 1])
                )
            )
        ):
            continue

        return idx

    return start_idx if start_idx < len(rows) else 0
