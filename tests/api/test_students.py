import io
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


async def _create_sample_group(
    client: AsyncClient,
    number: str = "101-А",
    course: int = 1,
    rows: list[list[Any]] | None = None,
) -> dict[str, Any]:
    if rows is None:
        rows = [
            ["ФИО", "Зачётка", "Примечание"],
            ["Иванов Иван", "24001", "староста"],
            ["Семёнов Пётр", "24002", ""],
        ]
    xlsx_data = _make_xlsx_bytes(rows)
    col_indices = list(range(len(rows[0])))
    resp = await client.post(
        "/api/groups",
        files={"file": ("group.xlsx", xlsx_data)},
        data={
            "header_row": "0",
            "columns": str(col_indices),
            "number": number,
            "course": str(course),
        },
    )
    assert resp.status_code == 200
    return resp.json()


async def test_student_and_column_endpoints_require_auth(
    client: AsyncClient,
) -> None:
    r_list = await client.get("/api/groups/1/students")
    assert r_list.status_code == 401
    assert r_list.json()["error"]["code"] == "not_authenticated"

    r_add = await client.post(
        "/api/groups/1/students",
        json={"data": {"c1": "Тест"}},
    )
    assert r_add.status_code == 401
    assert r_add.json()["error"]["code"] == "not_authenticated"

    r_patch = await client.patch(
        "/api/groups/1/students/1",
        json={"key": "c1", "value": "Тест"},
    )
    assert r_patch.status_code == 401
    assert r_patch.json()["error"]["code"] == "not_authenticated"

    r_del_s = await client.delete("/api/groups/1/students/1")
    assert r_del_s.status_code == 401
    assert r_del_s.json()["error"]["code"] == "not_authenticated"

    r_del_col = await client.delete("/api/groups/1/columns/c1")
    assert r_del_col.status_code == 401
    assert r_del_col.json()["error"]["code"] == "not_authenticated"

    r_export = await client.get("/api/groups/1/export")
    assert r_export.status_code == 401
    assert r_export.json()["error"]["code"] == "not_authenticated"


