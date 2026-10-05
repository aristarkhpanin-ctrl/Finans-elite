"""Активация по событиям (пакет L, L8).

Когорты регистрации по неделям: какая доля организаций **за семь дней** посчитала свою
модель и сколько времени на это ушло. Проверяется то, на чём такая метрика врёт молча:
неделя без записи событий показана нулём, незавершённая неделя — окончательной долей,
открытие пустого дела — расчётом, сотрудник платформы — самым быстрым клиентом.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import crud, usage
from app.db_models import Membership, Organization, User
from app.metrics import ACTIVATION_DAYS, _week_start, activation

#: Среда, полдень: внутри недели, чтобы «неделя назад» не пересекала границу дня.
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
THIS_WEEK = _week_start(NOW)


@pytest.fixture
def collecting(monkeypatch):
    monkeypatch.setenv("USAGE_EVENTS", "1")
    monkeypatch.setenv("USAGE_SALT", "соль-теста")


def _event(db, org: str, event: str, at: datetime, **context) -> None:
    assert usage.record(db, event=event, org_id=org, now=at, context=context) is not None


def _week(result, start: datetime):
    return next(w for w in result.weeks if w.week == start.date().isoformat())


# --- Когорта и окно ---

def test_share_counts_only_calculations_within_seven_days(db_session, collecting):
    """Посчитал через два часа — активирован; через восемь дней — нет; не считал — нет."""
    start = THIS_WEEK - timedelta(weeks=3)
    at = start + timedelta(days=1)
    _event(db_session, "fast", "signup", at)
    _event(db_session, "fast", "project.calculate", at + timedelta(hours=2))
    _event(db_session, "late", "signup", at)
    _event(db_session, "late", "project.calculate", at + timedelta(days=8))
    _event(db_session, "never", "signup", at)

    week = _week(activation(db_session, NOW, collecting=True), start)
    assert (week.signed_up, week.activated, week.complete) == (3, 1, True)
    assert week.share == pytest.approx(1 / 3)
    # Медиана — по активировавшимся: «поздний» и «не считавший» её не тянут.
    assert week.median_hours == pytest.approx(2)


def test_the_first_calculation_counts_not_the_last(db_session, collecting):
    start = THIS_WEEK - timedelta(weeks=3)
    at = start + timedelta(hours=1)
    _event(db_session, "o", "signup", at)
    _event(db_session, "o", "project.calculate", at + timedelta(hours=30))
    _event(db_session, "o", "project.calculate", at + timedelta(hours=5))
    assert _week(activation(db_session, NOW, collecting=True), start).median_hours == \
        pytest.approx(5)


def test_an_unfinished_week_is_not_a_final_share(db_session, collecting):
    """Пришли позавчера: семь дней не прошли, и «0 из 2» сейчас — не «никто не
    активировался». Доли нет, посчитавших показываем как «пока»."""
    _event(db_session, "a", "signup", NOW - timedelta(days=2))
    _event(db_session, "a", "project.calculate", NOW - timedelta(days=1))
    _event(db_session, "b", "signup", NOW - timedelta(days=2))

    result = activation(db_session, NOW, collecting=True)
    week = _week(result, THIS_WEEK)
    assert (week.signed_up, week.activated, week.complete) == (2, 1, False)
    assert week.share is None and week.median_hours is None
    # Итог — только по завершённым неделям: незавершённая его только занизила бы.
    assert result.signed_up == 0 and result.share is None


def test_a_week_is_complete_only_when_its_last_signup_had_seven_days(db_session,
                                                                     collecting):
    _event(db_session, "o", "signup", THIS_WEEK - timedelta(weeks=3))
    result = activation(db_session, NOW, collecting=True)
    last_week = _week(result, THIS_WEEK - timedelta(weeks=1))
    two_ago = _week(result, THIS_WEEK - timedelta(weeks=2))
    # Прошлая неделя кончилась в понедельник: её последнему пришедшему ещё нет 7 дней.
    assert last_week.complete is False
    assert two_ago.complete is True
    assert THIS_WEEK - timedelta(weeks=1) + timedelta(days=7 + ACTIVATION_DAYS) > NOW


def test_totals_add_up_complete_weeks(db_session, collecting):
    for k, (org, hours) in enumerate([("a", 1.0), ("b", 3.0), ("c", None)]):
        at = THIS_WEEK - timedelta(weeks=4 + k) + timedelta(hours=1)
        _event(db_session, org, "signup", at)
        if hours is not None:
            _event(db_session, org, "project.calculate", at + timedelta(hours=hours))
    result = activation(db_session, NOW, collecting=True)
    assert (result.signed_up, result.activated) == (3, 2)
    assert result.share == pytest.approx(2 / 3)
    assert result.median_hours == pytest.approx(2)


def test_an_empty_week_is_zero_not_unmeasured(db_session, collecting):
    """Сбор шёл, а регистраций не было — это ответ «ноль», а не «не измеряется»."""
    _event(db_session, "o", "signup", THIS_WEEK - timedelta(weeks=5))
    week = _week(activation(db_session, NOW, collecting=True),
                 THIS_WEEK - timedelta(weeks=3))
    assert week.signed_up == 0 and week.share is None and week.complete is True


# --- «Не измеряется» ---

def test_without_events_nothing_is_measured(db_session):
    result = activation(db_session, NOW, collecting=False)
    assert all(w.signed_up is None for w in result.weeks)
    assert result.first_event_at is None


def test_weeks_before_collection_started_are_not_measured(db_session, collecting):
    started = THIS_WEEK - timedelta(weeks=4) + timedelta(days=3)
    _event(db_session, "o", "signup", started)
    result = activation(db_session, NOW, collecting=True)
    assert _week(result, THIS_WEEK - timedelta(weeks=5)).signed_up is None
    first = _week(result, THIS_WEEK - timedelta(weeks=4))
    # Неделя начала сбора — неполная: кто пришёл в её понедельник, не записан.
    assert first.signed_up == 1 and first.partial is True
    assert _week(result, THIS_WEEK - timedelta(weeks=3)).partial is False


def test_when_collection_is_off_weeks_after_the_last_event_are_not_measured(db_session,
                                                                           collecting):
    """Когда выключили сбор, не видно; нули после последнего события читались бы как
    «никто не приходил»."""
    _event(db_session, "o", "signup", THIS_WEEK - timedelta(weeks=6))
    result = activation(db_session, NOW, collecting=False)
    assert _week(result, THIS_WEEK - timedelta(weeks=6)).signed_up == 1
    assert _week(result, THIS_WEEK - timedelta(weeks=5)).signed_up is None
    assert _week(result, THIS_WEEK).signed_up is None


# --- Что считается расчётом ---

def test_opening_an_empty_case_is_not_a_calculation(db_session, collecting):
    start = THIS_WEEK - timedelta(weeks=3)
    for org, reporting in (("empty", "empty"), ("filled", "filled")):
        _event(db_session, org, "signup", start)
        _event(db_session, org, "case.analyze", start + timedelta(hours=1),
               reporting=reporting)
    week = _week(activation(db_session, NOW, collecting=True), start)
    assert (week.signed_up, week.activated) == (2, 1)


def test_an_analysis_without_the_mark_is_not_counted_and_is_named(db_session,
                                                                  collecting):
    """Разбор, записанный до признака отчётности: пустое ли было дело, не видно."""
    start = THIS_WEEK - timedelta(weeks=3)
    _event(db_session, "old", "signup", start)
    _event(db_session, "old", "case.analyze", start + timedelta(hours=1))
    result = activation(db_session, NOW, collecting=True)
    assert _week(result, start).activated == 0
    assert result.unmarked_orgs == 1


# --- Кого не считаем ---

def _member(db, org_id: str, email: str, *, staff: bool) -> None:
    db.add(Organization(id=org_id, name=org_id))
    user = User(email=email, full_name="", is_staff=staff)
    db.add(user)
    db.flush()
    db.add(Membership(organization_id=org_id, user_id=user.id, role="owner"))
    db.commit()


def test_staff_organizations_are_excluded_and_named(db_session, collecting):
    """Сотрудник знает продукт и считает в первую минуту — посчитанный, он выглядел бы
    лучшей активацией платформы. Но выброшенное молча выглядит неизмеренным — число
    названо."""
    _member(db_session, "ours", "staff@e.ru", staff=True)
    _member(db_session, "client", "client@e.ru", staff=False)
    start = THIS_WEEK - timedelta(weeks=3)
    for org in ("ours", "client"):
        _event(db_session, org, "signup", start)
        _event(db_session, org, "project.calculate", start + timedelta(minutes=5))
    result = activation(db_session, NOW, collecting=True)
    assert _week(result, start).signed_up == 1
    assert result.staff_excluded == 1


def test_a_pilot_with_a_client_inside_is_a_client_organization(db_session, collecting):
    """Платформа завела организацию и пригласила туда клиента — она клиентская."""
    _member(db_session, "pilot", "staff@e.ru", staff=True)
    user = User(email="client@e.ru", full_name="")
    db_session.add(user)
    db_session.flush()
    db_session.add(Membership(organization_id="pilot", user_id=user.id, role="analyst"))
    db_session.commit()
    start = THIS_WEEK - timedelta(weeks=3)
    _event(db_session, "pilot", "signup", start)
    assert _week(activation(db_session, NOW, collecting=True), start).signed_up == 1


def test_demo_is_not_a_cohort(db_session, collecting):
    db_session.add(Organization(id="demo", name="Демо", is_demo=True))
    db_session.commit()
    start = THIS_WEEK - timedelta(weeks=3)
    # Новые события демо не пишутся вовсе (L2); проверяем и оставшиеся от заведения.
    from app.db_models import UsageEvent
    db_session.add(UsageEvent(organization_id="demo", event="signup", actor="",
                              context={}, created_at=start))
    db_session.commit()
    _event(db_session, "client", "signup", start)
    assert _week(activation(db_session, NOW, collecting=True), start).signed_up == 1


# --- Маршрут: разбор дела пишет признак, сводка и файл несут активацию ---

def _org_id(client, headers) -> str:
    return client.get("/api/v1/organizations", headers=headers).json()[0]["id"]


def test_case_analysis_records_whether_there_was_reporting(client, register, db_session,
                                                           collecting):
    from app.db_models import UsageEvent

    headers = register()
    empty = client.post("/api/v1/audit/subjects", json={
        "name": "Пустое", "model": {"name": "Пустое", "periods": []}},
        headers=headers).json()["id"]
    filled = client.post("/api/v1/audit/subjects/demo", headers=headers).json()["id"]
    client.post(f"/api/v1/audit/subjects/{empty}/analyze", headers=headers)
    client.post(f"/api/v1/audit/subjects/{filled}/analyze", headers=headers)

    marks = [e.context.get("reporting") for e in db_session.query(UsageEvent)
             .filter(UsageEvent.event == "case.analyze").order_by(UsageEvent.created_at)]
    assert marks == ["empty", "filled"]


def _staff(client, db_session, register) -> dict:
    headers = register(email="staff@e.ru", org="Платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "staff@e.ru"),
                   is_staff=True)
    return headers


def test_metrics_carry_activation_and_its_caveats(client, register, db_session,
                                                  collecting):
    staff = _staff(client, db_session, register)
    headers = register(email="client@e.ru", org="Клиент")
    pid = client.post("/api/v1/projects", json={"name": "П", "model":
                      client.get("/api/v1/sample").json()}, headers=headers).json()["id"]
    client.post(f"/api/v1/projects/{pid}/calculate", headers=headers)

    body = client.get("/api/v1/admin/metrics", headers=staff).json()
    act = body["activation"]
    current = act["weeks"][-1]
    # Регистрация этой недели: служебная организация не считается, клиент — да, и неделя
    # ещё не завершена — посчитавших «пока» один, доли нет.
    assert (current["signed_up"], current["activated"], current["complete"]) == (1, 1, False)
    assert current["share"] is None
    assert act["staff_excluded"] == 1
    notes = " ".join(body["notes"])
    assert "Активация — организация посчитала свою модель" in notes
    assert "не завершены" in notes and "Служебных организаций" in notes


def test_metrics_say_unmeasured_when_nothing_is_collected(client, register, db_session):
    staff = _staff(client, db_session, register)
    body = client.get("/api/v1/admin/metrics", headers=staff).json()
    assert all(w["signed_up"] is None for w in body["activation"]["weeks"])
    assert any("Активация **не измеряется**" in n for n in body["notes"])


def test_csv_names_unmeasured_and_unfinished_weeks_in_words(client, register, db_session,
                                                            collecting):
    staff = _staff(client, db_session, register)
    register(email="client@e.ru", org="Клиент")
    text = client.get("/api/v1/admin/metrics.csv", headers=staff).content.decode("utf-8-sig")
    assert "Посчитали за 7 дн." in text
    assert "не измеряется" in text          # недели до первого события
    assert "не завершена" in text           # неделя регистрации клиента
    assert "Итог по завершённым неделям" in text
