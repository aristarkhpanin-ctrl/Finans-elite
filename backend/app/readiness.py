"""Готовность установки (пакет G, G9): что включено, что нет и что из-за этого не работает.

Решения владельца установки — почта, сбор событий, трекер ошибок, реквизиты продавца —
кодом не принимаются. Пакет G делает выключенное **видимым**: по каждому пункту здесь
сказано, в каком он состоянии, **что из-за этого не работает** и чем это включить.

Три правила:

* **Выключенное по решению — не проблема.** «Сбор событий не включён» — выбор владельца,
  и красить его красным значило бы подталкивать к решению, которое продукт принимать не
  вправе. Проблема — это ошибка настройки: неверный адрес трекера, опечатка в реквизитах,
  порог вне допустимого, почта «в память» в продакшене.
* **Проверка ничего не меняет** — ни окружения, ни базы: она только читает. Экран
  служебного раздела и скрипт эксплуатации (``scripts/check_readiness.py``) зовут одну
  функцию :func:`check`, второй копии перечня нет.
* **Пункт, который не удалось проверить, — проблема с причиной**, а не «в порядке»: база
  без таблиц или недоступная — не повод промолчать.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import billing, closing_docs, error_tracking, mail, scheduler, usage
from .billing import PaymentProvider

OK, OFF, PROBLEM = "ok", "off", "problem"


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    title: str
    status: str
    #: Что сейчас — словами («выключена», «включена: smtp, mail.example.ru»).
    state: str
    #: Что из-за этого не работает. Пусто — всё работает.
    impact: str = ""
    #: Чем включить или исправить.
    how: str = ""


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


# --- Пункты ---

_MAIL_IMPACT = ("не уходят приглашения, восстановление пароля, письма о деньгах, "
                "предупреждения об автопродлении, оповещения о зависших задачах; "
                "автопродление недоступно")


def _mail() -> ReadinessItem:
    kind = mail.backend()
    title = "Почта"
    if kind == "off":
        return ReadinessItem("mail", title, OFF, "выключена", _MAIL_IMPACT,
                             "MAIL_BACKEND=smtp и SMTP_* (см. .env.example)")
    if kind == "memory":
        if _production():
            return ReadinessItem("mail", title, PROBLEM,
                                 "«в память» — режим тестов, письма никуда не уходят",
                                 _MAIL_IMPACT, "MAIL_BACKEND=smtp и SMTP_*")
        return ReadinessItem("mail", title, OK, "«в память» (разработка)")
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return ReadinessItem("mail", title, PROBLEM, "smtp без SMTP_HOST", _MAIL_IMPACT,
                             "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")
    return ReadinessItem("mail", title, OK, f"smtp: {host}")


def _public_url() -> ReadinessItem:
    url = mail.public_url()
    title = "Публичный адрес"
    if url:
        return ReadinessItem("public_url", title, OK, url)
    status = PROBLEM if mail.mail_enabled() else OFF
    return ReadinessItem("public_url", title, status, "не задан",
                         "в письмах вместо ссылок названы разделы словами — перейти по "
                         "письму в нужное место нельзя", "PUBLIC_URL=https://…")


def _events() -> ReadinessItem:
    if usage.collecting():
        if not os.getenv("USAGE_SALT", "").strip():
            # Сбор включён решением владельца — значит, и ряды удержания ему нужны: соль,
            # взятая у ключа токенов, рвёт их при первой же смене ключа (все участники
            # станут «новыми»), и узнали бы об этом по сломанной сводке, а не здесь.
            return ReadinessItem("events", "События пользования", PROBLEM,
                                 "собираются, но соль отпечатков не задана — взят ключ "
                                 "токенов JWT_SECRET",
                                 "смена JWT_SECRET порвёт ряды удержания: все участники "
                                 "станут «новыми»",
                                 "USAGE_SALT — случайная строка от 32 символов, отдельная "
                                 "от JWT_SECRET")
        return ReadinessItem("events", "События пользования", OK, "собираются")
    return ReadinessItem("events", "События пользования", OFF, "не собираются",
                         "удержание на сводке платформы — «не измеряется»",
                         "USAGE_EVENTS=1 — решение владельца установки")


#: Как давно должен был пройти запуск: суточные задачи — сутки с запасом, частая —
#: два часа (без новостей она пишет след раз в час).
_FRESH = {"stuck": timedelta(hours=2)}
_DAILY = timedelta(hours=26)


def _scheduler(db: Session, now: datetime) -> ReadinessItem:
    runs = scheduler.last_runs(db)
    title = "Планировщик"
    how = "сервис beat в docker-compose — ровно один процесс, и воркер Celery"
    impact = ("не идут сверка неоплаты, письма о деньгах, автопродление, акты и проверка "
              "зависших задач")
    never = sorted(task for task, moment in runs.items() if moment is None)
    if never:
        return ReadinessItem("scheduler", title, PROBLEM,
                             "ни разу не запускались: " + ", ".join(never), impact, how)
    stale = []
    for task, moment in runs.items():
        assert moment is not None
        age = now - _aware(moment)
        if age > _FRESH.get(task, _DAILY):
            stale.append(f"{task} — {int(age.total_seconds() // 3600)} ч назад")
    if stale:
        return ReadinessItem("scheduler", title, PROBLEM,
                             "давно не запускались: " + "; ".join(stale), impact, how)
    return ReadinessItem("scheduler", title, OK, "все задачи запускаются по расписанию")


def _tracker() -> ReadinessItem:
    state = error_tracking.state()
    title = "Трекер ошибок"
    if state.enabled:
        return ReadinessItem("tracker", title, OK, "включён")
    configured = bool(os.getenv(error_tracking.DSN_ENV, "").strip())
    return ReadinessItem("tracker", title, PROBLEM if configured else OFF, state.reason,
                         "об ошибках платформа узнаёт из логов процесса или от клиента",
                         "SENTRY_DSN (Sentry или GlitchTip у себя)")


def _payments(provider: PaymentProvider) -> ReadinessItem:
    kind = billing.provider_kind(provider)
    title = "Оплата в продукте"
    if kind == "yookassa":
        return ReadinessItem("payments", title, OK, "ЮKassa")
    if kind == "manual":
        return ReadinessItem("payments", title, OFF,
                             "ручной провайдер (разработка: тариф сразу и без денег)",
                             "настоящих платежей нет", "YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")
    return ReadinessItem("payments", title, OFF, "не подключена",
                         "клиенты не могут оплатить в продукте — только по счёту, "
                         "назначение тарифа делает платформа",
                         "YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")


def _seller() -> ReadinessItem:
    problems = closing_docs.seller_problems()
    title = "Реквизиты продавца"
    if not problems:
        return ReadinessItem("seller", title, OK, "заданы")
    configured = any(os.getenv(var, "").strip()
                     for var, _ in closing_docs.SELLER_ENV.values())
    return ReadinessItem("seller", title, PROBLEM if configured else OFF,
                         "; ".join(problems), "счета и акты не формируются",
                         "SELLER_* (см. .env.example)")


def _months(n: int) -> str:
    """«1 месяц», «2 месяца», «5 месяцев» — подарок не больше полугода."""
    return f"{n} " + ("месяц" if n == 1 else "месяца" if 2 <= n <= 4 else "месяцев")


def _gift() -> ReadinessItem:
    title = "Подарок за оплату года"
    problem = billing.free_months_problem()
    if problem:
        return ReadinessItem("discount", title, PROBLEM, problem,
                             "год оплачивается полной ценой двенадцати месяцев",
                             f"{billing.FREE_MONTHS_ENV} — целое число 0–"
                             f"{billing.MAX_FREE_MONTHS}")
    gift = billing.annual_free_months()
    if not gift:
        return ReadinessItem("discount", title, OK,
                             "нет — год по цене 12 месяцев (решение владельца)")
    return ReadinessItem("discount", title, OK,
                         f"{_months(gift)} в подарок — год по цене {12 - gift} месяцев")


def _auto_renew(provider: PaymentProvider) -> ReadinessItem:
    reason = billing.auto_renew_unavailable(provider)
    if reason is None:
        return ReadinessItem("auto_renew", "Автопродление", OK, "доступно клиентам")
    return ReadinessItem("auto_renew", "Автопродление", OFF, "недоступно", reason,
                         "оплата в продукте и почта")


def _stuck() -> ReadinessItem:
    minutes, problem = scheduler.stuck_threshold()
    title = "Зависшие задачи"
    if problem:
        return ReadinessItem("stuck", title, PROBLEM, problem,
                             "зависшие задачи не проверяются",
                             f"{scheduler.STUCK_ENV} — от 1 до 59 минут")
    if minutes is None:
        return ReadinessItem("stuck", title, OFF, "порог не задан",
                             "о зависших задачах не пишут — их видно только на вкладке "
                             "«Эксплуатация»", f"{scheduler.STUCK_ENV} — решение эксплуатации")
    return ReadinessItem("stuck", title, OK, f"порог {minutes} мин")


def _database(db: Session) -> ReadinessItem:
    title = "База данных"
    try:
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 — нет таблицы версий: база создана не миграциями
        db.rollback()
        return ReadinessItem("database", title, PROBLEM,
                             "таблицы версий нет — база создана не миграциями",
                             "состояние схемы неизвестно", "alembic upgrade head")
    return ReadinessItem("database", title, OK, f"ревизия {version}")


def _safe(key: str, title: str, fn: Callable[[], ReadinessItem]) -> ReadinessItem:
    """Пункт, который не удалось проверить, — проблема с причиной, а не «в порядке»."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — проверка не должна ронять экран
        return ReadinessItem(key, title, PROBLEM, f"проверить не удалось: {exc}",
                             "состояние неизвестно", "см. логи процесса")


def check(db: Session, *, provider: PaymentProvider,
          now: datetime | None = None) -> list[ReadinessItem]:
    """Все пункты готовности. Только читает — ничего не меняет."""
    moment = now or datetime.now(timezone.utc)
    return [
        _safe("database", "База данных", lambda: _database(db)),
        _safe("mail", "Почта", _mail),
        _safe("public_url", "Публичный адрес", _public_url),
        _safe("scheduler", "Планировщик", lambda: _scheduler(db, moment)),
        _safe("payments", "Оплата в продукте", lambda: _payments(provider)),
        _safe("auto_renew", "Автопродление", lambda: _auto_renew(provider)),
        _safe("seller", "Реквизиты продавца", _seller),
        _safe("discount", "Подарок за оплату года", _gift),
        _safe("tracker", "Трекер ошибок", _tracker),
        _safe("stuck", "Зависшие задачи", _stuck),
        _safe("events", "События пользования", _events),
    ]
