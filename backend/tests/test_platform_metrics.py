"""Сводка платформы (ADMIN-DECOMPOSITION.md, B3).

Владелец SaaS не мог ответить на простые вопросы о собственном деле: сколько клиентов,
кто из них жив, чем пользуются. Фаза отвечает — из **уже имеющихся** данных: организации,
пользователи, членство, подписки и журнал. Второй системы учёта не заводится: счётчик,
поставленный «под метрики», начинает расходиться с данными, и разбирать потом приходится
не бизнес, а расхождение.

Половина тестов здесь — про **оговорки**, а не про числа. Сводка обязана говорить, чего
она не измеряет: ноль выгрузок за период, которого журнал не застал, выглядит ровно как
ноль выгрузок, и без оговорки им и станет.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud
from app.db_models import Membership
from app.metrics import _months_back


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _metrics(client, staff, **params) -> dict:
    return client.get("/api/v1/admin/metrics", params=params, headers=staff).json()


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


# --- Доступ ---

def test_metrics_are_staff_only(client, auth_headers):
    assert client.get("/api/v1/admin/metrics", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/metrics.csv", headers=auth_headers).status_code == 403


# --- Числа ---

def test_counts_the_platform_as_it_is(client, db_session, register):
    staff = _staff(client, db_session, register)
    register(email="a@e.ru", org="Первая")
    register(email="b@e.ru", org="Вторая")

    m = _metrics(client, staff)
    assert m["organizations"] == 3          # две клиентские и наша собственная
    assert m["users"] == 3


def test_volumes_are_summed_across_tenants(client, db_session, register):
    """Проекты и дела лежат под RLS: свод собирается обходом арендаторов — той же
    дверью, что и всё остальное в служебном контуре (обхода изоляции у платформы нет)."""
    staff = _staff(client, db_session, register)
    a = register(email="a@e.ru", org="Первая")
    b = register(email="b@e.ru", org="Вторая")
    for headers in (a, b):
        client.post("/api/v1/projects", json={"name": "П", "model":
                    client.get("/api/v1/sample").json()}, headers=headers)
    client.post("/api/v1/audit/subjects",
                json={"name": "Дело", "model": {"name": "Дело", "periods": [], "lines": []}},
                headers=b)

    m = _metrics(client, staff)
    assert m["projects"] == 2 and m["cases"] == 1


def test_calculated_counts_projects_not_calculations(client, db_session, register):
    """Счётчика расчётов у платформы нет — и «сколько считали» его не подменяет.

    Проект, открытый трижды, остаётся одним проектом: иначе число зависело бы от того,
    сколько раз человек нажал F5, и выглядело бы измеренным.
    """
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()}, headers=owner).json()["id"]

    assert _metrics(client, staff)["projects_calculated"] == 0
    for _ in range(3):
        client.post(f"/api/v1/projects/{pid}/calculate", headers=owner)
    m = _metrics(client, staff)
    assert m["projects_calculated"] == 1
    assert any("не сколько было расчётов" in n for n in m["notes"])


def test_exports_come_from_the_journal(client, db_session, register):
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()}, headers=owner).json()["id"]

    assert _metrics(client, staff)["exports"] == 0
    client.get(f"/api/v1/projects/{pid}/business-plan.docx", headers=owner)
    assert _metrics(client, staff)["exports"] == 1


def test_journal_export_is_not_counted_as_a_document(client, db_session, register):
    """Выгрузка журнала — вынос следов, а не продукта. Одно число на два вопроса
    отвечало бы неправильно на оба."""
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    org = _org_id(client, owner)
    client.get(f"/api/v1/organizations/{org}/audit-log.csv", headers=owner)
    assert _metrics(client, staff)["exports"] == 0


def test_active_counts_the_person_once_per_window(client, db_session, register):
    """Человек, работавший в трёх организациях, — один активный пользователь.

    Иначе «активных пользователей» окажется больше, чем пользователей вообще, и первый
    же взгляд на сводку покажет, что она не считает, а складывает.
    """
    staff = _staff(client, db_session, register)
    a = register(email="a@e.ru", org="Первая")
    b = register(email="b@e.ru", org="Вторая")
    org_b = _org_id(client, b)
    member = client.post(f"/api/v1/organizations/{org_b}/members",
                         json={"email": "a@e.ru", "full_name": "А", "role": "editor"},
                         headers=b).json()
    assert member["user_id"]
    client.get("/api/v1/projects", headers=a)
    client.get("/api/v1/projects", headers={**a, "X-Organization-Id": org_b})

    # Отметок присутствия три (у «а» их две — по одной на организацию), а людей два.
    fresh = [m for m in db_session.query(Membership).all() if m.last_seen_at is not None]
    assert len(fresh) == 3

    m = _metrics(client, staff)
    assert m["active_users"]["7"] == 2              # «а» посчитан один раз, не два
    assert m["active_organizations"]["7"] == 2
    assert m["active_users"]["7"] <= m["users"]


def test_members_without_a_mark_are_unknown_not_idle(client, db_session, register):
    """Отметка присутствия ведётся не с первого дня, и молчание о ней — «неизвестно»."""
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    org = _org_id(client, owner)
    client.post(f"/api/v1/organizations/{org}/members",
                json={"email": "новый@e.ru", "full_name": "Новый", "role": "editor"},
                headers=owner)

    m = _metrics(client, staff)
    assert m["members_without_mark"] >= 1
    assert any("«неизвестно», а не «не работают»" in n for n in m["notes"])


def test_growth_keeps_empty_months(client, db_session, register):
    """Пустой месяц остаётся в ряду с нулём: выброшенный, он превращает провал в
    графике в ровную линию — то есть врёт там, где смотреть интереснее всего."""
    staff = _staff(client, db_session, register)
    m = _metrics(client, staff, months=6)
    assert [p["period"] for p in m["growth"]] == _months_back(
        datetime.now(timezone.utc), 6)
    assert sum(p["organizations"] for p in m["growth"]) == m["organizations"]


def test_plans_count_only_the_subscriptions_that_exist(client, db_session, register):
    """«Выбрал бесплатный» и «не выбирал ничего» — разные состояния клиента."""
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    org = _org_id(client, owner)
    m = _metrics(client, staff)
    business = [p for p in m["plans"] if p["product"] == "business"]
    assert sum(p["organizations"] for p in business) == m["organizations"]
    # «Аудитом» никто не оформлял подписку — и в разрезе его нет вовсе, а не с нулём:
    # приписать всех к тарифу по умолчанию значило бы выдать неоформленное за выбранное.
    assert not [p for p in m["plans"] if p["product"] == "audit"]

    crud.set_plan(db_session, org, "audit_team", status="active", product="audit")
    m = _metrics(client, staff)
    audit = [p for p in m["plans"] if p["product"] == "audit"]
    assert len(audit) == 1 and audit[0]["organizations"] == 1
    assert audit[0]["plan_name"] == "Команда"      # тариф назван словом, а не кодом


# --- Оговорки ---

def test_journal_horizon_is_named(client, db_session, register):
    """Ноль выгрузок за период, которого журнал не застал, — это «не записывали»."""
    staff = _staff(client, db_session, register)
    m = _metrics(client, staff)
    assert any("Журнал ведётся с" in n or "Журнал действий пуст" in n for n in m["notes"])


def test_empty_platform_says_so_instead_of_showing_zeros(client, db_session, register):
    staff = _staff(client, db_session, register)
    m = _metrics(client, staff)
    assert m["projects"] == 0 and m["exports"] == 0
    # Ноль сам по себе ничего не объясняет — рядом сказано, почему он ноль.
    assert len(m["notes"]) >= 2


def test_window_is_a_parameter_and_is_named_in_the_answer(client, db_session, register):
    staff = _staff(client, db_session, register)
    m = _metrics(client, staff, days=7)
    assert m["since_days"] == 7
    assert any("за 7 дн." in n for n in m["notes"])


def test_calculation_outside_the_window_is_not_counted(client, db_session, register):
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()}, headers=owner).json()["id"]
    client.post(f"/api/v1/projects/{pid}/calculate", headers=owner)

    project = crud.get_project(db_session, _org_id(client, owner), pid)
    project.last_calculated_at = datetime.now(timezone.utc) - timedelta(days=40)
    db_session.commit()

    assert _metrics(client, staff, days=30)["projects_calculated"] == 0
    assert _metrics(client, staff, days=90)["projects_calculated"] == 1


# --- Выгрузка ---

def test_csv_carries_the_same_numbers_and_the_same_caveats(client, db_session, register):
    """Таблица, доехавшая до чужой презентации без оговорок, утверждает больше, чем
    платформа измеряла."""
    staff = _staff(client, db_session, register)
    register(email="a@e.ru", org="Первая")

    r = client.get("/api/v1/admin/metrics.csv", headers=staff)
    assert r.status_code == 200
    body = r.content.decode("utf-8-sig")
    assert body.startswith("Показатель;Значение")
    assert "Организаций;2" in body
    assert "Чего эти числа не значат" in body
    for note in _metrics(client, staff)["notes"]:
        assert note in body


def test_looking_at_metrics_is_written_only_in_the_service_journal(client, db_session,
                                                                    register):
    """Сводка — платформенный взгляд, а не визит к клиенту: запись в журнале каждой
    организации при каждом обновлении экрана утопила бы сигнал «к нам приходили»."""
    staff = _staff(client, db_session, register)
    owner = register(email="a@e.ru", org="Первая")
    org = _org_id(client, owner)

    client.get("/api/v1/admin/metrics", headers=staff)
    client.get("/api/v1/admin/metrics.csv", headers=staff)

    theirs = client.get(f"/api/v1/organizations/{org}/audit-log",
                        headers=owner).json()["entries"]
    assert not [e for e in theirs if e["action"].startswith("staff.")]
    ours = {e["action"] for e in
            client.get("/api/v1/admin/log", headers=staff).json()["entries"]}
    assert {"staff.metrics", "staff.metrics_export"} <= ours
