"""Свои данные: выгрузка и удаление учётной записи (ADMIN-DECOMPOSITION.md, C3, 152-ФЗ).

Два права человека, которых у платформы не было вовсе: забрать то, что о нём хранится, и
уйти. Тесты здесь больше про **границы**, чем про механику: что в выгрузку не попадает,
чего удаление не стирает и почему, и где оно отказывает, называя выход.
"""
from __future__ import annotations

import json
from pathlib import Path

from app import crud
from app.db_models import AuditLogEntry, Organization, Project, User
from app.personal_data import build_export, deletion_plan


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _member(client, owner, email="k@e.ru", role="editor") -> dict:
    org = _org_id(client, owner)
    return client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": email, "full_name": "Коллега", "role": role},
                       headers=owner).json()


def _activate(client, invite: dict, password="kollega-parol7") -> dict:
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Выгрузка ---

def test_export_gives_the_person_what_is_stored_about_them(client, register, db_session):
    headers = register()
    client.get("/api/v1/projects", headers=headers)          # отметка присутствия

    r = client.get("/api/v1/auth/export", headers=headers)
    assert r.status_code == 200
    data = json.loads(r.content.decode("utf-8"))
    assert data["учётная_запись"]["адрес"] == "owner@e.ru"
    assert data["организации"][0]["роль"] == "owner"
    assert data["входы"] and data["входы"][0]["устройство"] is not None
    assert any(a["действие"] == "org.create" for a in data["мои_действия"])


def test_export_does_not_carry_the_company_models(client, register):
    """Проекты и дела принадлежат организации, а не сотруднику.

    Отдать их «по запросу субъекта персональных данных» значило бы выдать уходящему
    модели работодателя под видом личного права. Имя проекта в записи журнала при этом
    остаётся: это след **его собственного** действия, и ничего, чего он не видел, оно
    ему не открывает.
    """
    headers = register()
    model = client.get("/api/v1/sample").json()
    client.post("/api/v1/projects", json={"name": "Покупка завода в Твери", "model": model},
                headers=headers)

    data = json.loads(client.get("/api/v1/auth/export",
                                 headers=headers).content.decode("utf-8"))
    assert set(data) == {"о_выгрузке", "учётная_запись", "организации", "входы",
                         "мои_действия"}
    body = json.dumps(data, ensure_ascii=False)
    assert "sales" not in body and "discount_rate" not in body
    # И в файле сказано, почему моделей там нет, — оговорку приложить больше будет негде.
    assert "принадлежат организациям" in body


def test_export_stays_inside_the_organizations_the_person_is_in(client, register,
                                                                db_session):
    """Журнал читается через ту же дверь арендатора, что и всё остальное: в организации,
    которую человек покинул, его записи остались у неё — и файл об этом говорит."""
    owner = register()
    org = _org_id(client, owner)
    invite = _member(client, owner)
    colleague = _activate(client, invite)
    client.post("/api/v1/projects", json={"name": "Чужой проект", "model":
                client.get("/api/v1/sample").json()}, headers=colleague)

    left = json.loads(client.get("/api/v1/auth/export",
                                 headers=colleague).content.decode("utf-8"))
    assert any(a["действие"] == "project.create" for a in left["мои_действия"])
    assert all(a["организация"] == "Орг" for a in left["мои_действия"])

    client.delete(f"/api/v1/organizations/{org}/members/{invite['user_id']}",
                  headers=owner)
    after = json.loads(client.get("/api/v1/auth/export",
                                  headers=colleague).content.decode("utf-8"))
    assert after["мои_действия"] == [] and after["организации"] == []
    assert any("покинули" in note for note in after["о_выгрузке"]["что_внутри"])
    # А у организации они остались: журнал принадлежит ей.
    assert db_session.query(AuditLogEntry).filter_by(organization_id=org).count() > 0


