"""Запись через ключ доступа (OPEN-DECISIONS §3).

Возражение было верным: у записи в журнале есть автор, а «модель изменил ключ» — не
автор. Снято оно не отменой, а тем, что автор нашёлся: **автор записи — человек,
выпустивший ключ**, сам ключ идёт пометкой в той же записи, и в журнале видно обоих.
Второе возражение — «ключ переживает увольнение» — снято тем же движением, каким смена
пароля закрывает сеансы: ключ работает, пока работает его автор.

Проверяются обещания: подмены автора нет, пометка не теряется, умолчание — чтение,
перечень доступного ключу закреплён, увольнение гасит ключ, а предел частоты называет
и себя, и что делать.
"""
from __future__ import annotations

from app import apikeys, crud
from app.db_models import AuditLogEntry
from app.rbac import Perm

WRITE = sorted(p.value for p in apikeys.WRITE_PERMS)


def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def _issue(client, headers, *, scopes=None, name="Обмен с 1С") -> tuple[str, dict]:
    org = _org_id(client, headers)
    body = client.post(f"/api/v1/organizations/{org}/api-keys",
                       json={"name": name, "scopes": scopes or []},
                       headers=headers).json()
    return body["token"], body


def _as_key(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _model(client) -> dict:
    return client.get("/api/v1/sample").json()


def _entries(client, headers) -> list[dict]:
    org = _org_id(client, headers)
    return client.get(f"/api/v1/organizations/{org}/audit-log",
                      headers=headers).json()["entries"]


# --- Автор записи ---

def test_a_key_with_write_rights_creates_a_project(client, register):
    headers = register()
    token, _ = _issue(client, headers, scopes=WRITE)

    created = client.post("/api/v1/projects",
                          json={"name": "Из 1С", "model": _model(client)},
                          headers=_as_key(token))
    assert created.status_code == 201


def test_the_author_is_the_person_who_issued_the_key(client, register):
    """Так устроена ответственность за доверенность: спросить можно с выдавшего."""
    headers = register()
    token, _ = _issue(client, headers, scopes=WRITE)
    client.post("/api/v1/projects", json={"name": "Из 1С", "model": _model(client)},
                headers=_as_key(token))

    entry = next(e for e in _entries(client, headers) if e["action"] == "project.create")
    assert entry["actor_email"] == "owner@e.ru"


def test_the_key_is_named_in_the_same_entry(client, register, db_session):
    """Подмены нет: в записи видно **обоих** — и человека, и ключ. Иначе правка из
    чужого сервера читалась бы как сделанная руками."""
    headers = register()
    token, body = _issue(client, headers, scopes=WRITE, name="Обмен с 1С")
    client.post("/api/v1/projects", json={"name": "Из 1С", "model": _model(client)},
                headers=_as_key(token))

    entry = db_session.query(AuditLogEntry).filter(
        AuditLogEntry.action == "project.create").one()
    assert "Обмен с 1С" in entry.via_key and body["key"]["masked"][:-1] in entry.via_key


def test_the_mark_reaches_the_journal_the_client_reads(client, register):
    """Пометка, которую видит только база, не выполняет своего обещания: «видно обоих»
    проверяют на экране журнала и в выгрузке, куда идут при разборе инцидента."""
    headers = register()
    org = _org_id(client, headers)
    token, _ = _issue(client, headers, scopes=WRITE, name="Обмен с 1С")
    client.post("/api/v1/projects", json={"name": "Из 1С", "model": _model(client)},
                headers=_as_key(token))

    entry = next(e for e in _entries(client, headers) if e["action"] == "project.create")
    assert entry["actor_email"] == "owner@e.ru" and "Обмен с 1С" in entry["via_key"]

    csv_text = client.get(f"/api/v1/organizations/{org}/audit-log.csv",
                          headers=headers).content.decode("utf-8-sig")
    assert "Через ключ" in csv_text and "Обмен с 1С" in csv_text


def test_a_persons_own_work_carries_no_key_mark(client, register, db_session):
    """Пометка, стоящая везде, не отличает ничего."""
    headers = register()
    client.post("/api/v1/projects", json={"name": "Руками", "model": _model(client)},
                headers=headers)

    entry = db_session.query(AuditLogEntry).filter(
        AuditLogEntry.action == "project.create").one()
    assert entry.via_key == ""


def test_the_mark_reaches_routes_nobody_touched_for_it(client, register, db_session):
    """Пометка едет в сессии запроса, а не параметром: журнал пишут два десятка
    маршрутов, и в каждом её бы однажды забыли. Здесь это проверяется на деле —
    правка дела в журнал пишется тем же общим способом."""
    headers = register()
    token, _ = _issue(client, headers, scopes=WRITE)
    cid = client.post("/api/v1/audit/subjects",
                      json={"name": "Дело", "model": {"name": "Дело", "periods": [],
                                                      "lines": []}},
                      headers=_as_key(token)).json()["id"]
    client.put(f"/api/v1/audit/subjects/{cid}",
               json={"name": "Дело (обновлено)"}, headers=_as_key(token))

    marks = {e.action: e.via_key for e in db_session.query(AuditLogEntry).all()}
    assert marks["case.create"] and marks["case.update"]


# --- Что ключу можно ---

def test_reading_is_the_default_and_writing_is_asked_for(client, register):
    """Ключ живёт в чужом сервере: умолчание обязано быть тем, о чём не пожалеют."""
    headers = register()
    reader, body = _issue(client, headers)
    assert body["key"]["writes"] is False
    assert client.post("/api/v1/projects",
                       json={"name": "Нельзя", "model": _model(client)},
                       headers=_as_key(reader)).status_code == 403

    _, written = _issue(client, headers, scopes=WRITE, name="Второй")
    assert written["key"]["writes"] is True


def test_a_writing_key_still_reads(client, register):
    """Ключ, который может создать проект, но не может его прочитать, — ловушка."""
    headers = register()
    token, _ = _issue(client, headers, scopes=WRITE)
    pid = client.post("/api/v1/projects", json={"name": "Из 1С", "model": _model(client)},
                      headers=_as_key(token)).json()["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=_as_key(token)).status_code == 200


def test_deleting_and_commenting_are_never_for_a_key(client, register):
    """Удаление необратимо, а ключ работает в скрипте без человека рядом; у реплики есть
    автор, который написал слова, — «ключ сказал» не разговор."""
    assert Perm.PROJECT_DELETE not in apikeys.ALLOWED_PERMS
    assert Perm.COMMENT_WRITE not in apikeys.ALLOWED_PERMS

    headers = register()
    pid = client.post("/api/v1/projects", json={"name": "П", "model": _model(client)},
                      headers=headers).json()["id"]
    token, _ = _issue(client, headers, scopes=WRITE)

    assert client.delete(f"/api/v1/projects/{pid}", headers=_as_key(token)).status_code == 403
    assert client.post(f"/api/v1/projects/{pid}/comments", json={"body": "ключ сказал"},
                       headers=_as_key(token)).status_code == 403


def test_asking_for_rights_a_key_never_has_is_refused_by_name(client, register):
    headers = register()
    org = _org_id(client, headers)
    r = client.post(f"/api/v1/organizations/{org}/api-keys",
                    json={"name": "Всемогущий",
                          "scopes": ["project.delete", "org.manage"]},
                    headers=headers)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "project.delete" in detail and "org.manage" in detail
    # И названо, что выдать всё-таки можно: отказ без выхода отправляет гадать.
    assert "project.update" in detail


def test_a_writing_key_is_still_not_a_person(client, register):
    """Право писать модели — не право распоряжаться организацией и не право быть её
    участником."""
    headers = register()
    org = _org_id(client, headers)
    token, _ = _issue(client, headers, scopes=WRITE)

    assert client.get("/api/v1/auth/me", headers=_as_key(token)).status_code == 403
    assert client.post(f"/api/v1/organizations/{org}/members",
                       json={"email": "x@e.ru", "full_name": "Х", "role": "editor"},
                       headers=_as_key(token)).status_code == 403


def test_the_key_writable_routes_are_a_closed_list():
    """Перечень-тест: что можно ключом — это перечень маршрутов, где стоит `acting_user`.
    Новый такой маршрут обязан появиться здесь осознанно, а не заодно.

    Маршруты берутся **из роутеров продукта**, а не из `app.routes`: в этой версии
    FastAPI включённые роутеры лежат там без пути, и проверка, смотревшая туда, однажды
    уже оказалась слепой (найдено при D5).
    """
    import inspect

    from app import deps
    from tests.test_audit_log_coverage import ROUTERS

    found = set()
    for router in ROUTERS:
        for route in router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            for param in inspect.signature(endpoint).parameters.values():
                if getattr(param.default, "dependency", None) is deps.acting_user:
                    method = sorted(getattr(route, "methods", {"GET"}))[0]
                    found.add(f"{method} {route.path}")
    assert found == {
        "POST /api/v1/projects",
        "PUT /api/v1/projects/{project_id}",
        "POST /api/v1/audit/subjects",
        "PUT /api/v1/audit/subjects/{subject_id}",
    }


def test_the_scope_route_separates_always_from_grantable(client, register):
    """«Есть всегда» и «можно выдать» — разные ответы; список, где они слиты, заставляет
    гадать, что именно выбирают при выпуске."""
    headers = register()
    org = _org_id(client, headers)
    body = client.get(f"/api/v1/organizations/{org}/api-keys/scope",
                      headers=headers).json()
    assert body["always"] == sorted(p.value for p in apikeys.READ_PERMS)
    assert body["grantable"] == WRITE
    assert "уходит из организации" in body["note"]


# --- Ключ гаснет вместе с автором ---

def test_suspending_the_issuer_kills_the_key(client, register, db_session):
    """Ключ уволенного, работающий в чужом сервере, — это доступ, за который не с кого
    спросить."""
    owner = register()
    org = _org_id(client, owner)
    invite = client.post(f"/api/v1/organizations/{org}/members",
                         json={"email": "k@e.ru", "full_name": "К", "role": "admin"},
                         headers=owner).json()
    token = client.post("/api/v1/auth/activate",
                        json={"token": invite["invite_token"],
                              "password": "kollega-parol7"}).json()["access_token"]
    admin = {"Authorization": f"Bearer {token}"}
    # Ключ выпускает владелец, но от имени коллеги — через crud, как это будет выглядеть
    # у любого администратора с правом на ключи.
    colleague = crud.get_user_by_email(db_session, "k@e.ru")
    fresh = apikeys.generate()
    crud.create_api_key(db_session, org, name="Его ключ", prefix=fresh.prefix,
                        fingerprint=fresh.fingerprint, created_by=colleague.email,
                        created_by_id=colleague.id, scopes=WRITE)
    assert client.get("/api/v1/projects",
                      headers=_as_key(fresh.token)).status_code == 200
    assert admin  # коллега действительно работал

    client.post(f"/api/v1/organizations/{org}/members/{colleague.id}/block",
                json={"reason": "уволен"}, headers=owner)
    refused = client.get("/api/v1/projects", headers=_as_key(fresh.token))
    assert refused.status_code == 403 and "уволен" in refused.json()["detail"]


def test_a_key_without_an_author_says_so_instead_of_pretending(client, register,
                                                                db_session):
    """Так выглядят ключи, выпущенные до появления автора (и те, чей автор удалён).
    Доверенность без доверителя не бывает — но отказ называет причину."""
    headers = register()
    org = _org_id(client, headers)
    fresh = apikeys.generate()
    crud.create_api_key(db_session, org, name="Древний", prefix=fresh.prefix,
                        fingerprint=fresh.fingerprint, created_by="ushedshiy@e.ru")

    refused = client.get("/api/v1/projects", headers=_as_key(fresh.token))
    assert refused.status_code == 401
    assert "выпустите его заново" in refused.json()["detail"]
    assert "ushedshiy@e.ru" in refused.json()["detail"]


def test_an_authorless_key_is_visible_in_the_list_as_broken(client, register, db_session):
    """Живая строка в списке означала бы, что интеграция цела, а она стоит."""
    headers = register()
    org = _org_id(client, headers)
    fresh = apikeys.generate()
    crud.create_api_key(db_session, org, name="Древний", prefix=fresh.prefix,
                        fingerprint=fresh.fingerprint, created_by="ushedshiy@e.ru")

    listed = client.get(f"/api/v1/organizations/{org}/api-keys", headers=headers).json()
    assert listed[0]["author_gone"] is True


def test_an_old_key_without_scopes_reads_and_does_not_write(client, register, db_session):
    """Молча дописать запись ключам, которые уже лежат в чужих серверах, значило бы
    расширить доступ, которого никто не просил."""
    headers = register()
    org = _org_id(client, headers)
    owner = crud.get_user_by_email(db_session, "owner@e.ru")
    fresh = apikeys.generate()
    key = crud.create_api_key(db_session, org, name="Прежний", prefix=fresh.prefix,
                              fingerprint=fresh.fingerprint, created_by=owner.email,
                              created_by_id=owner.id)
    key.scopes = None          # так выглядит строка до миграции
    db_session.commit()

    assert client.get("/api/v1/projects", headers=_as_key(fresh.token)).status_code == 200
    assert client.post("/api/v1/projects",
                       json={"name": "Нельзя", "model": _model(client)},
                       headers=_as_key(fresh.token)).status_code == 403


# --- Предел частоты ---

def test_a_runaway_loop_is_stopped_and_told_what_to_do(client, register, monkeypatch):
    """Цикл в чужом скрипте не должен валить базу. Отказ несёт `Retry-After`: чинит
    сорвавшийся цикл обычно не человек, а сам клиент."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(apikeys, "MAX_REQUESTS_PER_MINUTE", 3)
    headers = register()
    token, _ = _issue(client, headers)

    for _ in range(3):
        assert client.get("/api/v1/projects", headers=_as_key(token)).status_code == 200
    refused = client.get("/api/v1/projects", headers=_as_key(token))
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "60"
    assert "предел на ключ" in refused.json()["detail"]


def test_the_limit_is_per_key_not_per_address(client, register, monkeypatch):
    """Ключ живёт в чужом сервере, и адрес у него один на всю интеграцию: предел по
    адресу наказывал бы соседей и ничего не говорил бы о самом ключе."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(apikeys, "MAX_REQUESTS_PER_MINUTE", 2)
    headers = register()
    first, _ = _issue(client, headers, name="Первый")
    second, _ = _issue(client, headers, name="Второй")

    for _ in range(2):
        client.get("/api/v1/projects", headers=_as_key(first))
    assert client.get("/api/v1/projects", headers=_as_key(first)).status_code == 429
    # Второй ключ с того же адреса работает: предел считается по ключу.
    assert client.get("/api/v1/projects", headers=_as_key(second)).status_code == 200


# --- Границы, которые механизм обязан пережить ---

def test_a_key_does_not_escape_the_plan_quota(client, register, db_session):
    """Квота тарифа — существующая: отдельной для ключа не нужно, и обходить её он
    не должен."""
    headers = register()
    org = _org_id(client, headers)
    crud.set_plan(db_session, org, "free")
    token, _ = _issue(client, headers, scopes=WRITE)

    refused = None
    for i in range(30):
        r = client.post("/api/v1/projects",
                        json={"name": f"П{i}", "model": _model(client)},
                        headers=_as_key(token))
        if r.status_code != 201:
            refused = r
            break
    assert refused is not None and refused.status_code == 402


def test_an_unpaid_organization_stops_a_writing_key(client, register, db_session):
    """Режим чтения и выгрузки (B2) закрывает изменение содержимого — чьей бы рукой оно
    ни делалось."""
    headers = register()
    token, _ = _issue(client, headers, scopes=WRITE)
    crud.set_plan(db_session, _org_id(client, headers), "pro", status="past_due")

    assert client.get("/api/v1/projects", headers=_as_key(token)).status_code == 200
    assert client.post("/api/v1/projects",
                       json={"name": "Нельзя", "model": _model(client)},
                       headers=_as_key(token)).status_code == 403


def test_a_key_writes_only_into_its_own_organization(client, register):
    first = register()
    token, _ = _issue(client, first, scopes=WRITE)
    stranger = register(email="alien@e.ru", org="Чужая")
    theirs = client.post("/api/v1/projects",
                         json={"name": "Чужой", "model": _model(client)},
                         headers=stranger).json()["id"]

    assert client.put(f"/api/v1/projects/{theirs}", json={"name": "Перехват"},
                      headers=_as_key(token)).status_code == 404
