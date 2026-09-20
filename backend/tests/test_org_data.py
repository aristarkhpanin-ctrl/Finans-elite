"""Организация может забрать всё и уйти (ADMIN-PHASE-F, F6).

У человека права 152-ФЗ закрыты (C3), у **организации** не было ни выгрузки, ни
удаления: закрыть компанию можно было только уничтожив заодно учётную запись её
последнего владельца.

Проверяются обещания, а не форма: выгрузка несёт **модели целиком** и называет, чего в
ней нет; удаление требует пароля **владельца**, собирает план заново и стирает всё;
участники живы; платформа видит уход клиента. И перечень-тест, из-за которого F6
началась: **состав удаления сверяется со списком таблиц** — шесть таблиц, заведённых
после C3, в нём отсутствовали.
"""
from __future__ import annotations

from app import crud
from app.database import Base


def _owner(client, register, email="owner@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _member(client, register, owner, org_id, email="analyst@e.ru", role="analyst") -> dict:
    headers = register(email=email, org=f"Личная {email}")
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": email, "full_name": "А", "role": role}, headers=owner)
    return {**headers, "X-Organization-Id": org_id}


def _project(client, headers, name="Покупка завода") -> str:
    model = client.get("/api/v1/sample").json()
    model["header"]["name"] = name
    return client.post("/api/v1/projects", json={"name": name, "model": model},
                       headers=headers).json()["id"]


def _case(client, headers, name="Цель поглощения") -> str:
    return client.post("/api/v1/audit/subjects", json={"name": name, "model": {
        "name": name, "periods": [], "lines": []}}, headers=headers).json()["id"]


def _export(client, headers, org_id) -> dict:
    return client.get(f"/api/v1/organizations/{org_id}/export", headers=headers).json()


def _preview(client, headers, org_id):
    return client.get(f"/api/v1/organizations/{org_id}/delete-preview", headers=headers)


def _delete(client, headers, org_id, password="secret123"):
    return client.request("DELETE", f"/api/v1/organizations/{org_id}",
                          json={"password": password}, headers=headers)


# --- Выгрузка ---

def test_the_export_carries_the_models_themselves(client, register):
    """Ради этого выгрузку и просят: не список названий, а модели целиком."""
    owner, org_id = _owner(client, register)
    _project(client, owner)
    _case(client, owner)

    body = _export(client, owner, org_id)
    assert body["проекты"][0]["модель"]["header"]["name"] == "Покупка завода"
    assert body["дела"][0]["название"] == "Цель поглощения"


def test_the_export_explains_itself(client, register):
    """Файл уедет к клиенту без нас, и приложить оговорку к нему больше будет негде."""
    owner, org_id = _owner(client, register)
    about = " ".join(_export(client, owner, org_id)["о_выгрузке"]["что_внутри"])

    assert "Результатов расчётов внутри нет" in about
    assert "Файлов внутри нет" in about          # хранилища у платформы нет вовсе
    assert "Секретов ключей доступа" in about


def test_the_export_holds_no_key_secrets(client, register):
    """Платформа хранит лишь отпечатки ключей и показать ключ не может — ни клиенту,
    ни себе. Выгрузка не должна выглядеть местом, где он вдруг нашёлся."""
    owner, org_id = _owner(client, register)
    token = client.post(f"/api/v1/organizations/{org_id}/api-keys",
                        json={"name": "Выгрузка в BI"}, headers=owner).json()["token"]

    body = client.get(f"/api/v1/organizations/{org_id}/export", headers=owner)
    assert token not in body.text
    assert body.json()["ключи_доступа"][0]["имя"] == "Выгрузка в BI"


def test_the_export_carries_the_journal_and_the_members(client, register):
    owner, org_id = _owner(client, register)
    _member(client, register, owner, org_id)

    body = _export(client, owner, org_id)
    assert {m["адрес"] for m in body["участники"]} == {"owner@e.ru", "analyst@e.ru"}
    assert any(e["действие"] == "member.add" for e in body["журнал_доступа"])


def test_the_export_is_written_into_the_journal(client, register):
    """Вынос данных наружу — событие (правило 5 пакета)."""
    owner, org_id = _owner(client, register)
    _export(client, owner, org_id)

    log = client.get(f"/api/v1/organizations/{org_id}/audit-log",
                     headers=owner).json()["entries"]
    assert any(e["действие" if "действие" in e else "action"] == "org.export" for e in log)


def test_an_ordinary_member_cannot_take_everything(client, register):
    """Выгрузка организации — это её данные целиком; забирает их тот, кто за неё
    отвечает, а не всякий, кто в ней работает."""
    owner, org_id = _owner(client, register)
    analyst = _member(client, register, owner, org_id)

    assert client.get(f"/api/v1/organizations/{org_id}/export",
                      headers=analyst).status_code == 403


# --- Предпросмотр удаления ---

def test_the_preview_counts_what_will_disappear(client, register):
    owner, org_id = _owner(client, register)
    _project(client, owner)
    _project(client, owner, name="Второй")
    _case(client, owner)

    plan = _preview(client, owner, org_id).json()
    assert plan["projects"] == 2 and plan["cases"] == 1
    assert plan["allowed"] is True


def test_the_preview_names_who_is_left_without_an_organization(client, register):
    """Для такого участника это не «выход из компании», а пустой продукт при следующем
    входе — и сказать об этом надо до нажатия."""
    owner, org_id = _owner(client, register)
    # У приглашённого своей организации нет: добавляем его, не регистрируя отдельно.
    client.post(f"/api/v1/organizations/{org_id}/members",
                json={"email": "invited@e.ru", "full_name": "П", "role": "analyst"},
                headers=owner)

    plan = _preview(client, owner, org_id).json()
    assert plan["members"] == 2
    # Оба: и приглашённый, и сам владелец — у него эта организация тоже единственная.
    # Вычесть себя из числа значило бы показать «останется один» тому, кто сам
    # останется без организаций и увидит пустой продукт сразу после нажатия.
    assert plan["members_left_homeless"] == 2
    assert any("единственная организация" in k for k in plan["kept"])


def test_the_preview_names_what_survives(client, register):
    """Пустым `kept` не бывает: «удалим всё» без списка исключений — неправда."""
    owner, org_id = _owner(client, register)
    kept = " ".join(_preview(client, owner, org_id).json()["kept"])

    assert "Учётные записи участников" in kept
    assert "служебного журнала" in kept
    assert "не возвращается" in kept          # оплаченный период


def test_only_the_owner_sees_the_preview(client, register):
    owner, org_id = _owner(client, register)
    admin = _member(client, register, owner, org_id, email="adm@e.ru", role="admin")

    r = _preview(client, admin, org_id)
    assert r.status_code == 403
    assert "только её владелец" in r.json()["detail"]


# --- Удаление ---

def test_deletion_requires_the_password(client, register):
    """Это ровно то, что сделает дорвавшийся до открытой вкладки."""
    owner, org_id = _owner(client, register)
    assert _delete(client, owner, org_id, password="не тот").status_code == 400
    assert client.get(f"/api/v1/organizations/{org_id}",
                      headers=owner).status_code == 200


def test_an_admin_cannot_close_the_company(client, register):
    """Администратор ведёт участников и справочники; закрытие компании — решение того,
    кто за неё платит."""
    owner, org_id = _owner(client, register)
    admin = _member(client, register, owner, org_id, email="adm@e.ru", role="admin")

    assert _delete(client, admin, org_id).status_code == 403


def test_deletion_removes_the_organization_and_its_models(client, register):
    owner, org_id = _owner(client, register)
    pid = _project(client, owner)
    _case(client, owner)

    r = _delete(client, owner, org_id)
    assert r.status_code == 200 and r.json()["projects"] == 1

    assert client.get(f"/api/v1/organizations/{org_id}", headers=owner).status_code == 403
    # У владельца организаций больше нет — продукт отвечает этим, а не «нет доступа»:
    # «вы не состоите в организации» это правда, а 403 отправил бы искать права.
    gone = client.get(f"/api/v1/projects/{pid}",
                      headers={**owner, "X-Organization-Id": org_id})
    assert gone.status_code == 400 and "не состоит" in gone.json()["detail"]
    assert client.get("/api/v1/organizations", headers=owner).json() == []


def test_the_report_is_gathered_anew_not_replayed(client, register, db_session):
    """Между «показали» и «сделали» проходит время: показать одно, а стереть другое —
    худший исход необратимого действия."""
    owner, org_id = _owner(client, register)
    before = _preview(client, owner, org_id).json()
    assert before["projects"] == 0
    _project(client, owner)

    assert _delete(client, owner, org_id).json()["projects"] == 1


def test_members_survive_the_organization(client, register):
    """Учётная запись принадлежит человеку, а не компании."""
    owner, org_id = _owner(client, register)
    _member(client, register, owner, org_id)
    _delete(client, owner, org_id)

    r = client.post("/api/v1/auth/login",
                    json={"email": "analyst@e.ru", "password": "secret123"})
    assert r.status_code == 200


def test_the_platform_sees_that_a_client_left(client, register, db_session):
    """Журнал организации уходит вместе с ней — записать «вас больше нет» некуда.
    Значит событие обязано попасть в служебный журнал: уход клиента платформа видеть
    обязана."""
    owner, org_id = _owner(client, register)
    _delete(client, owner, org_id)

    staff_email = "staff@e.ru"
    staff = register(email=staff_email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, staff_email),
                   is_staff=True)
    entries = client.get("/api/v1/admin/log", headers=staff).json()["entries"]
    row = next(e for e in entries if e["action"] == "org.delete")
    assert row["organization_name"] == "ООО «Клиент»"