def test_export_does_not_carry_the_second_factor_secret(client, register, db_session):
    """Это ключ от учётной записи, а не сведения о человеке: файл, который кладут в
    почту и в облако, — не место для ключа."""
    headers = register()
    secret = client.post("/api/v1/auth/totp/setup", headers=headers).json()["secret"]
    body = client.get("/api/v1/auth/export", headers=headers).content.decode("utf-8")
    assert secret not in body
    assert "второй_фактор" in body                 # сам факт настройки — сказан


def test_export_names_its_own_truncation(client, register, db_session, monkeypatch):
    """Молча обрезанный файл выглядит как полный."""
    import app.personal_data as pd
    monkeypatch.setattr(pd, "MAX_EXPORT_LOG", 1)
    headers = register()
    for i in range(3):
        client.post("/api/v1/projects", json={"name": f"П{i}", "model":
                    client.get("/api/v1/sample").json()}, headers=headers)

    user = crud.get_user_by_email(db_session, "owner@e.ru")
    payload = build_export(db_session, user)
    assert len(payload["мои_действия"]) == 1
    assert any("вошли последние" in note for note in payload["о_выгрузке"]["что_внутри"])


def test_export_is_written_to_the_journal(client, register):
    """Вынос данных наружу — событие (правило 5 пакета)."""
    headers = register()
    org = _org_id(client, headers)
    client.get("/api/v1/auth/export", headers=headers)
    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=headers).json()["entries"]}
    assert "user.data_export" in actions


def test_export_needs_a_session(client):
    assert client.get("/api/v1/auth/export").status_code == 401


# --- План удаления ---

def test_plan_says_what_disappears_before_it_disappears(client, register):
    headers = register()
    client.post("/api/v1/projects", json={"name": "П", "model":
                client.get("/api/v1/sample").json()}, headers=headers)

    plan = client.get("/api/v1/auth/delete-preview", headers=headers).json()
    assert plan["allowed"] is True
    assert plan["organizations_deleted"] == ["Орг"]
    assert plan["projects"] == 1
    # И что останется — тоже: обещать «полное удаление», оставляя журнал, было бы неправдой.
    assert any("журнал" in k.lower() for k in plan["kept"])


def test_owner_of_a_populated_organization_is_refused_with_a_way_out(client, register):
    """Организация без владельца — компания без того, кто платит за тариф и управляет
    доступом. Отказ называет выход, а не просто запрещает."""
    owner = register()
    _member(client, owner)

    plan = client.get("/api/v1/auth/delete-preview", headers=owner).json()
    assert plan["allowed"] is False
    assert any("Передайте владение" in b for b in plan["blockers"])

    refused = client.post("/api/v1/auth/delete", json={"password": "secret123"},
                          headers=owner)
    assert refused.status_code == 409 and "Передайте владение" in refused.json()["detail"]


def test_member_just_leaves_and_the_organization_stays(client, register, db_session):
    owner = register()
    org = _org_id(client, owner)
    colleague = _activate(client, _member(client, owner))

    plan = client.get("/api/v1/auth/delete-preview", headers=colleague).json()
    assert plan["allowed"] is True
    assert plan["organizations_deleted"] == [] and plan["organizations_left"] == ["Орг"]

    client.post("/api/v1/auth/delete", json={"password": "kollega-parol7"},
                headers=colleague)
    assert db_session.get(Organization, org) is not None
    assert crud.count_members(db_session, org) == 1


# --- Удаление ---

def test_deletion_requires_the_password(client, register):
    """Удаление — ровно то, что сделает дорвавшийся до открытой вкладки."""
    headers = register()
    assert client.post("/api/v1/auth/delete", json={"password": "не тот"},
                       headers=headers).status_code == 400


