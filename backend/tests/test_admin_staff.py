"""Служебный контур платформы (ADMIN-DECOMPOSITION.md, фаза B1).

Мы как владельцы SaaS не видели собственных клиентов вовсе: ни списка организаций, ни
тарифов, ни ответа на вопрос поддержки «почему человек не может войти». Фаза заводит
фигуру сотрудника платформы — и **границу** вокруг неё, которая здесь важнее самой
функции: оператор видит клиента снаружи (кто, с какого числа, за что платит, сколько
чего завёл) и не видит ни одного числа из его моделей.

Проверяются четыре обещания: доступ только с признаком сотрудника; содержимого моделей
не видно; вход в организацию идёт через ту же дверь арендатора, что и у её участников;
визит виден **клиенту** в его собственном журнале.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app import crud
from app.db_models import Organization
from app.routers import admin


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    """Сотрудник платформы: обычная регистрация плюс признак, поставленный вне API."""
    headers = register(email=email, org="Наша платформа")
    user = crud.get_user_by_email(db_session, email)
    crud.set_staff(db_session, user, is_staff=True)
    return headers


def _client_org(client, register, *, email="client@e.ru", org="ООО «Клиент»") -> dict:
    return register(email=email, org=org)


# --- Граница: кто вообще сюда входит ---

def test_staff_area_is_closed_to_ordinary_users(client, auth_headers):
    """Обычный пользователь — 403 с названной причиной, а не 404 и не пустой список."""
    r = client.get("/api/v1/admin/organizations", headers=auth_headers)
    assert r.status_code == 403
    assert "сотрудник" in r.json()["detail"].lower()


def test_staff_area_is_closed_without_a_token(client):
    """Без токена — 401 (это вход), с токеном без признака — 403 (это права).

    Разные ответы на разные вопросы: 401 отправляет входить, 403 говорит, что входить
    бесполезно. Слить их в один означало бы гонять своего же сотрудника по кругу
    аутентификации из-за недостающего признака.
    """
    assert client.get("/api/v1/admin/organizations").status_code == 401


def test_every_admin_route_requires_the_staff_mark():
    """Перечень: новый служебный маршрут не может открыться всем незаметно.

    Проверяется не поведение одного эндпоинта, а то, что зависимость стоит на **каждом**:
    забытая на одном маршруте, она отдала бы наружу весь контур целиком.
    """
    unguarded = []
    for route in admin.router.routes:
        params = inspect.signature(route.endpoint).parameters
        if not any(getattr(p.default, "dependency", None) is admin.require_staff
                   for p in params.values()):
            unguarded.append(f"{sorted(route.methods)} {route.path}")
    assert unguarded == [], f"маршруты без require_staff: {unguarded}"


def test_staff_can_change_exactly_four_things():
    """Перечень власти оператора над клиентом — в одном месте и целиком.

    В B1 изменяющих маршрутов не было вовсе. B2 добавил ровно два действия (приостановка
    организации и блокировка учётной записи) со снятием у каждого — и список закрыт:
    новый служебный маршрут, меняющий что-то у клиента, обязан пройти здесь, а не
    появиться тихо между экранами наблюдения.
    """
    mutating = sorted(f"{sorted(r.methods)[0]} {r.path}" for r in admin.router.routes
                      if (r.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"})
    assert mutating == [
        "DELETE /api/v1/admin/organizations/{org_id}/suspend",
        "DELETE /api/v1/admin/users/{user_id}/block",
        "POST /api/v1/admin/organizations/{org_id}/suspend",
        "POST /api/v1/admin/users/{user_id}/block",
    ]


def test_staff_mark_grants_nothing_in_client_organizations(client, db_session, register):
    """Признак сотрудника — другая ось власти: прав в чужой организации он не даёт.

    Иначе служебный признак стал бы универсальной отмычкой, и разделение контуров
    существовало бы только на бумаге.
    """
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]

    r = client.get("/api/v1/projects", headers={**staff, "X-Organization-Id": org_id})
    assert r.status_code == 403
    assert client.get(f"/api/v1/organizations/{org_id}/members",
                      headers=staff).status_code == 403


# --- Что видно и чего не видно ---

def test_operator_sees_the_client_from_outside(client, db_session, register):
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    client.post("/api/v1/projects", json={"name": "Проект", "model":
                client.get("/api/v1/sample").json()}, headers=client_headers)

    page = client.get("/api/v1/admin/organizations", headers=staff).json()
    ours = next(o for o in page["organizations"] if o["name"] == "ООО «Клиент»")
    assert ours["members"] == 1 and ours["projects"] == 1
    assert page["total"] >= 2                      # клиент и наша собственная организация
    # Оба продукта, а не только оформленные подписки: пользоваться продуктом можно и на
    # тарифе по умолчанию, и такой клиент не должен выглядеть не пользующимся им.
    subs = {s["product"]: s for s in ours["subscriptions"]}
    assert set(subs) == {"business", "audit"}
    assert subs["business"]["plan_name"]           # тариф назван словом, а не кодом
    assert subs["audit"]["status"] == "none"       # «не оформлял» ≠ «оформил бесплатный"


def test_operator_does_not_see_the_contents_of_models(client, db_session, register):
    """Правило 6: метаданные — да, содержимое — нет.

    Название проекта («Покупка завода в Твери») само по себе коммерческая тайна, поэтому
    служебный ответ не содержит ни имён сущностей, ни чисел модели. Проверка идёт по
    всему тексту ответа: поле, добавленное «на всякий случай», провалит её сразу.
    """
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    model = client.get("/api/v1/sample").json()
    model["header"]["project_name"] = "Покупка завода в Твери"
    client.post("/api/v1/projects", json={"name": "Покупка завода в Твери", "model": model},
                headers=client_headers)
    client.post("/api/v1/audit/subjects", json={"name": "Цель поглощения", "model": {
        "name": "Цель поглощения", "periods": [], "lines": []}}, headers=client_headers)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]

    texts = [client.get("/api/v1/admin/organizations", headers=staff).text,
             client.get(f"/api/v1/admin/organizations/{org_id}", headers=staff).text,
             client.get("/api/v1/admin/users?q=client", headers=staff).text]
    for text in texts:
        assert "Покупка завода" not in text
        assert "Цель поглощения" not in text


def test_volumes_report_the_last_calculation_not_an_invented_count(client, db_session,
                                                                   register):
    """Счётчика расчётов у платформы нет — и он не выдумывается.

    Расчёт зовётся при каждом открытии результатов, это чтение, и в журнал он не пишется
    (правило 5). Вместо придуманного числа возвращается дата последнего расчёта: она
    есть в самих проектах, и за неё можно отвечать.
    """
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()},
                      headers=client_headers).json()["id"]

    page = client.get("/api/v1/admin/organizations", headers=staff).json()
    ours = next(o for o in page["organizations"] if o["name"] == "ООО «Клиент»")
    assert "calculations" not in ours
    assert ours["last_calculated_at"] is None

    client.post(f"/api/v1/projects/{pid}/calculate", headers=client_headers)
    page = client.get("/api/v1/admin/organizations", headers=staff).json()
    ours = next(o for o in page["organizations"] if o["name"] == "ООО «Клиент»")
    assert ours["last_calculated_at"] is not None


def test_user_search_answers_the_support_question(client, db_session, register):
    """«Человек не может войти» — это два разных случая, и ответ их различает."""
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]
    member = client.post(f"/api/v1/organizations/{org_id}/members",
                         json={"email": "новичок@e.ru", "full_name": "Новичок",
                               "role": "editor"}, headers=client_headers).json()
    client.post(f"/api/v1/organizations/{org_id}/members/{member['user_id']}/block",
                json={"reason": "испытательный срок"}, headers=client_headers)

    found = client.get("/api/v1/admin/users?q=новичок", headers=staff).json()
    assert [u["email"] for u in found] == ["новичок@e.ru"]
    assert found[0]["has_password"] is False       # пароль не заводился — не «забыт»
    assert found[0]["organizations"][0]["blocked"] is True
    assert found[0]["organizations"][0]["block_reason"] == "испытательный срок"


def test_unknown_organization_is_named_not_silently_empty(client, db_session, register):
    staff = _staff(client, db_session, register)
    assert client.get("/api/v1/admin/organizations/нет-такой", headers=staff).status_code == 404


# --- Клиент видит, что к нему приходили ---

def test_visit_is_written_in_both_journals(client, db_session, register):
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]

    client.get(f"/api/v1/admin/organizations/{org_id}", headers=staff)

    theirs = client.get(f"/api/v1/organizations/{org_id}/audit-log",
                        headers=client_headers).json()["entries"]
    visit = [e for e in theirs if e["action"] == "staff.org_view"]
    assert len(visit) == 1 and visit[0]["actor_email"] == "staff@e.ru"

    ours = client.get("/api/v1/admin/log", headers=staff).json()["entries"]
    assert [e["action"] for e in ours if e["organization_id"] == org_id] == ["staff.org_view"]


def test_reading_the_client_journal_is_itself_written_into_it(client, db_session, register):
    """Чтение журнала — вынос данных наружу, и умолчать о нём журнал не вправе."""
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]

    client.get(f"/api/v1/admin/organizations/{org_id}/audit-log", headers=staff)

    theirs = client.get(f"/api/v1/organizations/{org_id}/audit-log",
                        headers=client_headers).json()["entries"]
    assert any(e["action"] == "staff.audit_log_view" for e in theirs)


def test_platform_wide_lists_do_not_touch_client_journals(client, db_session, register):
    """Список клиентов — не визит к клиенту.

    Запись у каждой организации при каждом обновлении экрана оператора утопила бы сигнал
    «к нам приходили» в шуме, который сама же и создаёт.
    """
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]

    client.get("/api/v1/admin/organizations", headers=staff)
    client.get("/api/v1/admin/users?q=client", headers=staff)

    theirs = client.get(f"/api/v1/organizations/{org_id}/audit-log",
                        headers=client_headers).json()["entries"]
    assert not [e for e in theirs if e["action"].startswith("staff.")]
    ours = client.get("/api/v1/admin/log", headers=staff).json()["entries"]
    assert {e["action"] for e in ours} == {"staff.orgs_list", "staff.users_search"}


def test_trace_of_the_visit_outlives_the_organization(client, db_session, register):
    """Удаление организации не стирает след визита — иначе он исчезал бы тогда, когда
    нужнее всего. Имя организации хранится в самой записи, как почта актора в журнале."""
    staff = _staff(client, db_session, register)
    client_headers = _client_org(client, register)
    org_id = client.get("/api/v1/organizations", headers=client_headers).json()[0]["id"]
    client.get(f"/api/v1/admin/organizations/{org_id}", headers=staff)

    db_session.delete(db_session.get(Organization, org_id))
    db_session.commit()

    ours = client.get("/api/v1/admin/log", headers=staff).json()["entries"]
    survived = [e for e in ours if e["organization_id"] == org_id]
    assert survived and survived[0]["organization_name"] == "ООО «Клиент»"


# --- Изоляция арендатора ---

def test_tenant_is_entered_only_in_two_named_places():
    """Дверь арендатора — в двух местах, и оба названы.

    План допускал служебный обход RLS «осознанно и в одном месте». Обхода не понадобилось:
    оператор входит в организацию тем же ``set_tenant``, что и её участники. Тест следит,
    чтобы третьего места не появилось: контур, в котором RLS не действует, живёт ровно до
    первой ошибки, направившей туда клиентский запрос.
    """
    app_dir = Path(__file__).resolve().parents[1] / "app"
    callers = sorted(
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if path.name not in {"database.py"}
        and ("set_tenant(" in path.read_text() or "clear_tenant(" in path.read_text())
    )
    assert callers == ["deps.py", "routers/admin.py"], (
        "арендатор выставляется где-то ещё; это либо новая дверь в чужие данные, "
        f"либо забытый выход из неё: {callers}")


def test_operator_leaves_the_tenant_behind(client, db_session, register):
    """После служебного запроса арендатор снят: оставленный от предыдущей организации,
    он открыл бы следующему запросу той же сессии не те данные."""
    source = inspect.getsource(admin._as_tenant)
    assert "finally" in source and "clear_tenant" in source
    staff = _staff(client, db_session, register)
    assert client.get("/api/v1/admin/organizations", headers=staff).status_code == 200


# --- Признак сотрудника ---

def test_mark_is_not_granted_through_the_api(client, auth_headers):
    """Маршрута, повышающего права, нет: он сам стал бы главной мишенью."""
    assert client.patch("/api/v1/auth/me", json={"is_staff": True},
                        headers=auth_headers).json().get("is_staff") is False
    assert not [r for r in admin.router.routes if "staff" in r.path and
                (r.methods or set()) & {"POST", "PUT", "PATCH"}]


def test_profile_reports_the_mark(client, db_session, register):
    """Интерфейсу признак сообщается — чтобы показать раздел; права даёт сервер."""
    assert client.get("/api/v1/auth/me",
                      headers=register(email="a@e.ru")).json()["is_staff"] is False
    staff = _staff(client, db_session, register)
    assert client.get("/api/v1/auth/me", headers=staff).json()["is_staff"] is True
