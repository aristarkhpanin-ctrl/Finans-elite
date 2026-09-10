"""Приостановка организации и блокировка учётной записи (ADMIN-DECOMPOSITION.md, B2).

Статус подписки писался с самого начала и **не читался никем**: неплательщик работал
ровно как плательщик. Здесь он начинает действовать — по правилу 7 плана: **неоплата не
конфискует данные**. Ограниченная организация видит свои модели, считает их и выгружает
документы; заводить новые и править старые нельзя.

Главный тест здесь — матрица «состояние × операция». Она проверяет не то, что отказ
случается, а **где проходит граница**: закрыв лишнее, мы отняли бы у клиента его же
числа, а оставив лишнее — сделали бы ограничение декоративным.
"""
from __future__ import annotations

import pytest

from app import crud
from app.access import UNPAID_STATUSES, WRITE_PERMS
from app.rbac import Perm


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _project(client, headers, name="Проект") -> str:
    return client.post("/api/v1/projects",
                       json={"name": name, "model": client.get("/api/v1/sample").json()},
                       headers=headers).json()["id"]


def _unpaid(db_session, org_id, status="past_due", product="business") -> None:
    crud.set_plan(db_session, org_id, "free", status=status, product=product)


# --- Граница режима чтения и выгрузки ---

def test_write_permissions_are_exactly_the_content_ones():
    """Закрывается **изменение содержимого** — и только оно.

    Расчёт остаётся открытым намеренно: это способ посмотреть свои числа (экран
    результатов зовёт его при каждом открытии, DOCX собирается тем же движком). Оплата и
    участники — тоже: иначе ограничение за неоплату превращается в ловушку, из которой
    нельзя ни выйти, ни отозвать доступ у уволенного.
    """
    assert WRITE_PERMS == {Perm.PROJECT_CREATE, Perm.PROJECT_UPDATE, Perm.PROJECT_DELETE}
    for open_perm in (Perm.PROJECT_READ, Perm.PROJECT_CALCULATE, Perm.MEMBER_READ,
                      Perm.MEMBER_MANAGE, Perm.ORG_MANAGE, Perm.BILLING_MANAGE):
        assert open_perm not in WRITE_PERMS