def test_deletion_erases_the_account_and_closes_the_way_back(client, register, db_session):
    headers = register()
    user_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]

    assert client.post("/api/v1/auth/delete", json={"password": "secret123"},
                       headers=headers).status_code == 200

    user = db_session.get(User, user_id)
    db_session.refresh(user)
    assert user.email != "owner@e.ru" and user.hashed_password is None
    assert client.post("/api/v1/auth/login",
                       json={"email": "owner@e.ru", "password": "secret123"}
                       ).status_code == 401
    # Выданный до удаления токен тоже мёртв: сеансы стёрты.
    assert client.get("/api/v1/projects", headers=headers).status_code in (401, 403)


def test_deletion_takes_the_solo_organization_with_all_its_data(client, register,
                                                                 db_session):
    headers = register()
    org = _org_id(client, headers)
    client.post("/api/v1/projects", json={"name": "П", "model":
                client.get("/api/v1/sample").json()}, headers=headers)
    client.post("/api/v1/audit/subjects",
                json={"name": "Дело", "model": {"name": "Дело", "periods": [], "lines": []}},
                headers=headers)

    client.post("/api/v1/auth/delete", json={"password": "secret123"}, headers=headers)

    assert db_session.get(Organization, org) is None
    assert db_session.query(Project).filter_by(organization_id=org).count() == 0
    # Журнал этой организации ушёл вместе с ней: он её собственность, а не платформы.
    assert db_session.query(AuditLogEntry).filter_by(organization_id=org).count() == 0


def test_journal_of_other_organizations_survives_the_deletion(client, register,
                                                               db_session):
    """Записи журнала принадлежат организациям, где человек работал, и отвечают на
    вопрос «кто это сделал» — ровно ради этого журнал и ведётся."""
    owner = register()
    org = _org_id(client, owner)
    colleague = _activate(client, _member(client, owner))
    client.post("/api/v1/projects", json={"name": "Чужой проект", "model":
                client.get("/api/v1/sample").json()}, headers=colleague)

    client.post("/api/v1/auth/delete", json={"password": "kollega-parol7"},
                headers=colleague)

    entries = client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=owner).json()["entries"]
    trace = [e for e in entries if e["actor_email"] == "k@e.ru"]
    # «Надгробие» почты осталось: журнал обязан отвечать «кто это сделал» и после ухода.
    assert trace and any(e["action"] == "project.create" for e in trace)


def test_deletion_is_written_before_it_happens(client, register):
    """Событие пишется в журналы организаций **до** удаления — после писать будет уже
    некуда."""
    owner = register()
    org = _org_id(client, owner)
    colleague = _activate(client, _member(client, owner))
    client.post("/api/v1/auth/delete", json={"password": "kollega-parol7"},
                headers=colleague)

    actions = {e["action"] for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=owner).json()["entries"]}
    assert "user.delete" in actions


def test_plan_of_a_deleted_account_is_not_reused(client, register, db_session):
    """Удаление идёт по свежему плану, а не по показанному раньше: между показом и
    нажатием состав организации мог измениться."""
    owner = register()
    user = crud.get_user_by_email(db_session, "owner@e.ru")
    assert deletion_plan(db_session, user).allowed is True
    _member(client, owner)                      # появился коллега — план изменился
    db_session.expire_all()
    assert deletion_plan(db_session, user).allowed is False


# --- Передача владения ---

def test_ownership_can_be_transferred_and_the_old_owner_stays(client, register):
    """Человек, отдавший компанию, чаще всего продолжает в ней работать: выкидывать его
    молча незачем."""
    owner = register()
    org = _org_id(client, owner)
    colleague = _member(client, owner)

    r = client.post(f"/api/v1/organizations/{org}/transfer-ownership",
                    json={"user_id": colleague["user_id"]}, headers=owner)
    assert r.status_code == 200
    roles = {m["email"]: m["role"] for m in
             client.get(f"/api/v1/organizations/{org}/members", headers=owner).json()}
    assert roles["k@e.ru"] == "owner" and roles["owner@e.ru"] == "admin"


