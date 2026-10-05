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
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import (
    billing,
    closing_docs,
    crud,
    error_tracking,
    girbo,
    legal,
    mail,
    scheduler,
    usage,
)
from .billing import PaymentProvider
from .env import env, env_int

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


_BACKUPS_TITLE = "Резервные копии"
#: Копия старше этого — служба копирования стоит: копия раз в сутки плюс запас.
BACKUP_STALE_HOURS = 26


def _read_mark(path: Path) -> dict[str, str] | None:
    """Отметка службы копирования: строки ``ключ=значение``. Нет файла — ``None``."""
    try:
        text_ = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return dict(line.split("=", 1) for line in text_.splitlines() if "=" in line)


def _mark_time(mark: dict[str, str] | None) -> datetime | None:
    if not mark or not mark.get("at"):
        return None
    try:
        return datetime.strptime(mark["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def restore_check_days() -> int:
    """Как часто проверяется восстановление (``RESTORE_CHECK_DAYS``, по умолчанию 7) — та
    же переменная, что у службы копирования: один источник на оба места."""
    days = env_int("RESTORE_CHECK_DAYS", 7)
    return days if days > 0 else 7


def _backups(now: datetime) -> ReadinessItem:
    """Резервные копии базы (L11): когда была последняя и проверено ли восстановление.

    Судится по **отметкам службы копирования** в её каталоге (сервис ``backup`` в
    `docker-compose.yml`, каталог подключён к API только для чтения): «Готовность»
    ничего не копирует и в базу ради этого не ходит. Нет каталога в продакшене —
    проблема: не видно, делаются ли копии, а без них сбой диска — потеря данных всех
    клиентов. Копия, которую ни разу не разворачивали, — тоже проблема.
    """
    title = _BACKUPS_TITLE
    run = "docker compose exec backup sh /ops/backup/backup.sh"
    directory = env("BACKUP_DIR")
    if not directory:
        return ReadinessItem("backups", title, PROBLEM if _production() else OFF,
                             "каталог копий не подключён к сервису API (BACKUP_DIR)",
                             "не видно, делаются ли копии; без них сбой диска — потеря "
                             "данных всех клиентов",
                             "сервис backup и том backups в docker-compose.yml, "
                             "BACKUP_DIR=/backups у API")
    folder = Path(directory)
    if not folder.is_dir():
        return ReadinessItem("backups", title, PROBLEM, f"каталога копий {directory} нет",
                             "не видно, делаются ли копии",
                             "подключить том backups к API (docker-compose.yml)")
    ok, failed = _read_mark(folder / "LAST_OK"), _read_mark(folder / "LAST_ERROR")
    checked = _read_mark(folder / "LAST_RESTORE_CHECK")
    check_failed = _read_mark(folder / "LAST_RESTORE_ERROR")
    ok_at, failed_at = _mark_time(ok), _mark_time(failed)
    checked_at, check_failed_at = _mark_time(checked), _mark_time(check_failed)
    how_copy = f"{run} once — копия сейчас; журнал службы — docker compose logs backup"
    if ok is None or ok_at is None:
        reason = f"; последняя попытка: {failed.get('error', '')}" if failed else ""
        return ReadinessItem("backups", title, PROBLEM, "копий ещё не было" + reason,
                             "сбой диска сейчас — потеря данных всех клиентов", how_copy)
    if failed_at is not None and failed_at > ok_at:
        return ReadinessItem(
            "backups", title, PROBLEM,
            f"последняя попытка {failed_at:%d.%m.%Y %H:%M} UTC не удалась: "
            f"{failed.get('error', '') if failed else ''}; предыдущая копия — "
            f"{ok_at:%d.%m.%Y %H:%M} UTC",
            "новые данные не защищены копией", how_copy)
    hours = int((now - ok_at).total_seconds() // 3600)
    if hours >= BACKUP_STALE_HOURS:
        return ReadinessItem("backups", title, PROBLEM,
                             f"последняя копия {hours} ч назад — служба копирования стоит",
                             "данные за это время не защищены копией", how_copy)
    days = restore_check_days()
    how_check = f"{run} check — развернуть последнюю копию и прочитать"
    if checked is None or checked_at is None:
        return ReadinessItem("backups", title, PROBLEM,
                             "восстановление из копии ни разу не проверялось",
                             "копия, которую ни разу не разворачивали, — надежда, а не "
                             "копия", how_check)
    if check_failed_at is not None and check_failed_at > checked_at:
        return ReadinessItem(
            "backups", title, PROBLEM,
            f"проверка восстановления {check_failed_at:%d.%m.%Y} не прошла: "
            f"{check_failed.get('error', '') if check_failed else ''}",
            "из последней копии данные, возможно, не восстановить", how_check)
    if (now - checked_at).days > days:
        return ReadinessItem("backups", title, PROBLEM,
                             f"восстановление проверялось {(now - checked_at).days} дн. "
                             f"назад (раз в {days} дн. по плану)",
                             "свежие копии не проверены", how_check)
    size = int(ok.get("bytes") or 0)
    mb = f"{size / 1_048_576:.1f}".replace(".", ",")
    return ReadinessItem(
        "backups", title, OK,
        f"последняя копия {ok_at:%d.%m.%Y %H:%M} UTC ({mb} МБ), восстановление "
        f"проверено {checked_at:%d.%m.%Y} (организаций: {checked.get('organizations', '?')}); "
        "копии на этом же сервере — вынесите копию за его пределы "
        "(docs/HOSTING-CHECKLIST.md)")


_RLS_TITLE = "Изоляция организаций в базе (RLS)"


def _rls(db: Session) -> ReadinessItem:
    """Действуют ли политики RLS на приложение (L11).

    Политики применяются только к роли **без** прав суперпользователя: суперпользователь
    и роль с BYPASSRLS обходят их всегда, даже с FORCE. В `docker-compose.yml` до L11
    приложение подключалось суперпользователем образа postgres — и вторая стена изоляции
    организаций стояла на бумаге: держал только фильтр приложения. Здесь проверяется
    роль, которой подключено само приложение, а не то, что написано в настройке.
    """
    title = _RLS_TITLE
    if db.bind is None or db.bind.dialect.name != "postgresql":
        if _production():
            return ReadinessItem("rls", title, PROBLEM, "база не PostgreSQL — политик RLS нет",
                                 "изоляцию организаций держит только фильтр приложения",
                                 "PostgreSQL и роль приложения (docker-compose.yml)")
        return ReadinessItem("rls", title, OFF, "SQLite (разработка): политик RLS нет",
                             "изоляцию организаций держит только фильтр приложения",
                             "в продакшене — PostgreSQL и роль приложения")
    role, superuser, bypass = db.execute(text(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
        "WHERE rolname = current_user")).one()
    policies = int(db.execute(text(
        "SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")).scalar_one())
    if superuser or bypass:
        right = "суперпользователь" if superuser else "право BYPASSRLS"
        return ReadinessItem(
            "rls", title, PROBLEM,
            f"приложение подключено ролью «{role}» ({right}) — политики RLS к нему не "
            "применяются",
            "изоляцию организаций держит только фильтр приложения: ошибка в нём открыла "
            "бы данные одной организации другой",
            "подключать приложение ролью без прав суперпользователя: ops/db/app-role.sql "
            "(в docker-compose.yml — сервис db-setup и DATABASE_URL с finans_app)")
    if not policies:
        return ReadinessItem("rls", title, PROBLEM, "политик RLS в базе нет",
                             "изоляцию организаций держит только фильтр приложения",
                             "alembic upgrade head — политики заводят миграции")
    return ReadinessItem("rls", title, OK,
                         f"роль «{role}» без права обходить RLS, политик: {policies}")


def _safe(key: str, title: str, fn: Callable[[], ReadinessItem]) -> ReadinessItem:
    """Пункт, который не удалось проверить, — проблема с причиной, а не «в порядке»."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — проверка не должна ронять экран
        return ReadinessItem(key, title, PROBLEM, f"проверить не удалось: {exc}",
                             "состояние неизвестно", "см. логи процесса")


def _demo(db: Session) -> ReadinessItem:
    """Демо без регистрации (L2) — выбор владельца, а не настройка: не заведено —
    «выключено», а не проблема."""
    title = "Демо без регистрации"
    user = crud.demo_account(db)
    if user is None:
        return ReadinessItem("demo", title, OFF, "не заведено",
                             "кнопки «Посмотреть демо» на входе нет — посетитель видит "
                             "продукт только после регистрации",
                             "python scripts/seed_demo.py --public")
    names = sorted(o.name for o, _ in crud.list_user_organizations(db, user.id) if o.is_demo)
    return ReadinessItem("demo", title, OK, "заведено: " + ", ".join(f"«{n}»" for n in names))


def _girbo() -> ReadinessItem:
    """Отчётность по ИНН (L3). Внешний запрос здесь не делается — «Готовность» только
    читает настройки; доступность ресурса проверяет сама загрузка и называет отказ."""
    title = "Отчётность по ИНН (ГИР БО)"
    if not girbo.enabled():
        return ReadinessItem("girbo", title, OFF, "выключена",
                             "в деле нет загрузки отчётности по ИНН — только Excel и ручной "
                             "ввод", "GIRBO_ENABLED=1")
    return ReadinessItem("girbo", title, OK, f"включена: запрос с сервера на {girbo.base_url()}")


def _legal() -> ReadinessItem:
    """Оферта, политика ПД и согласие (L5). Черновик — **проблема**, а не «выключено»:
    это не решение владельца отключить документы, а работа, которую ещё не сделали, и
    сайт с непроверенной офертой принимает деньги."""
    title = "Юридические документы"
    gaps = legal.seller_problems()
    if legal.is_draft():
        return ReadinessItem(
            "legal", title, PROBLEM,
            "черновик: оферта, политика обработки ПД и согласие подготовлены платформой "
            "и юристом не проверены — над текстами стоит пометка «Черновик»"
            + (f"; кроме того: {'; '.join(gaps)}" if gaps else ""),
            "договор с клиентами и согласие на обработку ПД держатся на непроверенном "
            "тексте", "отдать тексты юристу (страницы /legal/…), внести правки в "
            "app/legal.py и задать LEGAL_DOCS_EDITION — дату утверждённой редакции")
    if gaps:
        return ReadinessItem("legal", title, PROBLEM,
                             f"редакция {legal.edition()}, но в текстах пробелы: "
                             + "; ".join(gaps),
                             "документы не называют оператора или связь с ним",
                             "SELLER_* и PUBLIC_URL (см. .env.example)")
    return ReadinessItem("legal", title, OK, f"редакция {legal.edition()}")


def check(db: Session, *, provider: PaymentProvider,
          now: datetime | None = None) -> list[ReadinessItem]:
    """Все пункты готовности. Только читает — ничего не меняет."""
    moment = now or datetime.now(timezone.utc)
    return [
        _safe("database", "База данных", lambda: _database(db)),
        _safe("rls", _RLS_TITLE, lambda: _rls(db)),
        _safe("backups", _BACKUPS_TITLE, lambda: _backups(moment)),
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
        _safe("demo", "Демо без регистрации", lambda: _demo(db)),
        _safe("girbo", "Отчётность по ИНН (ГИР БО)", _girbo),
        _safe("legal", "Юридические документы", _legal),
    ]
