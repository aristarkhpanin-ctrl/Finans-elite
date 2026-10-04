"""Настройки установки доходят до контейнеров (пакет K, K6).

`docker-compose.yml` передаёт контейнерам окружение **явным перечнем** (`x-backend-env`), а
`.env` рядом с ним подставляется только в сам файл. До K6 в перечне не было ни почты, ни
реквизитов продавца, ни скидки за год, ни сбора событий, ни трекера ошибок: владелец,
вписавший `MAIL_BACKEND=smtp` в `.env`, получал молча выключенную почту — и отказ
«почта не настроена», противоречащий его же настройке.

Перечень — вторая копия списка переменных, поэтому его стережёт этот тест: всё, что
читает приложение, должно быть в перечне (или в исключениях с причиной). Compose
передаёт незаданное как пустую строку — отсюда второе правило: пустое значение равно
незаданному (`app/env.py`), и ни один разбор на нём не падает.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

from app import billing, closing_docs, error_tracking, mail, scheduler

ROOT = Path(__file__).resolve().parents[2]
APP = Path(__file__).resolve().parents[1] / "app"

#: Читаются приложением, но установке не передаются — с причиной.
NOT_PASSED: dict[str, str] = {
    "CELERY_TASK_ALWAYS_EAGER": "режим «сразу» — для тестов и съёмки матрицы; на установке "
                                "очередь настоящая (воркер и Redis)",
}


def compose_env() -> dict[str, str]:
    """Перечень `x-backend-env`: имя → значение-подстановка."""
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = text.split("x-backend-env: &backend-env", 1)[1].split("\nservices:", 1)[0]
    return dict(re.findall(r"^  ([A-Z][A-Z0-9_]+): (.+)$", block, re.MULTILINE))


def app_env() -> set[str]:
    """Переменные, которые читает приложение: литералы в вызовах и именованные константы."""
    names: set[str] = set()
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        names |= set(re.findall(r'(?:getenv|env|env_int|env_float)\(\s*"([A-Z][A-Z0-9_]+)"', text))
    names |= {error_tracking.DSN_ENV, billing.DISCOUNT_ENV, scheduler.STUCK_ENV}
    names |= {var for var, _ in closing_docs.SELLER_ENV.values()}
    return names


def test_the_scan_sees_the_settings():
    """Сторож самой выборки: пустая выборка выглядела бы зелёным тестом."""
    assert {"MAIL_BACKEND", "SELLER_INN", "ANNUAL_DISCOUNT_PERCENT", "USAGE_EVENTS",
            "SENTRY_DSN", "JWT_SECRET", "SMTP_PORT"} <= app_env()
    assert len(compose_env()) > 30


def test_every_setting_the_app_reads_reaches_the_containers():
    missing = sorted(app_env() - set(compose_env()) - set(NOT_PASSED))
    assert not missing, ("приложение читает, а docker-compose.yml не передаёт контейнерам: "
                         + ", ".join(missing))


def test_exceptions_are_still_read_and_not_passed():
    assert set(NOT_PASSED) <= app_env()
    assert not set(NOT_PASSED) & set(compose_env())


def test_unset_settings_arrive_empty_and_break_nothing(monkeypatch):
    """Как придёт незаданное на установке: `${X:-}` — пустая строка. Умолчания кода
    действуют, а не падают на `int("")` при импорте и при отправке письма."""
    for name, value in compose_env().items():
        if value == "${%s:-}" % name:
            monkeypatch.setenv(name, "")
    from app import pwned, security

    security = importlib.reload(security)
    pwned = importlib.reload(pwned)
    assert security.JWT_TTL_SECONDS > 0 and security.REMEMBER_TTL_SECONDS > 0
    assert security.INVITE_TTL_SECONDS > 0 and security.MUTE_TTL_SECONDS > 0
    assert pwned.PWNED_TIMEOUT > 0
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    host, port, _, _, mode = mail._smtp_settings()
    assert (port, mode) == (587, "starttls") and mail._timeout() == 10
    assert mail.backend() == "off" and billing.annual_discount_percent() == 0