@pytest.mark.parametrize("status", sorted(UNPAID_STATUSES))
def test_unpaid_subscription_closes_writing_and_leaves_reading(client, auth_headers,
                                                               db_session, status):
    org = _org_id(client, auth_headers)
    pid = _project(client, auth_headers)
    _unpaid(db_session, org, status)

    # Закрыто: завести, изменить, удалить.
    assert client.post("/api/v1/projects", json={"name": "Ещё", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 403
    assert client.put(f"/api/v1/projects/{pid}", json={"name": "Новое"},
                      headers=auth_headers).status_code == 403
    assert client.delete(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 403

    # Открыто: посмотреть, посчитать, выгрузить, управлять организацией и заплатить.
    assert client.get("/api/v1/projects", headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}", headers=auth_headers).status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/calculate",
                       headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/business-plan.docx",
                      headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/organizations/{org}/members",
                      headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/organizations/{org}/subscription",
                      headers=auth_headers).status_code == 200


def test_refusal_names_the_reason_and_the_way_out(client, auth_headers, db_session):
    """Отказ без причины неотличим от поломки — клиент пойдёт не в поддержку, а в отзывы."""
    org = _org_id(client, auth_headers)
    _unpaid(db_session, org)
    detail = client.post("/api/v1/projects", json={"name": "Х", "model":
                         client.get("/api/v1/sample").json()},
                         headers=auth_headers).json()["detail"]
    assert "Финанс-Элит" in detail            # какой продукт
    assert "оплатите" in detail.lower()       # что делать
    assert "выгрузк" in detail.lower()        # и что данные не отняты


def test_paying_returns_the_organization_to_work(client, auth_headers, db_session):
    """Ограничение обязано сниматься тем, чем оно вызвано, иначе это ловушка."""
    org = _org_id(client, auth_headers)
    _unpaid(db_session, org)
    assert client.post("/api/v1/projects", json={"name": "Х", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 403
    crud.set_plan(db_session, org, "free", status="active")
    assert client.post("/api/v1/projects", json={"name": "Х", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 201


def test_products_are_restricted_separately(client, auth_headers, db_session):
    """Подписка своя у каждого продукта: просроченный «Аудит» не закрывает «Элит».

    Иначе клиент, переставший платить за один продукт, теряет и второй — оплаченный.
    """
    org = _org_id(client, auth_headers)
    _unpaid(db_session, org, product="audit")

    assert client.post("/api/v1/projects", json={"name": "Проект", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 201
    assert client.post("/api/v1/audit/subjects",
                       json={"name": "Дело", "model": {"name": "Дело", "periods": [],
                                                       "lines": []}},
                       headers=auth_headers).status_code == 403


def test_audit_routes_all_name_their_product():
    """Маршрут «Аудита» без явного продукта спрашивал бы про чужую подписку — молча.

    Проверяется по исходнику: забытый `product` не виден ни в одном ответе, он просто
    смотрит не на ту подписку, и ошибка всплывёт у клиента, а не в тесте.
    """
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app" / "routers" / "audit.py").read_text()
    bare = [line.strip() for line in source.splitlines()
            if "require_permission(Perm." in line and 'product="audit"' not in line]
    assert bare == []


# --- Ручная приостановка оператором ---

def test_operator_suspends_and_the_client_is_told_why(client, auth_headers, db_session,
                                                       register):
    staff = _staff(client, db_session, register)
    org = _org_id(client, auth_headers)

    r = client.post(f"/api/v1/admin/organizations/{org}/suspend",
                    json={"reason": "жалоба на содержимое"}, headers=staff)
    assert r.status_code == 200 and r.json()["suspended"] is True

    detail = client.post("/api/v1/projects", json={"name": "Х", "model":
                         client.get("/api/v1/sample").json()},
                         headers=auth_headers).json()["detail"]
    assert "жалоба на содержимое" in detail
    assert "поддержку" in detail          # выход отсюда — не оплата

    mine = client.get("/api/v1/organizations", headers=auth_headers).json()[0]
    kinds = {x["kind"] for x in mine["restrictions"]}
    assert kinds == {"suspended"}
    # Приостановка — про организацию целиком, поэтому приходит по обоим продуктам.
    assert {x["product"] for x in mine["restrictions"]} == {"business", "audit"}


def test_paying_does_not_lift_a_manual_suspension(client, auth_headers, db_session,
                                                   register):
    """Обещать «оплатите — и заработает» там, где решает человек, нельзя."""
    staff = _staff(client, db_session, register)
    org = _org_id(client, auth_headers)
    client.post(f"/api/v1/admin/organizations/{org}/suspend",
                json={"reason": "разбирательство"}, headers=staff)
    crud.set_plan(db_session, org, "pro", status="active")

    assert client.post("/api/v1/projects", json={"name": "Х", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 403


def test_lifting_the_suspension_returns_work_and_clears_the_reason(client, auth_headers,
                                                                    db_session, register):
    staff = _staff(client, db_session, register)
    org = _org_id(client, auth_headers)
    client.post(f"/api/v1/admin/organizations/{org}/suspend",
                json={"reason": "проверка"}, headers=staff)

    r = client.delete(f"/api/v1/admin/organizations/{org}/suspend", headers=staff)
    assert r.status_code == 200 and r.json()["suspended"] is False
    # Причина стёрта: оставленная у работающей организации, она читалась бы как
    # действующее ограничение. Историю хранит журнал.
    assert r.json()["suspend_reason"] == ""
    assert client.get("/api/v1/organizations",
                      headers=auth_headers).json()[0]["restrictions"] == []
    assert client.post("/api/v1/projects", json={"name": "Х", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 201


def test_suspension_is_written_in_both_journals(client, auth_headers, db_session, register):
    staff = _staff(client, db_session, register)
    org = _org_id(client, auth_headers)
    client.post(f"/api/v1/admin/organizations/{org}/suspend",
                json={"reason": "жалоба"}, headers=staff)

    theirs = client.get(f"/api/v1/organizations/{org}/audit-log",
                        headers=auth_headers).json()["entries"]
    entry = next(e for e in theirs if e["action"] == "staff.org_suspend")
    assert entry["details"] == "жалоба" and entry["actor_email"] == "staff@e.ru"
    ours = client.get("/api/v1/admin/log", headers=staff).json()["entries"]
    assert any(e["action"] == "staff.org_suspend" for e in ours)


def test_reason_is_required(client, auth_headers, db_session, register):
    staff = _staff(client, db_session, register)
    org = _org_id(client, auth_headers)
    assert client.post(f"/api/v1/admin/organizations/{org}/suspend", json={"reason": ""},
                       headers=staff).status_code == 422


def test_client_admin_cannot_suspend_anything(client, auth_headers):
    """Ручная приостановка — власть платформы, а не роль в организации."""
    org = _org_id(client, auth_headers)
    assert client.post(f"/api/v1/admin/organizations/{org}/suspend",
                       json={"reason": "хочу"}, headers=auth_headers).status_code == 403


# --- Блокировка учётной записи платформы ---

def test_account_block_acts_on_all_organizations_at_once(client, db_session, register):
    """Отличие от A1: там администратор закрывает человеку **своё** пространство, здесь
    платформа закрывает саму учётную запись — во всех организациях сразу."""
    staff = _staff(client, db_session, register)
    a = register(email="a@e.ru", org="Первая")
    b = register(email="b@e.ru", org="Вторая")
    org_a, org_b = _org_id(client, a), _org_id(client, b)
    member = client.post(f"/api/v1/organizations/{org_a}/members",
                         json={"email": "общий@e.ru", "full_name": "Общий",
                               "role": "editor"}, headers=a).json()
    client.post(f"/api/v1/organizations/{org_b}/members",
                json={"email": "общий@e.ru", "full_name": "Общий", "role": "editor"},
                headers=b)
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    token = client.post("/api/v1/auth/login",
                        json={"email": "общий@e.ru", "password": "secret123"}
                        ).json()["access_token"]
    worker = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/projects",
                      headers={**worker, "X-Organization-Id": org_b}).status_code == 200

    r = client.post(f"/api/v1/admin/users/{member['user_id']}/block",
                    json={"reason": "мошенничество"}, headers=staff)
    assert r.status_code == 200 and r.json()["blocked"] is True

    # Выданный до блокировки токен перестаёт работать сразу и везде.
    for org in (org_a, org_b):
        refused = client.get("/api/v1/projects",
                             headers={**worker, "X-Organization-Id": org})
        assert refused.status_code == 403
        assert "мошенничество" in refused.json()["detail"]


def test_blocked_account_cannot_log_in_and_is_told_why(client, db_session, register):
    staff = _staff(client, db_session, register)
    owner = register(email="o@e.ru", org="Орг")
    org = _org_id(client, owner)
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    client.post(f"/api/v1/admin/users/{member['user_id']}/block",
                json={"reason": "по заявлению"}, headers=staff)

    r = client.post("/api/v1/auth/login",
                    json={"email": "к@e.ru", "password": "secret123"})
    # 403, а не 401: пароль верен, человек тот самый — гонять его по кругу «проверьте
    # пароль» значило бы прятать причину, ради которой блокировку и ставили.
    assert r.status_code == 403 and "по заявлению" in r.json()["detail"]
    assert any(e["action"] == "auth.login_blocked" for e in
               client.get(f"/api/v1/organizations/{org}/audit-log",
                          headers=owner).json()["entries"])


def test_block_is_visible_to_the_organizations_of_the_person(client, db_session, register):
    """Администратор обязан понимать, почему его сотрудник перестал работать, — иначе
    он будет искать поломку у себя."""
    staff = _staff(client, db_session, register)
    owner = register(email="o@e.ru", org="Орг")
    org = _org_id(client, owner)
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    client.post(f"/api/v1/admin/users/{member['user_id']}/block",
                json={"reason": "по заявлению"}, headers=staff)

    entries = client.get(f"/api/v1/organizations/{org}/audit-log",
                         headers=owner).json()["entries"]
    assert any(e["action"] == "staff.user_block" and "по заявлению" in e["details"]
               for e in entries)


def test_unblocking_returns_access(client, db_session, register):
    staff = _staff(client, db_session, register)
    owner = register(email="o@e.ru", org="Орг")
    org = _org_id(client, owner)
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    client.post("/api/v1/auth/activate",
                json={"token": member["invite_token"], "password": "secret123"})
    client.post(f"/api/v1/admin/users/{member['user_id']}/block",
                json={"reason": "ошибка"}, headers=staff)
    client.delete(f"/api/v1/admin/users/{member['user_id']}/block", headers=staff)

    r = client.post("/api/v1/auth/login",
                    json={"email": "к@e.ru", "password": "secret123"})
    assert r.status_code == 200


def test_operator_cannot_block_himself_or_a_colleague(client, db_session, register):
    """Два запрета — не придирки: первый спасает оператора от самозапирания, второй не
    даёт служебному контуру решать свои споры блокировками."""
    staff = _staff(client, db_session, register)
    other = _staff(client, db_session, register, email="staff2@e.ru")
    me = client.get("/api/v1/auth/me", headers=staff).json()
    colleague = client.get("/api/v1/auth/me", headers=other).json()

    r1 = client.post(f"/api/v1/admin/users/{me['id']}/block",
                     json={"reason": "проверка"}, headers=staff)
    assert r1.status_code == 400 and "Себя" in r1.json()["detail"]
    r2 = client.post(f"/api/v1/admin/users/{colleague['id']}/block",
                     json={"reason": "проверка"}, headers=staff)
    assert r2.status_code == 400 and "сотрудника платформы" in r2.json()["detail"]


def test_blocked_account_is_visible_in_the_operator_search(client, db_session, register):
    staff = _staff(client, db_session, register)
    owner = register(email="o@e.ru", org="Орг")
    org = _org_id(client, owner)
    member = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "к@e.ru", "full_name": "К", "role": "editor"},
                         headers=owner).json()
    client.post(f"/api/v1/admin/users/{member['user_id']}/block",
                json={"reason": "по заявлению"}, headers=staff)

    found = client.get("/api/v1/admin/users?q=к@e.ru", headers=staff).json()[0]
    assert found["blocked"] is True and found["block_reason"] == "по заявлению"
    assert found["blocked_by"] == "staff@e.ru"


# --- Инертность ---

def test_ordinary_organization_is_unaffected(client, auth_headers):
    """Пока никто ничего не приостановил, платформа работает как прежде."""
    assert client.get("/api/v1/organizations",
                      headers=auth_headers).json()[0]["restrictions"] == []
    assert client.post("/api/v1/projects", json={"name": "Х", "model":
                       client.get("/api/v1/sample").json()},
                       headers=auth_headers).status_code == 201