def test_a_neighbours_data_is_untouched(client, register):
    """Удаление идёт **внутри арендатора**: запрос без него стёр бы на PostgreSQL ноль
    строк, а с чужим фильтром — чужие."""
    owner, mine = _owner(client, register)
    alien, theirs = _owner(client, register, email="alien@e.ru", org="Чужая")
    _project(client, alien, name="Чужой проект")
    _delete(client, owner, mine)

    kept = client.get("/api/v1/projects", headers=alien).json()
    assert [p["name"] for p in kept] == ["Чужой проект"]
    assert client.get(f"/api/v1/organizations/{theirs}", headers=alien).status_code == 200


# --- Перечень: что стирается вместе с организацией ---

def test_every_table_of_an_organization_is_either_purged_or_named():
    """Перечень-тест, из-за которого F6 и началась.

    Удаление организации перечисляет таблицы руками, и таблица, заведённая позже,
    выпадает из него **молча**: организация исчезает, а её строки остаются висеть на
    несуществующем арендаторе — под RLS их уже никто не увидит, а ключ доступа к API и
    грант поддержки при этом продолжат существовать. Так и случилось: после C3 завели
    шесть таблиц с `organization_id`, и ни одна в список не попала.

    Теперь каждая обязана быть либо в составе удаления, либо в списке оставляемых —
    с причиной. Третьего состояния нет.
    """
    from app.personal_data import KEPT_AFTER_ORGANIZATION, PURGED_WITH_ORGANIZATION

    with_org = {m.class_.__tablename__ for m in Base.registry.mappers
                if hasattr(m.class_, "organization_id")}
    purged = {m.__tablename__ for m in PURGED_WITH_ORGANIZATION}
    named = purged | set(KEPT_AFTER_ORGANIZATION)

    assert with_org - named == set(), (
        "эти таблицы привязаны к организации и не названы ни в составе удаления, ни в "
        "списке оставляемых: " + ", ".join(sorted(with_org - named)))
    assert purged & set(KEPT_AFTER_ORGANIZATION) == set()
    assert all(reason for reason in KEPT_AFTER_ORGANIZATION.values())


def test_deletion_leaves_no_rows_behind(client, register, db_session):
    """Перечень проверяет намерение, этот тест — исполнение: после удаления ни одна
    таблица не должна помнить организацию, кроме названных оставленными."""
    from app.personal_data import KEPT_AFTER_ORGANIZATION

    owner, org_id = _owner(client, register)
    _project(client, owner)
    _case(client, owner)
    client.post(f"/api/v1/organizations/{org_id}/api-keys",
                json={"name": "Ключ"}, headers=owner)
    client.post(f"/api/v1/organizations/{org_id}/support-access",
                json={"hours": 24, "reason": "разбор обращения"}, headers=owner)
    client.put(f"/api/v1/organizations/{org_id}/checklists",
               json=[{"name": "Проверки", "scope": "", "items": ["раз"]}], headers=owner)
    _delete(client, owner, org_id)

    left = []
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if not hasattr(model, "organization_id"):
            continue
        if model.__tablename__ in KEPT_AFTER_ORGANIZATION:
            continue
        rows = db_session.query(model).filter(
            model.organization_id == org_id).count()
        if rows:
            left.append(f"{model.__tablename__}: {rows}")
    assert left == [], "остались строки удалённой организации: " + ", ".join(left)
