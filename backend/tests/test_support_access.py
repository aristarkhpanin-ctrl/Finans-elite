"""Доступ поддержки к моделям клиента — по его гранту (ADMIN-PHASE-F, F4).

**Это единственное изменение правила 6 во всей фазе**, и оно принимается только целиком:
выдаёт клиент, срок ограничен сверху, каждое чтение пишется в журнал клиента, грант даёт
чтение и только чтение. Здесь проверяются все четыре ограничения — каждое **в обе
стороны**: без гранта не видно, по гранту видно; просроченный и отозванный не работают;
власть от гранта не выросла; журнал клиента наполняется построчно.

Слепоту маршрутов наблюдения (правило 6 там, где оно и было) стережёт
`test_admin_staff.py::test_operator_does_not_see_the_contents_of_models` — он остался на
месте и упадёт, если содержимое просочится в карточку клиента.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud, support_access
from app.db_models import STAFF_SUPPORT


def _staff(client, db_session, register, *, email="staff@e.ru", role=None) -> dict:
    headers = register(email=email, org=f"Платформа {email}")
    user = crud.get_user_by_email(db_session, email)
    kwargs = {"role": role} if role else {}
    crud.set_staff(db_session, user, is_staff=True, **kwargs)
    return headers


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _project(client, headers, name="Покупка завода в Твери") -> str:
    model = client.get("/api/v1/sample").json()
    model["header"]["name"] = name
    r = client.post("/api/v1/projects", json={"name": name, "model": model},
                    headers=headers)
    return r.json()["id"]


def _case(client, headers, name="Цель поглощения") -> str:
    r = client.post("/api/v1/audit/subjects", json={"name": name, "model": {
        "name": name, "periods": [], "lines": []}}, headers=headers)
    return r.json()["id"]


def _analyst(client, register, owner, org_id, email="analyst@e.ru") -> dict:
    """Участник без права `org.manage` — со своими заголовками в этой организации."""
    headers = register(email=email, org=f"Личная {email}")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": email, "full_name": "А", "role": "analyst"}, headers=owner)
    return {**headers, "X-Organization-Id": org_id}


def _grant(client, headers, org_id, hours=24, reason="не считается проект"):
    return client.post(f"/api/v1/organizations/{org_id}/support-access",
                       json={"hours": hours, "reason": reason}, headers=headers)


def _org_log(client, headers, org_id) -> list[dict]:
    return client.get(f"/api/v1/organizations/{org_id}/audit-log",
                      headers=headers).json()["entries"]


# --- 1. Без гранта не видно ничего, и отказ называет дорогу ---

def test_without_a_grant_the_model_is_closed(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)

    r = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}", headers=staff)
    assert r.status_code == 403


def test_without_a_grant_even_the_names_are_closed(client, register, db_session):
    """Название проекта само по себе коммерческая тайна — ради этого правило 6 и
    запрещало показывать имена сущностей в карточке клиента."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    _project(client, owner)

    r = client.get(f"/api/v1/admin/organizations/{org_id}/projects", headers=staff)
    assert r.status_code == 403
    assert "Покупка завода" not in r.text


def test_the_refusal_says_who_opens_the_door(client, register, db_session):
    """Отказ называет **не нехватку прав**, а недостающее действие клиента: иначе
    поддержка попросит выгрузку почтой — тем каналом, который продукт и заменяет."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)

    detail = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}",
                        headers=staff).json()["detail"]
    assert "доступ выдаёт сама организация" in detail.lower()
    assert "72" in detail


def test_the_card_names_the_reason_before_the_click(client, register, db_session):
    """Причина нужна оператору **до** нажатия, а не после 403."""
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    access = client.get(f"/api/v1/admin/organizations/{org_id}",
                        headers=staff).json()["access"]
    assert access["granted"] is False
    assert "доступ выдаёт сама организация" in access["reason"].lower()


# --- 2. По гранту видно ---

def test_a_granted_model_opens(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)

    body = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}",
                      headers=staff).json()
    assert body["name"] == "Покупка завода в Твери"
    assert body["model"]["header"]["name"] == "Покупка завода в Твери"


def test_a_granted_case_opens_too(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    sid = _case(client, owner)
    _grant(client, owner, org_id)

    body = client.get(f"/api/v1/admin/organizations/{org_id}/audit-subjects/{sid}",
                      headers=staff).json()
    assert body["name"] == "Цель поглощения"


def test_the_model_travels_with_the_basis_for_seeing_it(client, register, db_session):
    """Экран, открытый по ошибке, не должен выглядеть как обычная работа: с числами
    едет строка о том, кто и до какого часа открыл доступ."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id, reason="не считается проект")

    note = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}",
                      headers=staff).json()["note"]
    assert "client@e.ru" in note
    assert "не считается проект" in note
    assert "журнал организации" in note