def test_transfer_unblocks_the_deletion(client, register):
    """Ради этого передача и появилась: без неё владелец не мог воспользоваться правом
    уйти."""
    owner = register()
    org = _org_id(client, owner)
    colleague = _member(client, owner)
    assert client.get("/api/v1/auth/delete-preview",
                      headers=owner).json()["allowed"] is False

    client.post(f"/api/v1/organizations/{org}/transfer-ownership",
                json={"user_id": colleague["user_id"]}, headers=owner)
    assert client.get("/api/v1/auth/delete-preview",
                      headers=owner).json()["allowed"] is True


def test_transfer_is_refused_to_a_suspended_member(client, register):
    """Отдать организацию тому, кому сами же закрыли доступ, — это организация без
    работающего владельца."""
    owner = register()
    org = _org_id(client, owner)
    colleague = _member(client, owner)
    client.post(f"/api/v1/organizations/{org}/members/{colleague['user_id']}/block",
                json={"reason": "отпуск"}, headers=owner)

    r = client.post(f"/api/v1/organizations/{org}/transfer-ownership",
                    json={"user_id": colleague["user_id"]}, headers=owner)
    assert r.status_code == 409 and "доступ" in r.json()["detail"]


def test_only_the_owner_transfers_ownership(client, register):
    owner = register()
    org = _org_id(client, owner)
    admin = _activate(client, _member(client, owner, email="a@e.ru", role="admin"))
    stranger = _member(client, owner, email="s@e.ru")

    r = client.post(f"/api/v1/organizations/{org}/transfer-ownership",
                    json={"user_id": stranger["user_id"]}, headers=admin)
    assert r.status_code == 403


def test_transfer_is_written_to_the_journal(client, register):
    owner = register()
    org = _org_id(client, owner)
    invite = _member(client, owner)
    new_owner = _activate(client, invite)
    client.post(f"/api/v1/organizations/{org}/transfer-ownership",
                json={"user_id": invite["user_id"]}, headers=owner)

    # Журнал читает новый владелец: прежний стал администратором, и права на журнал
    # у него больше нет — это и есть переданное владение.
    entries = client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=new_owner).json()["entries"]
    transfer = next(e for e in entries if e["action"] == "org.transfer_ownership")
    assert "owner@e.ru" in transfer["details"] and "k@e.ru" in transfer["details"]


# --- Что код не делает ---

def test_the_journal_has_no_retention_job_in_the_code():
    """Срок хранения журнала — политика эксплуатации, а не логика приложения.

    Код, умеющий стирать записи по возрасту, не журнал охраняет, а себя: достаточно
    ошибки в сроке, и следов не останется ровно там, где они и нужны. Чистку старых
    записей делает тот, кто отвечает за базу, — по регламенту и с резервной копией.

    Единственное место, где записи исчезают из приложения, — удаление организации
    целиком вместе с ними: журнал принадлежит ей, и хранить его, когда хранить его
    больше некому, незачем.
    """
    app_dir = Path(__file__).resolve().parents[1] / "app"
    guilty = [
        f"{path.relative_to(app_dir)}:{no}"
        for path in sorted(app_dir.rglob("*.py"))
        for no, line in enumerate(path.read_text().splitlines(), 1)
        if "AuditLogEntry" in line and ("delete" in line or "expire" in line)
    ]
    assert guilty == [], "записи журнала где-то стираются адресно: " + ", ".join(guilty)


def test_deleting_one_organization_leaves_the_other_journals_alone(client, register,
                                                                   db_session):
    """Ограда предыдущего теста — поведением: журнал уходит только со своей организацией."""
    owner = register()
    mine = _org_id(client, owner)
    other = crud.create_organization(db_session, "Соседи")
    crud.log_action(db_session, other.id, None, "org.create")

    client.post("/api/v1/auth/delete", json={"password": "secret123"}, headers=owner)

    assert db_session.query(AuditLogEntry).filter_by(organization_id=mine).count() == 0
    assert db_session.query(AuditLogEntry).filter_by(organization_id=other.id).count() == 1
