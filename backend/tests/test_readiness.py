"""Готовность установки (пакет G, G9).

Решения владельца (почта, события, трекер, реквизиты продавца) кодом не принимаются —
пакет делает выключенное **видимым**. Проверяются обещания:

* по каждому пункту — состояние, **что из-за него не работает** и чем включить; пункт
  в порядке — без «что не работает»;
* выключенное по решению («сбор событий не включён») — не проблема, а «выключено»;
  ошибка настройки (неверный DSN, опечатка в реквизитах, порог вне 1–59) — проблема;
* планировщик судится по **следам запусков**: «ни разу» — не «давно», а давность
  называется числом;
* проверка **ничего не меняет** — ни окружения, ни базы;
* экран и скрипт эксплуатации — одна функция; маршрут — только для сотрудников.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import crud, readiness, scheduler
from app.billing import ManualPaymentProvider, UnavailablePaymentProvider

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _items(db, provider=None, now=NOW) -> dict[str, readiness.ReadinessItem]:
    return {i.key: i for i in readiness.check(db, provider=provider or
                                              ManualPaymentProvider(), now=now)}


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("MAIL_BACKEND", "PUBLIC_URL", "USAGE_EVENTS", "SENTRY_DSN",
                "ANNUAL_DISCOUNT_PERCENT", "STUCK_JOB_ALERT_MINUTES", "SMTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    for var, _ in readiness.closing_docs.SELLER_ENV.values():
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_every_item_says_what_does_not_work_and_how_to_turn_it_on(db_session, clean_env):
    items = _items(db_session)
    assert {"mail", "public_url", "events", "scheduler", "tracker", "payments", "seller",
            "discount", "auto_renew", "stuck"} <= set(items)
    for item in items.values():
        assert item.status in ("ok", "off", "problem"), item.key
        if item.status != "ok":
            assert item.impact and item.how, item.key
    assert items["mail"].status == "off" and "письма" in items["mail"].impact


def test_a_decision_is_off_not_a_problem(db_session, clean_env):
    """Сбор событий выключен по умолчанию — это решение владельца, а не поломка."""
    assert _items(db_session)["events"].status == "off"


def test_configuration_mistakes_are_problems(db_session, clean_env):
    clean_env.setenv("SENTRY_DSN", "это не адрес")
    readiness.error_tracking.init_error_tracking(component="api")
    clean_env.setenv("STUCK_JOB_ALERT_MINUTES", "90")
    clean_env.setenv("ANNUAL_DISCOUNT_PERCENT", "15%")
    clean_env.setenv("SELLER_NAME", "ООО «Платформа»")
    items = _items(db_session)
    for key in ("tracker", "stuck", "discount", "seller"):
        assert items[key].status == "problem", key
    clean_env.delenv("SENTRY_DSN")
    readiness.error_tracking.init_error_tracking(component="api")


def test_memory_mail_in_production_is_a_problem(db_session, clean_env):
    """Режим «в память» — для тестов: в продакшене письма в нём никуда не уходят."""
    clean_env.setenv("MAIL_BACKEND", "memory")
    clean_env.setenv("APP_ENV", "production")
    assert _items(db_session)["mail"].status == "problem"


def test_smtp_without_a_host_is_a_problem(db_session, clean_env):
    clean_env.setenv("MAIL_BACKEND", "smtp")
    assert _items(db_session)["mail"].status == "problem"


def test_payments_off_in_production_names_the_invoice_way(db_session, clean_env):
    item = _items(db_session, provider=UnavailablePaymentProvider())["payments"]
    assert item.status == "off" and "по счёту" in item.impact


# --- Планировщик ---

def test_a_scheduler_that_never_ran_is_named_so(db_session, clean_env):
    item = _items(db_session)["scheduler"]
    assert item.status == "problem" and "ни разу" in item.state


def test_a_stale_scheduler_names_the_age(db_session, clean_env, monkeypatch):
    for task in scheduler.TASKS:
        scheduler.record_run(db_session, task, "проверка")
    assert _items(db_session, now=datetime.now(timezone.utc))["scheduler"].status == "ok"
    later = datetime.now(timezone.utc) + timedelta(hours=30)
    item = _items(db_session, now=later)["scheduler"]
    assert item.status == "problem" and "ч назад" in item.state


# --- Ничего не меняет, одна функция, только сотрудникам ---

def test_the_check_changes_nothing(db_session, clean_env):
    before_env = dict(os.environ)
    before_log = len(crud.list_staff_log(db_session, limit=1000))
    _items(db_session)
    assert dict(os.environ) == before_env
    assert len(crud.list_staff_log(db_session, limit=1000)) == before_log


def test_the_route_is_for_staff_only(client, register, db_session, clean_env):
    client_headers = register(email="client@e.ru", org="Клиент")
    assert client.get("/api/v1/admin/readiness", headers=client_headers).status_code == 403
    support = register(email="support@platform.ru", org="Платформа")
    crud.set_staff(db_session, crud.get_user_by_email(db_session, "support@platform.ru"),
                   is_staff=True, role="support")
    items = client.get("/api/v1/admin/readiness", headers=support).json()
    assert {"mail", "scheduler", "seller"} <= {i["key"] for i in items}


def test_the_script_uses_the_same_function_and_fails_on_problems(tmp_path):
    """Скрипт для эксплуатации — та же проверка; код выхода 1, если есть проблема."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "check_readiness.py").read_text()
    assert "readiness.check(" in source
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'r.db'}",
           "MAIL_BACKEND": "smtp", "SMTP_HOST": ""}
    r = subprocess.run([sys.executable, "scripts/check_readiness.py"], cwd=root, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1 and "Почта" in r.stdout