async def test_add_update_delete_student_and_updated_at(
    client: AsyncClient,
) -> None:
    await _register(client)
    group = await _create_sample_group(client)
    gid = group["id"]
    ts0 = group["updated_at"]

    # Add student: trims whitespace, fills missing column keys with "", position = max + 1 (2)
    add_resp = await client.post(
        f"/api/groups/{gid}/students",
        json={"data": {"c1": "  Каримова Дилноза  ", "c2": " 24003 "}},
    )
    assert add_resp.status_code == 200
    added = add_resp.json()
    assert added["position"] == 2
    assert added["data"] == {
        "c1": "Каримова Дилноза",
        "c2": "24003",
        "c3": "",
    }
    sid = added["id"]

    g_after_add = (await client.get(f"/api/groups/{gid}")).json()
    ts1 = g_after_add["updated_at"]
    assert ts1 > ts0

    # Patch student cell
    patch_resp = await client.patch(
        f"/api/groups/{gid}/students/{sid}",
        json={"key": "c3", "value": "  отличница  "},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["data"]["c3"] == "отличница"
    assert patched["data"]["c1"] == "Каримова Дилноза"

    g_after_patch = (await client.get(f"/api/groups/{gid}")).json()
    ts2 = g_after_patch["updated_at"]
    assert ts2 > ts1

    # Delete student -> 204
    del_resp = await client.delete(f"/api/groups/{gid}/students/{sid}")
    assert del_resp.status_code == 204

    g_after_del = (await client.get(f"/api/groups/{gid}")).json()
    ts3 = g_after_del["updated_at"]
    assert ts3 > ts2
    assert len(g_after_del["students"]) == 2

    # Deleting again gives 404 student_not_found
    del_again = await client.delete(f"/api/groups/{gid}/students/{sid}")
    assert del_again.status_code == 404
    assert del_again.json()["error"]["code"] == "student_not_found"


async def test_student_validation_and_cross_group_errors(
    client: AsyncClient,
) -> None:
    await _register(client)
    g1 = await _create_sample_group(client, number="101")
    g2 = await _create_sample_group(client, number="102")
    g1_id = g1["id"]
    g2_student_id = g2["students"][0]["id"]

    # Unknown column key on POST /students -> 422 invalid_columns
    bad_key_add = await client.post(
        f"/api/groups/{g1_id}/students",
        json={"data": {"c99": "Значение"}},
    )
    assert bad_key_add.status_code == 422
    assert bad_key_add.json()["error"]["code"] == "invalid_columns"

    # Empty student (all values blank/whitespace) -> 422 student_empty
    empty_add = await client.post(
        f"/api/groups/{g1_id}/students",
        json={"data": {"c1": "   ", "c2": ""}},
    )
    assert empty_add.status_code == 422
    assert empty_add.json()["error"]["code"] == "student_empty"

    # Value longer than 500 chars -> 422 validation_error
    too_long_add = await client.post(
        f"/api/groups/{g1_id}/students",
        json={"data": {"c1": "а" * 501}},
    )
    assert too_long_add.status_code == 422
    assert too_long_add.json()["error"]["code"] == "validation_error"

    # Unknown column key on PATCH /students/{sid} -> 422 invalid_columns
    g1_student_id = g1["students"][0]["id"]
    bad_key_patch = await client.patch(
        f"/api/groups/{g1_id}/students/{g1_student_id}",
        json={"key": "unknown_col", "value": "Тест"},
    )
    assert bad_key_patch.status_code == 422
    assert bad_key_patch.json()["error"]["code"] == "invalid_columns"

    # Student from another group of the same teacher -> 404 student_not_found
    cross_patch = await client.patch(
        f"/api/groups/{g1_id}/students/{g2_student_id}",
        json={"key": "c1", "value": "Чужая группа"},
    )
    assert cross_patch.status_code == 404
    assert cross_patch.json()["error"]["code"] == "student_not_found"

    cross_del = await client.delete(
        f"/api/groups/{g1_id}/students/{g2_student_id}"
    )
    assert cross_del.status_code == 404
    assert cross_del.json()["error"]["code"] == "student_not_found"


async def test_delete_column_and_last_column_protection(
    client: AsyncClient,
) -> None:
    await _register(client)
    group = await _create_sample_group(
        client,
        rows=[
            ["ФИО", "Телефон"],
            ["Иванов И.", "900111222"],
            ["Петров П.", "900333444"],
        ],
    )
    gid = group["id"]
    ts0 = group["updated_at"]

    # Unknown column -> 404 column_not_found
    not_found = await client.delete(f"/api/groups/{gid}/columns/c99")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "column_not_found"

    # Delete column c2 ("Телефон")
    del_col = await client.delete(f"/api/groups/{gid}/columns/c2")
    assert del_col.status_code == 200
    updated = del_col.json()
    assert updated["updated_at"] > ts0
    assert updated["columns"] == [{"key": "c1", "title": "ФИО"}]
    for student in updated["students"]:
        assert "c2" not in student["data"]
        assert "c1" in student["data"]

    # Verify via fresh GET that JSONB changes persisted in DB
    fresh = (await client.get(f"/api/groups/{gid}")).json()
    assert fresh["columns"] == [{"key": "c1", "title": "ФИО"}]
    for student in fresh["students"]:
        assert "c2" not in student["data"]

    # Attempting to delete the last remaining column -> 409 cannot_delete_last_column
    last_col = await client.delete(f"/api/groups/{gid}/columns/c1")
    assert last_col.status_code == 409
    assert last_col.json()["error"]["code"] == "cannot_delete_last_column"


async def test_search_students_via_api(client: AsyncClient) -> None:
    await _register(client)
    group = await _create_sample_group(
        client,
        rows=[
            ["ФИО", "Зачётка"],
            ["Иванов Иван", "24001"],
            ["Семёнов Пётр", "24002"],
            ["Абдуллоев Фарход", "24003"],
        ],
    )
    gid = group["id"]

    # Empty q returns all
    all_resp = await client.get(f"/api/groups/{gid}/students")
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 3

    # Case + space insensitive
    q1 = await client.get(
        f"/api/groups/{gid}/students",
        params={"q": "ивановиван"},
    )
    assert q1.status_code == 200
    assert [s["data"]["c1"] for s in q1.json()] == ["Иванов Иван"]

    # Yo / Ye equivalence
    q2 = await client.get(
        f"/api/groups/{gid}/students",
        params={"q": "семенов петр"},
    )
    assert q2.status_code == 200
    assert [s["data"]["c1"] for s in q2.json()] == ["Семёнов Пётр"]

    # Fuzzy typo match
    q3 = await client.get(
        f"/api/groups/{gid}/students",
        params={"q": "Абдулоев"},
    )
    assert q3.status_code == 200
    assert [s["data"]["c1"] for s in q3.json()] == ["Абдуллоев Фарход"]


async def test_export_group_to_excel_and_formula_safety(
    client: AsyncClient,
) -> None:
    await _register(client)
    group = await _create_sample_group(
        client,
        number="205/Б: Поток",
        rows=[
            ["Удаляемая", "ФИО", "Формула"],
            ["х", "Иванов И.", "текст"],
            ["у", "+SUM(A1:A2)", "-100@test"],
        ],
    )
    gid = group["id"]
    first_sid = group["students"][0]["id"]

    # Set formula-like value "=1+1" via PATCH
    patch_formula = await client.patch(
        f"/api/groups/{gid}/students/{first_sid}",
        json={"key": "c3", "value": "=1+1"},
    )
    assert patch_formula.status_code == 200

    # Delete first column (c1) and reorder remaining [c3, c2]
    await client.delete(f"/api/groups/{gid}/columns/c1")
    await client.patch(
        f"/api/groups/{gid}",
        json={"columns_order": ["c3", "c2"]},
    )

    resp = await client.get(f"/api/groups/{gid}/export")
    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    content_disp = resp.headers["content-disposition"]
    assert "filename*=" in content_disp
    assert "%D0%9F%D0%BE%D1%82%D0%BE%D0%BA" in content_disp

    wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=False)
    ws = wb.active
    assert ws is not None

    # Header row: bold, only remaining columns in current order ["Формула", "ФИО"]
    assert ws.max_column == 2
    assert ws.max_row == 3
    assert ws.cell(1, 1).value == "Формула"
    assert ws.cell(1, 2).value == "ФИО"
    assert ws.cell(1, 1).font.bold is True
    assert ws.cell(1, 2).font.bold is True

    # Data cells: formula-like strings are stored as plain text ('s'), not formula ('f')
    c_formula = ws.cell(2, 1)
    assert c_formula.value == "=1+1"
    assert c_formula.data_type == "s"

    assert ws.cell(2, 2).value == "Иванов И."
    assert ws.cell(2, 2).data_type == "s"

    assert ws.cell(3, 1).value == "-100@test"
    assert ws.cell(3, 1).data_type == "s"
    assert ws.cell(3, 2).value == "+SUM(A1:A2)"
    assert ws.cell(3, 2).data_type == "s"