def test_support_level_may_look_too(client, register, db_session):
    """Грант открывает **чтение**, а чтение — работа поддержки (F5): ради разбора
    обращения его и выдают. Требовать здесь оператора значило бы, что смотреть может
    только тот, кто может заблокировать."""
    support = _staff(client, db_session, register, email="s@e.ru", role=STAFF_SUPPORT)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)

    assert client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}",
                      headers=support).status_code == 200


def test_a_grant_of_one_organization_does_not_open_another(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, mine = _client_org(client, register)
    other, theirs = _client_org(client, register, email="alien@e.ru", org="Чужая")
    their_project = _project(client, other, name="Чужой проект")
    _grant(client, owner, mine)

    r = client.get(f"/api/v1/admin/organizations/{theirs}/projects/{their_project}",
                   headers=staff)
    assert r.status_code == 403 and "Чужой проект" not in r.text


def test_an_outsider_cannot_read_by_someone_elses_grant(client, register, auth_headers,
                                                        db_session):
    """Грант открывает дверь **служебного контура**, а не дверь вообще."""
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)

    assert client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}",
                      headers=auth_headers).status_code == 403


# --- 3. Срок и отзыв ---

def test_an_expired_grant_does_not_work(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)

    grant = crud.list_support_grants(db_session, org_id)[0]
    grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    r = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}", headers=staff)
    assert r.status_code == 403
    assert "истёк" in r.json()["detail"]


def test_a_revoked_grant_does_not_work(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)
    client.delete(f"/api/v1/organizations/{org_id}/support-access", headers=owner)

    r = client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}", headers=staff)
    assert r.status_code == 403
    assert "закрыл доступ" in r.json()["detail"]


def test_the_three_refusals_are_different(client, register, db_session):
    """«Не открывали», «истёк» и «закрыли» — разные утверждения. Свести их к одному
    значило бы отвечать «может быть, вы ошиблись» там, где клиент только что нажал
    «закрыть»."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    path = f"/api/v1/admin/organizations/{org_id}/projects/{pid}"

    never = client.get(path, headers=staff).json()["detail"]
    _grant(client, owner, org_id)
    client.delete(f"/api/v1/organizations/{org_id}/support-access", headers=owner)
    revoked = client.get(path, headers=staff).json()["detail"]
    _grant(client, owner, org_id)
    grant = crud.list_support_grants(db_session, org_id)[0]
    grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    expired = client.get(path, headers=staff).json()["detail"]

    assert len({never, revoked, expired}) == 3


def test_the_term_is_capped_and_the_cut_is_named(client, register, db_session):
    """«Бессрочный грант» это не грант. Обрезка не бывает молчаливой: экран показывал бы
    «до пятницы» там, где доступ кончится в среду."""
    owner, org_id = _client_org(client, register)
    body = _grant(client, owner, org_id, hours=720).json()

    granted = datetime.fromisoformat(body["current"]["expires_at"])
    created = datetime.fromisoformat(body["current"]["created_at"])
    assert (granted - created) <= timedelta(hours=support_access.MAX_GRANT_HOURS + 1)
    assert any("сокращён" in n for n in body["notes"])


def test_a_new_grant_closes_the_previous_one(client, register, db_session):
    """Два живых гранта означали бы, что «до какого часа открыто» зависит от того,
    какой из них посмотреть."""
    owner, org_id = _client_org(client, register)
    _grant(client, owner, org_id, hours=1)
    body = _grant(client, owner, org_id, hours=48).json()

    assert sum(1 for g in body["history"] if g["active"]) == 1


def test_a_closed_grant_stays_in_the_history(client, register, db_session):
    """«Нам никто не открывал» должно быть проверяемым утверждением, а не отсутствием
    записи."""
    owner, org_id = _client_org(client, register)
    _grant(client, owner, org_id)
    body = client.delete(f"/api/v1/organizations/{org_id}/support-access",
                         headers=owner).json()

    assert body["current"] is None
    assert len(body["history"]) == 1 and body["history"][0]["revoked_at"]


# --- 4. Кто открывает дверь ---

def test_the_platform_cannot_open_the_door_for_itself(client, register, db_session):
    """В этом весь смысл ограничения: правило 6 не отменено, у него появился ключ — и
    ключ у клиента. Служебных маршрутов, выдающих грант, нет вовсе."""
    from app.routers import admin

    paths = [r.path for r in admin.router.routes]
    assert not [p for p in paths if "support-access" in p]


def test_an_ordinary_member_cannot_open_the_door(client, register, db_session):
    """Доступ к моделям организации — решение того, кто за организацию отвечает."""
    owner, org_id = _client_org(client, register)
    analyst = _analyst(client, register, owner, org_id)

    assert _grant(client, analyst, org_id).status_code == 403


def test_every_member_sees_whether_the_door_is_open(client, register, db_session):
    """«Кто пустил платформу в наши числа» — вопрос, на который сотрудник вправе
    получить ответ, не спрашивая администратора."""
    owner, org_id = _client_org(client, register)
    analyst = _analyst(client, register, owner, org_id)
    _grant(client, owner, org_id)

    body = client.get(f"/api/v1/organizations/{org_id}/support-access",
                      headers=analyst).json()
    assert body["current"]["granted_by_email"] == "client@e.ru"


def test_the_scope_of_the_grant_is_stated_where_it_is_given(client, register, db_session):
    """Грант — **на организацию**, а не на проект. Сузить его платформа не умеет, и
    делать вид, что умеет, хуже: клиент должен знать, что открывает всё."""
    owner, org_id = _client_org(client, register)
    notes = " ".join(_grant(client, owner, org_id).json()["notes"])

    assert "всем" in notes and "журнал" in notes
    assert "только смотреть" in notes


# --- 5. Каждое чтение — в журнал клиента ---

def test_every_read_lands_in_the_clients_journal(client, register, db_session):
    """Приход постороннего в свои числа клиент обязан видеть **построчно**, а не одной
    записью «доступ выдан»."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)

    for _ in range(2):
        client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}", headers=staff)

    views = [e for e in _org_log(client, owner, org_id)
             if e["action"] == "support.project_view"]
    assert len(views) == 2
    assert views[0]["actor_email"] == "staff@e.ru"
    assert views[0]["entity_name"] == "Покупка завода в Твери"


