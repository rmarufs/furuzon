import io
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.storage.local import LocalStorage
from tests.conftest import FakeStorage


def _make_xlsx_bytes(rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_pdf_bytes(text: str = "Hello Furuzon") -> bytes:
    return f"%PDF-1.4\n1 0 obj\n<< /Text ({text}) >>\nendobj\n%%EOF\n".encode()


def _make_doc_bytes() -> bytes:
    return bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512


def _make_docx_bytes(text: str = "Lecture notes") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types></Types>',
        )
        zf.writestr(
            "word/document.xml",
            f"<w:document><w:body><w:p>{text}</w:p></w:body></w:document>",
        )
    return buf.getvalue()


async def _register(
    client: AsyncClient,
    email: str = "teacher@example.com",
    password: str = "password123",
    first_name: str = "Иван",
    last_name: str = "Петров",
) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
        },
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


async def _create_group(
    client: AsyncClient,
    number: str,
    course: int,
) -> int:
    xlsx_data = _make_xlsx_bytes([["ФИО"], ["Раҳмонов А."]])
    resp = await client.post(
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
            "number": number,
            "course": str(course),
        },
    )
    assert resp.status_code == 200
    return int(resp.json()["id"])


async def test_materials_endpoints_require_authentication(
    client: AsyncClient,
) -> None:
    pdf_data = _make_pdf_bytes()

    r_tree = await client.get("/api/materials/tree")
    assert r_tree.status_code == 401
    assert r_tree.json()["error"]["code"] == "not_authenticated"

    r_upload = await client.post(
        "/api/materials",
        files={"file": ("lecture.pdf", pdf_data, "application/pdf")},
        data={"course": "1", "group_ids": "[1]"},
    )
    assert r_upload.status_code == 401

    r_replace = await client.put(
        "/api/materials/1/file",
        files={"file": ("lecture.pdf", pdf_data, "application/pdf")},
    )
    assert r_replace.status_code == 401

    r_del = await client.delete("/api/materials/1")
    assert r_del.status_code == 401

    r_unlink = await client.delete("/api/materials/1/groups/1")
    assert r_unlink.status_code == 401

    r_qr = await client.get("/api/materials/1/qr.svg")
    assert r_qr.status_code == 401

    r_act = await client.get("/api/activity")
    assert r_act.status_code == 401


