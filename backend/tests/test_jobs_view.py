"""Видно, что зависло (ADMIN-PHASE-F, F3).

`AnalysisJob` хранил только владение, а состояние живёт в Celery — и опросить задачу
можно было **только по её идентификатору и только своим арендатором**. Значит зависшая
или упавшая задача не видна никому: ни клиенту (он ушёл с экрана), ни платформе, и
первый зависший Монте-Карло платформа узнавала от клиента по телефону.

Проверяются два правила честности и одна граница:

* **молчание сети — не отказ задачи**: недоступное хранилище результатов даёт
  «неизвестно» с причиной, а не «упало» и не 500;
* **истёкший результат — не «в очереди»**: Celery хранит результат час и потом отвечает
  о посчитанной задаче так же, как о несуществующей;
* **результата задачи в ответе нет** — это содержимое модели клиента (правило 6).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import crud, job_state


def _staff(client, db_session, register, email="staff@e.ru") -> dict:
    headers = register(email=email, org="Наша платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, email), is_staff=True)
    return headers


def _client_org(client, register, email="client@e.ru", org="ООО «Клиент»") -> tuple:
    headers = register(email=email, org=org)
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    return headers, org_id


def _job(db, org_id, job_id="job-1", *, kind="monte_carlo", age_minutes=0):
    row = crud.create_analysis_job(db, job_id, org_id, "p1", kind)
    if age_minutes:
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
        db.commit()
    return row


def _jobs(client, staff, **params) -> dict:
    return client.get("/api/v1/admin/jobs", params=params, headers=staff).json()


# --- Правила честности (чистые функции, без брокера) ---

def test_silence_of_the_broker_is_not_a_failed_task():
    """«Упало» и «мы не знаем» — разные утверждения, и второе нельзя показывать как
    первое: задача могла и посчитаться."""
    verdict = job_state.interpret(None)
    assert verdict.status == "unknown"
    assert "молчание сети" in verdict.note


def test_an_expired_result_is_not_queued():
    """Celery хранит результат час и потом отвечает о посчитанной задаче так же, как о
    несуществующей. «В очереди» здесь было бы неправдой."""
    now = datetime.now(timezone.utc)
    old = now - job_state.RESULT_TTL - timedelta(minutes=1)

    assert job_state.interpret("PENDING", created_at=old, now=now).status == "unknown"
    assert "срок хранения" in job_state.interpret("PENDING", created_at=old,
                                                  now=now).note
    # Свежая задача в очереди остаётся в очереди — правило не съедает нормальный случай.
    fresh = now - timedelta(minutes=5)
    assert job_state.interpret("PENDING", created_at=fresh, now=now).status == "pending"


def test_unknown_never_comes_without_a_reason():
    """«Неизвестно» без причины неотличимо от поломки."""
    for state, created in ((None, None),
                           ("PENDING", datetime.now(timezone.utc) - timedelta(days=1))):
        verdict = job_state.interpret(state, created_at=created)
        assert verdict.status == "unknown" and verdict.note


def test_known_states_pass_through():
    assert job_state.interpret("SUCCESS").status == "success"
    assert job_state.interpret("STARTED").status == "running"
    assert job_state.interpret("FAILURE", error="boom").error == "boom"


def test_poll_does_not_let_a_broken_broker_raise():
    """Падение чужого хозяйства не должно ронять наш запрос."""
    def angry(_job_id):
        raise RuntimeError("redis отказал")

    assert job_state.poll("x", angry) == (None, None)


def test_age_is_a_number_not_soon():
    now = datetime.now(timezone.utc)
    assert job_state.age_minutes(now - timedelta(minutes=40), now) == 40


# --- Служебный список ---

def test_the_operator_sees_what_is_running(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _job(db_session, org_id, age_minutes=40)

    body = _jobs(client, staff)
    assert body["total"] == 1
    row = body["jobs"][0]
    assert row["organization_name"] == "ООО «Клиент»"
    assert row["kind"] == "monte_carlo"
    assert row["age_minutes"] == 40           # «в очереди 40 минут» — это и есть сигнал


def test_the_window_is_a_window(client, register, db_session):
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _job(db_session, org_id, "old", age_minutes=60 * 48)
    _job(db_session, org_id, "new", age_minutes=10)

    assert [j["id"] for j in _jobs(client, staff, hours=24)["jobs"]] == ["new"]
    assert {j["id"] for j in _jobs(client, staff, hours=24 * 7)["jobs"]} == {"old", "new"}


def test_the_result_of_a_task_is_not_in_the_response(client, register, db_session):
    """Числа Монте-Карло — содержимое модели клиента, и правило 6 на них
    распространяется: открываются они только по гранту (F4).

    Проверка идёт по **всему тексту** ответа, как у границы B1: поле, добавленное «на
    всякий случай», провалит её сразу.
    """
    staff = _staff(client, db_session, register)
    _owner, org_id = _client_org(client, register)
    _job(db_session, org_id)

    text = client.get("/api/v1/admin/jobs", headers=staff).text
    for word in ("npv", "irr", "percentile", "result", "samples"):
        assert word not in text.lower(), word


def test_the_caveats_travel_with_the_list(client, register, db_session):
    staff = _staff(client, db_session, register)
    notes = " ".join(_jobs(client, staff)["notes"])

    assert "молчание хранилища результатов" in notes
    assert "только по его гранту" in notes
    assert "не чистится" in notes             # строки не удаляются никогда


def test_an_outsider_sees_no_jobs(client, auth_headers):
    assert client.get("/api/v1/admin/jobs", headers=auth_headers).status_code == 403


def test_looking_at_jobs_is_not_power(client, register, db_session):
    """Список — наблюдение: разбирает его поддержка, а не только оператор (F5)."""
    from app.db_models import STAFF_SUPPORT

    headers = register(email="s@e.ru", org="Платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "s@e.ru"),
                   is_staff=True, role=STAFF_SUPPORT)
    assert client.get("/api/v1/admin/jobs", headers=headers).status_code == 200


# --- Клиентский маршрут: тот же отказ, та же причина ---

def test_a_broken_broker_does_not_become_a_client_error(client, register, db_session,
                                                        monkeypatch):
    """Раньше запрос к упавшему хранилищу результатов давал 500, и клиент видел «не
    удалось загрузить» — сообщение о поломке продукта там, где замолчало соседнее
    хозяйство."""
    from app.routers import jobs as jobs_router

    owner, org_id = _client_org(client, register)
    _job(db_session, org_id, "job-x")

    def angry(_job_id):
        raise RuntimeError("redis отказал")

    monkeypatch.setattr(jobs_router, "fetch_state", angry)
    r = client.get("/api/v1/analysis/jobs/job-x",
                   headers={**owner, "X-Organization-Id": org_id})

    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
    assert "молчание сети" in r.json()["note"]


def test_someone_elses_job_is_still_invisible(client, register, db_session):
    """У таблицы нет RLS-политики (названо в `NO_RLS_POLICY`), и видимость держит
    явная проверка организации в маршруте — значит она обязана работать."""
    _owner, mine = _client_org(client, register)
    alien, _theirs = _client_org(client, register, email="alien@e.ru", org="Чужая")
    _job(db_session, mine, "job-mine")

    assert client.get("/api/v1/analysis/jobs/job-mine",
                      headers=alien).status_code == 404


def test_one_door_to_celery():
    """Обёртка вокруг `AsyncResult` одна на оба маршрута: вторая однажды забыла бы
    ловить отказ брокера — ровно то, из-за чего клиент и видел 500."""
    import inspect

    from app.routers import admin, jobs

    assert "AsyncResult" in inspect.getsource(jobs.fetch_state)
    assert "AsyncResult" not in inspect.getsource(admin)
    assert "fetch_state" in inspect.getsource(admin.list_jobs)
