from dataclasses import dataclass

from app.services.student_search import normalize_search_text, search_students


@dataclass
class DummyStudent:
    id: int
    position: int
    data: dict[str, str]


def _sample_students() -> list[DummyStudent]:
    return [
        DummyStudent(
            id=1,
            position=0,
            data={"c1": "Иванов Иван Иванович", "c2": "24001"},
        ),
        DummyStudent(
            id=2,
            position=1,
            data={"c1": "Семёнов Пётр", "c2": "24002"},
        ),
        DummyStudent(
            id=3,
            position=2,
            data={"c1": "Абдуллоев Фарход", "c2": "24003"},
        ),
        DummyStudent(
            id=4,
            position=3,
            data={"c1": "Петрова Анна", "c2": "24004"},
        ),
    ]


def test_normalize_search_text() -> None:
    assert normalize_search_text("  Семёнов   Пётр \t\n ") == "семеновпетр"


def test_search_case_and_whitespace_insensitive() -> None:
    students = _sample_students()
    results = search_students(students, "  ивановиван ")
    assert [s.id for s in results] == [1]


def test_search_yo_ye_equivalence() -> None:
    students = _sample_students()
    res_ye = search_students(students, "семенов петр")
    res_yo = search_students(students, "Семёнов Пётр")
    assert [s.id for s in res_ye] == [2]
    assert [s.id for s in res_yo] == [2]


def test_search_typo_fuzzy_match() -> None:
    students = _sample_students()
    # "Абдулоев" (one 'л' instead of two) matches "Абдуллоев Фарход" via fuzzy
    results = search_students(students, "Абдулоев")
    assert [s.id for s in results] == [3]


def test_search_no_matches() -> None:
    students = _sample_students()
    assert search_students(students, "Зокиров") == []


def test_search_short_query_uses_exact_only() -> None:
    students = _sample_students()
    # "02" is 2 chars -> exact substring match in "24002"
    exact_short = search_students(students, "02")
    assert [s.id for s in exact_short] == [2]

    # "ив" is 2 chars -> exact substring match in "Иванов Иван Иванович"
    assert [s.id for s in search_students(students, "ив")] == [1]

    # "ії" / "ъэ" (not a substring) does not match
    assert search_students(students, "ъэ") == []


def test_search_empty_query_returns_all_in_position_order() -> None:
    students = list(reversed(_sample_students()))
    res_none = search_students(students, None)
    res_empty = search_students(students, "   ")
    assert [s.id for s in res_none] == [1, 2, 3, 4]
    assert [s.id for s in res_empty] == [1, 2, 3, 4]


def test_search_ordering_exact_first_then_fuzzy_by_score_then_position() -> None:
    students = [
        DummyStudent(id=10, position=0, data={"c1": "Каримов Рустам"}),
        DummyStudent(id=20, position=1, data={"c1": "Каримова Дилноза"}),
        DummyStudent(id=30, position=2, data={"c1": "Каримов Рустамджон"}),
    ]
    # Query "Каримова":
    # id=20 has exact substring "каримова".
    # id=10 and id=30 have "каримов" (fuzzy partial_ratio = 87.5 >= 80).
    results = search_students(students, "Каримова")
    assert [s.id for s in results] == [20, 10, 30]