async def test_material_upload_validation_and_tree(
    client: AsyncClient,
    fake_storage: FakeStorage,
) -> None:
    await _register(client)
    g1 = await _create_group(client, "ИС-11", 1)
    g2 = await _create_group(client, "ИС-12", 1)
    g_course2 = await _create_group(client, "ИС-21", 2)

    # Wrong extension -> 415 invalid_file_type
    r_ext = await client.post(
        "/api/materials",
        files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_ext.status_code == 415
    assert r_ext.json()["error"]["code"] == "invalid_file_type"

    # Spoofed extension (.pdf with non-PDF bytes) -> 415 invalid_file_type
    r_spoof_pdf = await client.post(
        "/api/materials",
        files={"file": ("fake.pdf", b"not a pdf file", "application/pdf")},
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_spoof_pdf.status_code == 415
    assert r_spoof_pdf.json()["error"]["code"] == "invalid_file_type"

    # Spoofed .docx (xlsx bytes renamed to .docx, no word/document.xml) -> 415
    r_spoof_docx = await client.post(
        "/api/materials",
        files={
            "file": (
                "fake.docx",
                _make_xlsx_bytes([["A"]]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_spoof_docx.status_code == 415
    assert r_spoof_docx.json()["error"]["code"] == "invalid_file_type"

    # File > 10 MB -> 413 file_too_large
    big_pdf = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 10)
    r_big = await client.post(
        "/api/materials",
        files={"file": ("huge.pdf", big_pdf, "application/pdf")},
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_big.status_code == 413
    assert r_big.json()["error"]["code"] == "file_too_large"

    # Group from another course -> 422 validation_error
    r_wrong_course = await client.post(
        "/api/materials",
        files={"file": ("lec.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"course": "1", "group_ids": f"[{g_course2}]"},
    )
    assert r_wrong_course.status_code == 422
    assert r_wrong_course.json()["error"]["code"] == "validation_error"

    # Valid PDF upload linked to two groups on course 1 (one stored object)
    pdf_bytes = _make_pdf_bytes("Lecture 1")
    r_ok = await client.post(
        "/api/materials",
        files={
            "file": (
                "Лекция №1 (Ғафуров).pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
        data={"course": "1", "group_ids": [str(g1), str(g2)]},
    )
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["original_name"] == "Лекция №1 (Ғафуров).pdf"
    assert body["course"] == 1
    assert body["group_ids"] == sorted([g1, g2])
    assert body["public_token"]
    assert body["public_url"].endswith(f"/f/{body['public_token']}")
    assert len(fake_storage.files) == 1
    stored_key = next(iter(fake_storage.files.keys()))
    assert stored_key.endswith(".pdf")
    assert "Лекция" not in stored_key

    # Valid DOC and DOCX uploads
    r_doc = await client.post(
        "/api/materials",
        files={"file": ("old.doc", _make_doc_bytes(), "application/msword")},
        data={"course": "2", "group_ids": f"[{g_course2}]"},
    )
    assert r_doc.status_code == 200

    r_docx = await client.post(
        "/api/materials",
        files={
            "file": (
                "modern.docx",
                _make_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"course": "2", "group_ids": f"[{g_course2}]"},
    )
    assert r_docx.status_code == 200
    assert len(fake_storage.files) == 3

    # Check tree structure
    r_tree = await client.get("/api/materials/tree")
    assert r_tree.status_code == 200
    tree = r_tree.json()
    assert len(tree["courses"]) == 6
    c1 = next(c for c in tree["courses"] if c["course"] == 1)
    assert len(c1["groups"]) == 2
    assert len(c1["groups"][0]["files"]) == 1
    assert len(c1["groups"][1]["files"]) == 1
    assert c1["groups"][0]["files"][0]["id"] == body["id"]


async def test_material_isolation_between_teachers(
    client: AsyncClient,
) -> None:
    await _register(client, email="t1@example.com")
    g1 = await _create_group(client, "101", 1)
    r_up = await client.post(
        "/api/materials",
        files={"file": ("t1.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_up.status_code == 200
    mat_id = r_up.json()["id"]

    await client.post("/api/auth/logout")
    await _register(client, email="t2@example.com")
    g2 = await _create_group(client, "102", 1)

    # Teacher 2 cannot upload to Teacher 1's group -> 404 group_not_found
    r_foreign_grp = await client.post(
        "/api/materials",
        files={"file": ("t2.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"course": "1", "group_ids": f"[{g1}]"},
    )
    assert r_foreign_grp.status_code == 404
    assert r_foreign_grp.json()["error"]["code"] == "group_not_found"

    # Teacher 2 tree does not include Teacher 1's groups or files
    r_tree = await client.get("/api/materials/tree")
    c1 = next(c for c in r_tree.json()["courses"] if c["course"] == 1)
    assert [g["id"] for g in c1["groups"]] == [g2]
    assert c1["groups"][0]["files"] == []

    # Teacher 2 cannot access QR, replace, unlink, or delete Teacher 1's material -> 404
    assert (await client.get(f"/api/materials/{mat_id}/qr.svg")).status_code == 404
    assert (
        await client.put(
            f"/api/materials/{mat_id}/file",
            files={"file": ("new.pdf", _make_pdf_bytes(), "application/pdf")},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/materials/{mat_id}/groups/{g1}")
    ).status_code == 404
    assert (await client.delete(f"/api/materials/{mat_id}")).status_code == 404


async def test_material_cascade_and_unlink_rules(
    client: AsyncClient,
    fake_storage: FakeStorage,
) -> None:
    await _register(client)
    g1 = await _create_group(client, "201", 2)
    g2 = await _create_group(client, "202", 2)
    g3 = await _create_group(client, "203", 2)

    r_up = await client.post(
        "/api/materials",
        files={"file": ("shared.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"course": "2", "group_ids": [str(g1), str(g2), str(g3)]},
    )
    assert r_up.status_code == 200
    mat_id = r_up.json()["id"]
    token = r_up.json()["public_token"]
    assert len(fake_storage.files) == 1

    # 1. Remove from g1 -> still linked to g2 and g3, file remains
    r_unlink1 = await client.delete(f"/api/materials/{mat_id}/groups/{g1}")
    assert r_unlink1.status_code == 200
    assert len(fake_storage.files) == 1
    assert (await client.get(f"/f/{token}")).status_code == 200

    # 2. Delete group g2 -> still linked to g3, file remains
    r_del_g2 = await client.delete(f"/api/groups/{g2}")
    assert r_del_g2.status_code == 200
    assert len(fake_storage.files) == 1
    assert (await client.get(f"/f/{token}")).status_code == 200

    # 3. Delete last remaining group g3 -> orphan file is deleted from DB and storage
    r_del_g3 = await client.delete(f"/api/groups/{g3}")
    assert r_del_g3.status_code == 200
    assert len(fake_storage.files) == 0
    assert (await client.get(f"/f/{token}")).status_code == 404

    # 4. Upload to a single group and unlink from that last group -> deleted completely
    g4 = await _create_group(client, "204", 2)
    r_up2 = await client.post(
        "/api/materials",
        files={"file": ("single.pdf", _make_pdf_bytes(), "application/pdf")},
        data={"course": "2", "group_ids": [str(g4)]},
    )
    mat2_id = r_up2.json()["id"]
    token2 = r_up2.json()["public_token"]
    assert len(fake_storage.files) == 1

    r_unlink_last = await client.delete(f"/api/materials/{mat2_id}/groups/{g4}")
    assert r_unlink_last.status_code == 200
    assert len(fake_storage.files) == 0
    assert (await client.get(f"/f/{token2}")).status_code == 404


async def test_replace_material_invalidates_old_token_and_deletes_old_object(
    client: AsyncClient,
    fake_storage: FakeStorage,
) -> None:
    await _register(client)
    g1 = await _create_group(client, "301", 3)

    r_up = await client.post(
        "/api/materials",
        files={"file": ("v1.pdf", _make_pdf_bytes("v1"), "application/pdf")},
        data={"course": "3", "group_ids": [str(g1)]},
    )
    assert r_up.status_code == 200
    mat_id = r_up.json()["id"]
    old_token = r_up.json()["public_token"]
    old_key = next(iter(fake_storage.files.keys()))

    new_docx = _make_docx_bytes("v2 updated")
    r_rep = await client.put(
        f"/api/materials/{mat_id}/file",
        files={
            "file": (
                "Конспект_v2.docx",
                new_docx,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert r_rep.status_code == 200
    new_body = r_rep.json()
    new_token = new_body["public_token"]
    assert new_token != old_token
    assert new_body["original_name"] == "Конспект_v2.docx"
    assert old_key not in fake_storage.files
    assert len(fake_storage.files) == 1

    # Old link returns 404, new link downloads new content
    r_old = await client.get(f"/f/{old_token}")
    assert r_old.status_code == 404

    r_new = await client.get(f"/f/{new_token}")
    assert r_new.status_code == 200
    assert r_new.content == new_docx


async def test_public_download_qr_and_bilingual_404(
    client: AsyncClient,
) -> None:
    await _register(client)
    g1 = await _create_group(client, "401", 4)

    pdf_bytes = _make_pdf_bytes("Public test")
    r_up = await client.post(
        "/api/materials",
        files={
            "file": (
                "Методичка по физике.pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
        data={"course": "4", "group_ids": [str(g1)]},
    )
    assert r_up.status_code == 200
    mat_id = r_up.json()["id"]
    token = r_up.json()["public_token"]

    # QR SVG endpoint
    r_qr = await client.get(f"/api/materials/{mat_id}/qr.svg")
    assert r_qr.status_code == 200
    assert "image/svg+xml" in r_qr.headers["content-type"]
    assert b"<svg" in r_qr.content

    # Unauthenticated student download via /f/{token}
    await client.post("/api/auth/logout")
    r_dl = await client.get(f"/f/{token}")
    assert r_dl.status_code == 200
    assert r_dl.content == pdf_bytes
    assert r_dl.headers["x-content-type-options"] == "nosniff"
    cd = r_dl.headers["content-disposition"]
    assert cd.startswith("attachment;")
    assert "filename*=UTF-8''" in cd
    assert "%D0%9C%D0%B5%D1%82%D0%BE%D0%B4%D0%B8%D1%87%D0%BA%D0%B0" in cd

    # Unknown token -> 404 HTML with both Russian and Tajik messages
    r_missing = await client.get("/f/nonexistent-token-12345")
    assert r_missing.status_code == 404
    assert "text/html" in r_missing.headers["content-type"]
    html = r_missing.text
    assert "Файл не найден" in html
    assert "Файл ёфт нашуд" in html


async def test_activity_recording_and_deduplication(
    client: AsyncClient,
) -> None:
    await _register(client)
    g1 = await _create_group(client, "ИС-51", 5)

    # Viewing group page twice collapses into 1 activity record (DEF-2)
    await client.get(f"/groups/{g1}")
    await client.get(f"/groups/{g1}")

    r_act1 = await client.get("/api/activity")
    assert r_act1.status_code == 200
    items1 = r_act1.json()
    assert len(items1) == 1
    assert items1[0]["type"] == "group_viewed"
    assert items1[0]["object_id"] == g1
    assert items1[0]["object_title"] == "ИС-51"

    # Upload file and replace it -> 1 file_uploaded record for this file
    r_up = await client.post(
        "/api/materials",
        files={"file": ("plan.pdf", _make_pdf_bytes("1"), "application/pdf")},
        data={"course": "5", "group_ids": [str(g1)]},
    )
    mat_id = r_up.json()["id"]
    await client.put(
        f"/api/materials/{mat_id}/file",
        files={
            "file": ("plan_updated.pdf", _make_pdf_bytes("2"), "application/pdf")
        },
    )

    r_act2 = await client.get("/api/activity")
    items2 = r_act2.json()
    assert len(items2) == 2
    assert items2[0]["type"] == "file_uploaded"
    assert items2[0]["object_id"] == mat_id
    assert items2[0]["object_title"] == "plan_updated.pdf"

    # Delete file -> adds file_deleted
    await client.delete(f"/api/materials/{mat_id}")
    r_act3 = await client.get("/api/activity")
    items3 = r_act3.json()
    assert items3[0]["type"] == "file_deleted"
    assert items3[0]["object_title"] == "plan_updated.pdf"

    # Deleting the group removes group_viewed activity for that group
    await client.delete(f"/api/groups/{g1}")
    r_act4 = await client.get("/api/activity")
    items4 = r_act4.json()
    assert all(
        not (item["object_type"] == "group" and item["object_id"] == g1)
        for item in items4
    )


async def test_local_storage_adapter(tmp_path: Path) -> None:
    nested_dir = tmp_path / "missing_uploads_dir"
    storage = LocalStorage(base_dir=nested_dir)
    key = "abcd1234.pdf"
    payload = _make_pdf_bytes("local")

    assert not nested_dir.exists()
    assert not await storage.exists(key)
    await storage.save(key, payload, "application/pdf")
    assert nested_dir.is_dir()
    assert await storage.exists(key)
    assert await storage.read(key) == payload

    await storage.delete(key)
    assert not await storage.exists(key)

    # Settings starts with local storage without SUPABASE_* and fails fast on supabase without keys
    s_local = Settings(STORAGE_BACKEND="local", SUPABASE_URL="", SUPABASE_SERVICE_KEY="")
    assert s_local.STORAGE_BACKEND == "local"
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings(STORAGE_BACKEND="supabase", SUPABASE_URL="", SUPABASE_SERVICE_KEY="")
