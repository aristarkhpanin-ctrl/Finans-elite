"""Два уровня сотрудника платформы и список в интерфейсе (ADMIN-PHASE-F, F5).

`is_staff` был всё или ничего. Поддержке нужен просмотр — разобрать обращение, ответить
«почему человек не может войти», — а приостанавливать организации, блокировать учётные
записи, сбрасывать второй фактор и назначать тарифы не нужно; раз это выдавалось вместе,
промах поддержки стоил бы клиенту работы.

Проверяется обещание, а не форма: поддержка **видит** контур и **не может** ни одного из
четырёх действий власти, каждый отказ **назван**, уровень ставится вне API, а сотрудник
без назначенного уровня власти не получает — и об этом сказано, а не угадано.
"""
from __future__ import annotations

from app import crud
from app.db_models import STAFF_OPERATOR, STAFF_SUPPORT


def _staff(client, db_session, register, *, role=STAFF_OPERATOR, email="staff@e.ru"):
    headers = register(email=email, org=f"Платформа {email}")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email),
                   is_staff=True, role=role)
    return headers


def _support(client, db_session, register, email="support@e.ru"):
    return _staff(client, db_session, register, role=STAFF_SUPPORT, email=email)


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»"):
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


# --- Поддержка смотрит ---

def test_support_sees_the_clients(client, register, db_session):
    """Ради этого уровень и заводится: разбор обращения — это списки и карточки."""
    support = _support(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    assert client.get("/api/v1/admin/organizations",
                      headers=support).status_code == 200
    assert client.get(f"/api/v1/admin/organizations/{org_id}",
                      headers=support).status_code == 200
    assert client.get("/api/v1/admin/users?q=client",
                      headers=support).status_code == 200
    assert client.get("/api/v1/admin/log", headers=support).status_code == 200


# --- И не может ничего из власти ---

def test_support_cannot_suspend_an_organization(client, register, db_session):
    support = _support(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    r = client.post(f"/api/v1/admin/organizations/{org_id}/suspend",
                    json={"reason": "разбирательство"}, headers=support)
    assert r.status_code == 403
    assert "оператор" in r.json()["detail"].lower()


def test_support_cannot_block_an_account(client, register, db_session):
    support = _support(client, db_session, register)
    owner, _org_id = _client_org(client, register)
    victim = crud.get_user_by_email(db_session, "client@e.ru")

    r = client.post(f"/api/v1/admin/users/{victim.id}/block",
                    json={"reason": "по запросу"}, headers=support)
    assert r.status_code == 403 and "оператор" in r.json()["detail"].lower()


def test_support_cannot_reset_the_second_factor(client, register, db_session):
    support = _support(client, db_session, register)
    _owner, _org_id = _client_org(client, register)
    victim = crud.get_user_by_email(db_session, "client@e.ru")

    r = client.delete(f"/api/v1/admin/users/{victim.id}/totp", headers=support)
    assert r.status_code == 403 and "оператор" in r.json()["detail"].lower()


def test_support_cannot_assign_a_plan(client, register, db_session):
    support = _support(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    r = client.post(f"/api/v1/admin/organizations/{org_id}/subscription",
                    json={"plan_code": "team", "months": 1}, headers=support)
    assert r.status_code == 403 and "оператор" in r.json()["detail"].lower()


def test_the_refusal_names_where_the_level_is_set(client, register, db_session):
    """Отказ обязан сказать, что делать дальше: признак и уровень ставятся вне API,
    и сотрудник, наткнувшийся на 403, иначе пойдёт искать кнопку, которой нет."""
    support = _support(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    detail = client.post(f"/api/v1/admin/organizations/{org_id}/suspend",
                         json={"reason": "х"}, headers=support).json()["detail"]
    assert "set_staff" in detail


def test_the_operator_still_can(client, register, db_session):
    """Разделение не должно забрать власть у того, у кого она была."""
    operator = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)

    assert client.post(f"/api/v1/admin/organizations/{org_id}/suspend",
                       json={"reason": "разбирательство"},
                       headers=operator).status_code == 200


# --- Уровень ставится вне API ---

def test_the_level_is_not_handed_out_through_the_api(client, register, db_session):
    """Правило B1 не ослаблено: маршрут, повышающий права, сам становится мишенью."""
    support = _support(client, db_session, register)
    user = crud.get_user_by_email(db_session, "support@e.ru")

    assert client.patch("/api/v1/auth/me", json={"staff_role": STAFF_OPERATOR},
                        headers=support).status_code in (200, 422)
    db_session.refresh(user)
    assert user.staff_role == STAFF_SUPPORT


def test_removing_the_mark_erases_the_level(client, register, db_session):
    """Оставленный `operator` у бывшего сотрудника читался бы как действующая власть."""
    _headers = _staff(client, db_session, register)
    user = crud.get_user_by_email(db_session, "staff@e.ru")
    crud.set_staff(db_session, user, is_staff=False)
    assert user.staff_role == ""


def test_a_staff_member_without_a_level_gets_no_power(client, register, db_session):
    """Состояние, которого `set_staff` не создаёт (правка базы руками). Считать
    неназванный уровень высшим значило бы выдать власть по опечатке."""
    headers = _staff(client, db_session, register)
    user = crud.get_user_by_email(db_session, "staff@e.ru")
    user.staff_role = ""
    db_session.commit()
    _owner, org_id = _client_org(client, register)

    assert client.get("/api/v1/admin/organizations", headers=headers).status_code == 200
    assert client.post(f"/api/v1/admin/organizations/{org_id}/suspend",
                       json={"reason": "х"}, headers=headers).status_code == 403


# --- Список сотрудников ---

def test_the_product_answers_who_our_staff_are(client, register, db_session):
    operator = _staff(client, db_session, register)
    _support(client, db_session, register)

    body = client.get("/api/v1/admin/staff", headers=operator).json()
    by_email = {m["email"]: m for m in body["members"]}
    assert by_email["staff@e.ru"]["role"] == STAFF_OPERATOR
    assert by_email["support@e.ru"]["role"] == STAFF_SUPPORT


def test_the_list_holds_only_staff(client, register, db_session):
    operator = _staff(client, db_session, register)
    _client_org(client, register)

    emails = {m["email"] for m in
              client.get("/api/v1/admin/staff", headers=operator).json()["members"]}
    assert "client@e.ru" not in emails


def test_support_sees_the_list_too(client, register, db_session):
    """Список — наблюдение: «кто ходит к клиентам» обязан быть виден изнутри контура."""
    support = _support(client, db_session, register)
    assert client.get("/api/v1/admin/staff", headers=support).status_code == 200


def test_the_caveats_travel_with_the_list(client, register, db_session):
    operator = _staff(client, db_session, register)
    notes = " ".join(client.get("/api/v1/admin/staff", headers=operator).json()["notes"])
    assert "set_staff" in notes
    assert "неизвестно" in notes and "никогда" in notes


def test_an_unassigned_level_is_named_in_the_list(client, register, db_session):
    """Пустой уровень — не «поддержка». Подставить сюда значение значило бы ответить на
    вопрос, на который ответа нет."""
    operator = _staff(client, db_session, register)
    stray = _staff(client, db_session, register, email="stray@e.ru")
    user = crud.get_user_by_email(db_session, "stray@e.ru")
    user.staff_role = ""
    db_session.commit()
    assert stray

    body = client.get("/api/v1/admin/staff", headers=operator).json()
    assert next(m for m in body["members"] if m["email"] == "stray@e.ru")["role"] == ""
    assert any("уровень не назначен" in n for n in body["notes"])


def test_an_outsider_does_not_see_the_staff_list(client, auth_headers):
    assert client.get("/api/v1/admin/staff", headers=auth_headers).status_code == 403


def test_last_seen_comes_from_the_sessions(client, register, db_session):
    """У сотрудника платформы вопрос не «когда заходил в эту компанию», а «жива ли
    учётная запись»: отметка присутствия в членстве на него не отвечает."""
    operator = _staff(client, db_session, register)

    body = client.get("/api/v1/admin/staff", headers=operator).json()
    mine = next(m for m in body["members"] if m["email"] == "staff@e.ru")
    assert mine["last_seen_at"]              # вход только что был — он и есть отметка


def test_the_list_does_not_write_to_the_journal(client, register, db_session):
    """Исключение «журнал пишет чтение» заведено для прихода постороннего **к клиенту**,
    а не для взгляда контура на себя."""
    operator = _staff(client, db_session, register)
    before = len(client.get("/api/v1/admin/log", headers=operator).json()["entries"])
    client.get("/api/v1/admin/staff", headers=operator)
    after = len(client.get("/api/v1/admin/log", headers=operator).json()["entries"])
    assert after == before
