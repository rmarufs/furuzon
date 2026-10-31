import re
from collections.abc import Sequence
from typing import Any, Protocol

from rapidfuzz import fuzz

FUZZY_MIN_QUERY_LEN = 3
FUZZY_THRESHOLD = 80.0
_WHITESPACE_RE = re.compile(r"\s+")


class StudentLike(Protocol):
    position: int
    data: dict[str, Any]


def normalize_search_text(text: str) -> str:
    lowered = text.casefold().replace("ё", "е")
    return _WHITESPACE_RE.sub("", lowered)


def search_students(
    students: Sequence[ Any ],
    query: str | None,
) -> list[Any]:
    ordered = sorted(students, key=lambda s: getattr(s, "position", 0))
    if not query:
        return ordered

    norm_query = normalize_search_text(query)
    if not norm_query:
        return ordered

    exact_matches: list[Any] = []
    fuzzy_matches: list[tuple[float, int, Any]] = []
    allow_fuzzy = len(norm_query) >= FUZZY_MIN_QUERY_LEN

    for student in ordered:
        data: dict[str, Any] = getattr(student, "data", {}) or {}
        norm_cells = [
            normalize_search_text(str(val))
            for val in data.values()
            if val is not None and str(val) != ""
        ]
        norm_cells = [cell for cell in norm_cells if cell]

        if any(norm_query in cell for cell in norm_cells):
            exact_matches.append(student)
            continue

        if allow_fuzzy and norm_cells:
            best_score = max(
                float(fuzz.partial_ratio(norm_query, cell))
                for cell in norm_cells
            )
            if best_score >= FUZZY_THRESHOLD:
                fuzzy_matches.append(
                    (best_score, getattr(student, "position", 0), student)
                )

    fuzzy_matches.sort(key=lambda item: (-item[0], item[1]))
    return exact_matches + [item[2] for item in fuzzy_matches]