def test_the_case_read_lands_there_too(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    sid = _case(client, owner)
    _grant(client, owner, org_id)
    client.get(f"/api/v1/admin/organizations/{org_id}/audit-subjects/{sid}", headers=staff)

    assert any(e["action"] == "support.case_view" for e in _org_log(client, owner, org_id))


def test_granting_and_closing_are_logged(client, register, db_session):
    owner, org_id = _client_org(client, register)
    _grant(client, owner, org_id)
    client.delete(f"/api/v1/organizations/{org_id}/support-access", headers=owner)

    actions = {e["action"] for e in _org_log(client, owner, org_id)}
    assert {"support.grant", "support.revoke"} <= actions


# --- 6. Чтение и только чтение ---

def test_the_grant_gives_no_power(client, register, db_session):
    """Перечень власти оператора (F5) от гранта не вырос ни на один маршрут.

    Проверяется не поведение, а **список**: маршрут, меняющий что-то у клиента, обязан
    пройти через перечень власти, а не появиться среди чтений по гранту.
    """
    from app.routers import admin

    granted = [r for r in admin.router.routes
               if "/projects" in r.path or "/audit-subjects" in r.path]
    assert granted, "маршруты гранта не найдены — тест смотрит не туда"
    for route in granted:
        assert set(route.methods or set()) == {"GET"}, route.path


def test_the_grant_does_not_let_the_operator_edit(client, register, db_session):
    """Поддержка смотрит и рассказывает, а меняет клиент. Ни правки, ни удаления, ни
    расчёта от чужого имени: служебный признак прав в чужой организации не даёт, и
    грант этого не меняет."""
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)
    headers = {**staff, "X-Organization-Id": org_id}

    assert client.put(f"/api/v1/projects/{pid}", json={"name": "Подменён"},
                      headers=headers).status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}", headers=headers).status_code == 403
    assert client.post(f"/api/v1/projects/{pid}/calculate",
                       headers=headers).status_code == 403


def test_the_model_stays_untouched_after_a_read(client, register, db_session):
    staff = _staff(client, db_session, register)
    owner, org_id = _client_org(client, register)
    pid = _project(client, owner)
    _grant(client, owner, org_id)
    before = client.get(f"/api/v1/projects/{pid}", headers=owner).json()["model"]

    client.get(f"/api/v1/admin/organizations/{org_id}/projects/{pid}", headers=staff)

    assert client.get(f"/api/v1/projects/{pid}", headers=owner).json()["model"] == before