async def test_isolation_between_teachers_for_stage_4b_endpoints(
    client: AsyncClient,
) -> None:
    await _register(client, email="teacher_a@example.com")
    group_a = await _create_sample_group(client, number="А-101")
    gid_a = group_a["id"]
    sid_a = group_a["students"][0]["id"]

    # Register Teacher B
    await _register(client, email="teacher_b@example.com")

    # GET /students
    r_search = await client.get(f"/api/groups/{gid_a}/students?q=Иванов")
    assert r_search.status_code == 404
    assert r_search.json()["error"]["code"] == "group_not_found"

    # POST /students
    r_add = await client.post(
        f"/api/groups/{gid_a}/students",
        json={"data": {"c1": "Хакер"}},
    )
    assert r_add.status_code == 404
    assert r_add.json()["error"]["code"] == "group_not_found"

    # PATCH /students/{sid}
    r_patch = await client.patch(
        f"/api/groups/{gid_a}/students/{sid_a}",
        json={"key": "c1", "value": "Хакер"},
    )
    assert r_patch.status_code == 404
    assert r_patch.json()["error"]["code"] == "group_not_found"

    # DELETE /students/{sid}
    r_del_s = await client.delete(f"/api/groups/{gid_a}/students/{sid_a}")
    assert r_del_s.status_code == 404
    assert r_del_s.json()["error"]["code"] == "group_not_found"

    # DELETE /columns/{key}
    r_del_col = await client.delete(f"/api/groups/{gid_a}/columns/c1")
    assert r_del_col.status_code == 404
    assert r_del_col.json()["error"]["code"] == "group_not_found"

    # GET /export
    r_export = await client.get(f"/api/groups/{gid_a}/export")
    assert r_export.status_code == 404
    assert r_export.json()["error"]["code"] == "group_not_found"

    # Verify Teacher A's data is unchanged
    await _login(client, email="teacher_a@example.com")
    check_a = (await client.get(f"/api/groups/{gid_a}")).json()
    assert len(check_a["columns"]) == 3
    assert len(check_a["students"]) == 2
    assert check_a["students"][0]["data"]["c1"] == "Иванов Иван"
