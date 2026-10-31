import io
import json
from typing import Any

import openpyxl
from httpx import AsyncClient


def _make_xlsx_bytes(rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _register(
    client: AsyncClient,
    email: str = "teacher@example.com",
    password: str = "password123",
) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200


async def _login(
    client: AsyncClient,
    email: str,
    password: str = "password123",
) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200


async def test_groups_endpoints_require_authentication(
    client: AsyncClient,
) -> None:
    xlsx_data = _make_xlsx_bytes([["ФИО"], ["Иванов И."]])

    r_parse = await client.post(
        "/api/groups/parse",
        files={
            "file": (
                "group.xlsx",
                xlsx_data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r_parse.status_code == 401
    assert r_parse.json()["error"]["code"] == "not_authenticated"

    r_create = await client.post(
        "/api/groups",
        files={
            "file": (
                "group.xlsx",
                xlsx_data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={
            "header_row": "0",
            "columns": "[0]",
            "number": "101",
            "course": "1",
        },
    )
    assert r_create.status_code == 401
    assert r_create.json()["error"]["code"] == "not_authenticated"

    r_list = await client.get("/api/groups")
    assert r_list.status_code == 401
    assert r_list.json()["error"]["code"] == "not_authenticated"

    r_get = await client.get("/api/groups/1")
    assert r_get.status_code == 401
    assert r_get.json()["error"]["code"] == "not_authenticated"

    r_patch = await client.patch("/api/groups/1", json={"number": "102"})
    assert r_patch.status_code == 401
    assert r_patch.json()["error"]["code"] == "not_authenticated"

    r_del = await client.delete("/api/groups/1")
    assert r_del.status_code == 401
    assert r_del.json()["error"]["code"] == "not_authenticated"


async def test_parse_group_and_override_header_row(
    client: AsyncClient,
) -> None:
    await _register(client)

    rows = [
        ["Ведомость успеваемости", "", ""],
        ["Факультет информатики", "", ""],
        ["№", "ФИО студента", "Зачётка"],
        [1, "Алиев Анвар", "24001"],
        [2, "Бобоев Бахром", "24002"],
    ]
    xlsx_data = _make_xlsx_bytes(rows)

    resp = await client.post(
        "/api/groups/parse",
        files={"file": ("list.xlsx", xlsx_data)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["header_row"] == 2
    assert body["columns"] == [
        {"index": 0, "title": "№"},
        {"index": 1, "title": "ФИО студента"},
        {"index": 2, "title": "Зачётка"},
    ]
    assert body["data_rows_count"] == 2
    assert len(body["rows"]) == 5

    # Override header_row explicitly
    resp_override = await client.post(
        "/api/groups/parse",
        files={"file": ("list.xlsx", xlsx_data)},
        data={"header_row": "0"},
    )
    assert resp_override.status_code == 200
    body_override = resp_override.json()
    assert body_override["header_row"] == 0
    assert body_override["columns"] == [
        {"index": 0, "title": "Ведомость успеваемости"},
        {"index": 1, "title": "#2"},
        {"index": 2, "title": "#3"},
    ]
    assert body_override["data_rows_count"] == 4


async def test_parse_and_create_invalid_header_row(
    client: AsyncClient,
) -> None:
    await _register(client)
    xlsx_data = _make_xlsx_bytes(
        [
            ["№", "ФИО"],
            [1, "Иванов И."],
        ]
    )

    resp_parse = await client.post(
        "/api/groups/parse",
        files={"file": ("list.xlsx", xlsx_data)},
        data={"header_row": "5"},
    )
    assert resp_parse.status_code == 422
    assert resp_parse.json()["error"]["code"] == "invalid_header_row"

    resp_create = await client.post(
        "/api/groups",
        files={"file": ("list.xlsx", xlsx_data)},
        data={
            "header_row": "-1",
            "columns": "[0, 1]",
            "number": "101",
            "course": "1",
        },
    )
    assert resp_create.status_code == 422
    assert resp_create.json()["error"]["code"] == "invalid_header_row"


async def test_create_group_with_reordered_and_dropped_columns(
    client: AsyncClient,
) -> None:
    await _register(client)
    rows = [
        ["Шапка документа", "", "", ""],
        ["№", "ФИО", "Телефон", "Примечание"],
        [1, "Каримов Рустам", "900112233", "староста"],
        [2, "", "", "полностью пустая строка оставленных колонок"],
        [3, "Саидова Мадина", "900445566", ""],
    ]
    xlsx_data = _make_xlsx_bytes(rows)

    # Keep only columns 2 ("Телефон") and 1 ("ФИО") in reversed order [2, 1]
    # Note: row index 3 has №=2 and Примечание=non-empty, but cols 2 and 1 are empty -> skipped!
    resp = await client.post(
        "/api/groups",
        files={"file": ("students.xlsx", xlsx_data)},
        data={
            "header_row": "1",
            "columns": json.dumps([2, 1]),
            "number": "  204-А  ",
            "course": "2",
        },
    )
    assert resp.status_code == 200
    group = resp.json()
    assert group["number"] == "204-А"
    assert group["course"] == 2
    assert group["columns"] == [
        {"key": "c1", "title": "Телефон"},
        {"key": "c2", "title": "ФИО"},
    ]
    assert len(group["students"]) == 2
    assert group["students"][0]["position"] == 0
    assert group["students"][0]["data"] == {
        "c1": "900112233",
        "c2": "Каримов Рустам",
    }
    assert group["students"][1]["position"] == 1
    assert group["students"][1]["data"] == {
        "c1": "900445566",
        "c2": "Саидова Мадина",
    }


async def test_create_group_with_zero_students_allowed(
    client: AsyncClient,
) -> None:
    await _register(client)
    xlsx_data = _make_xlsx_bytes([["ФИО", "Группа"]])

    resp = await client.post(
        "/api/groups",
        files={"file": ("header_only.xlsx", xlsx_data)},
        data={
            "header_row": "0",
            "columns": "[0, 1]",
            "number": "Empty-1",
            "course": "1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["students"] == []
    assert body["columns"] == [
        {"key": "c1", "title": "ФИО"},
        {"key": "c2", "title": "Группа"},
    ]


async def test_create_group_invalid_columns(client: AsyncClient) -> None:
    await _register(client)
    xlsx_data = _make_xlsx_bytes(
        [
            ["№", "ФИО"],
            [1, "Иванов И."],
        ]
    )

    for bad_columns in ["[]", "[0, 0]", "[2]", "[-1]", "not-json", '{"a": 1}', "[true]"]:
        resp = await client.post(
            "/api/groups",
            files={"file": ("list.xlsx", xlsx_data)},
            data={
                "header_row": "0",
                "columns": bad_columns,
                "number": "101",
                "course": "1",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_columns"


async def test_invalid_file_type_returns_415(client: AsyncClient) -> None:
    await _register(client)

    resp_parse = await client.post(
        "/api/groups/parse",
        files={"file": ("students.csv", b"name,phone\nIvan,123\n", "text/csv")},
    )
    assert resp_parse.status_code == 415
    assert resp_parse.json()["error"]["code"] == "invalid_file_type"

    resp_create = await client.post(
        "/api/groups",
        files={"file": ("fake.xlsx", b"not-a-zip-file")},
        data={
            "header_row": "0",
            "columns": "[0]",
            "number": "101",
            "course": "1",
        },
    )
    assert resp_create.status_code == 415
    assert resp_create.json()["error"]["code"] == "invalid_file_type"


async def test_list_filter_by_course_get_patch_and_delete(
    client: AsyncClient,
) -> None:
    await _register(client)
    xlsx_2_students = _make_xlsx_bytes(
        [
            ["ФИО", "Код"],
            ["Студент 1", "A1"],
            ["Студент 2", "A2"],
        ]
    )
    xlsx_1_student = _make_xlsx_bytes(
        [
            ["ФИО", "Код"],
            ["Студент 3", "B1"],
        ]
    )

    # Create 3 groups: two in course 1 ("Б-10", "А-10"), one in course 3 ("В-30")
    r1 = await client.post(
        "/api/groups",
        files={"file": ("g1.xlsx", xlsx_2_students)},
        data={"header_row": "0", "columns": "[0, 1]", "number": "Б-10", "course": "1"},
    )
    assert r1.status_code == 200
    g1_id = r1.json()["id"]

    r2 = await client.post(
        "/api/groups",
        files={"file": ("g2.xlsx", xlsx_1_student)},
        data={"header_row": "0", "columns": "[0, 1]", "number": "А-10", "course": "1"},
    )
    assert r2.status_code == 200
    g2_id = r2.json()["id"]

    r3 = await client.post(
        "/api/groups",
        files={"file": ("g3.xlsx", xlsx_1_student)},
        data={"header_row": "0", "columns": "[0, 1]", "number": "В-30", "course": "3"},
    )
    assert r3.status_code == 200
    g3_id = r3.json()["id"]

    # List all groups -> ordered by number ("А-10", "Б-10", "В-30"), then id
    list_all = await client.get("/api/groups")
    assert list_all.status_code == 200
    items_all = list_all.json()
    assert [item["id"] for item in items_all] == [g2_id, g1_id, g3_id]
    assert items_all[0]["students_count"] == 1
    assert items_all[1]["students_count"] == 2

    # Filter by course=1
    list_c1 = await client.get("/api/groups?course=1")
    assert list_c1.status_code == 200
    assert [item["id"] for item in list_c1.json()] == [g2_id, g1_id]

    # Filter by course=3
    list_c3 = await client.get("/api/groups?course=3")
    assert list_c3.status_code == 200
    assert [item["id"] for item in list_c3.json()] == [g3_id]

    # GET group detail
    detail_resp = await client.get(f"/api/groups/{g1_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["number"] == "Б-10"
    assert detail["course"] == 1
    assert detail["columns"] == [
        {"key": "c1", "title": "ФИО"},
        {"key": "c2", "title": "Код"},
    ]
    assert len(detail["students"]) == 2
    old_updated_at = detail["updated_at"]

    # PATCH number, course, and columns_order
    patch_resp = await client.patch(
        f"/api/groups/{g1_id}",
        json={
            "number": "  Б-10-Нов  ",
            "course": 4,
            "columns_order": ["c2", "c1"],
        },
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["number"] == "Б-10-Нов"
    assert patched["course"] == 4
    assert patched["columns"] == [
        {"key": "c2", "title": "Код"},
        {"key": "c1", "title": "ФИО"},
    ]
    assert patched["updated_at"] >= old_updated_at

    # PATCH with invalid columns_order (not a permutation) -> 422 invalid_columns
    bad_patch = await client.patch(
        f"/api/groups/{g1_id}",
        json={"columns_order": ["c1"]},
    )
    assert bad_patch.status_code == 422
    assert bad_patch.json()["error"]["code"] == "invalid_columns"

    # DELETE group
    del_resp = await client.delete(f"/api/groups/{g1_id}")
    assert del_resp.status_code == 200

    get_deleted = await client.get(f"/api/groups/{g1_id}")
    assert get_deleted.status_code == 404
    assert get_deleted.json()["error"]["code"] == "group_not_found"


async def test_group_isolation_between_teachers(
    client: AsyncClient,
) -> None:
    # Teacher A registers and creates a group
    await _register(client, email="teacher_a@example.com")
    xlsx_data = _make_xlsx_bytes(
        [
            ["ФИО"],
            ["Ахмедов Т."],
        ]
    )
    create_resp = await client.post(
        "/api/groups",
        files={"file": ("a.xlsx", xlsx_data)},
        data={
            "header_row": "0",
            "columns": "[0]",
            "number": "А-1",
            "course": "1",
        },
    )
    assert create_resp.status_code == 200
    group_a_id = create_resp.json()["id"]

    # Teacher B registers (switches session to Teacher B)
    await _register(client, email="teacher_b@example.com")

    # Teacher B list does not contain Teacher A's group
    list_b = await client.get("/api/groups")
    assert list_b.status_code == 200
    assert list_b.json() == []

    # Teacher B gets 404 on GET, PATCH, DELETE of Teacher A's group
    get_b = await client.get(f"/api/groups/{group_a_id}")
    assert get_b.status_code == 404
    assert get_b.json()["error"]["code"] == "group_not_found"

    patch_b = await client.patch(
        f"/api/groups/{group_a_id}",
        json={"number": "Взлом"},
    )
    assert patch_b.status_code == 404
    assert patch_b.json()["error"]["code"] == "group_not_found"

    del_b = await client.delete(f"/api/groups/{group_a_id}")
    assert del_b.status_code == 404
    assert del_b.json()["error"]["code"] == "group_not_found"

    # Switch back to Teacher A and verify group is untouched
    await _login(client, email="teacher_a@example.com")
    get_a = await client.get(f"/api/groups/{group_a_id}")
    assert get_a.status_code == 200
    assert get_a.json()["number"] == "А-1"
