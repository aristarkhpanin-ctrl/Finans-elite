"""Завести демо-организацию для проверки продукта (пакет J, J2).

Одна команда заводит организацию «ООО «Демо Групп» (вымышленные данные)», владельца и
аналитика, пять проектов «Финанс-Элита» (производство с фактом и версиями, кофейня,
перевозки, магазин, подписка), холдинг, обсуждение и три дела «Финанс-Аудита» с
группой, ориентирами и чек-листом. Вне продакшена — ещё и сотрудника платформы, который
назначает организации тарифы. Состав и числа — ``app/demo_seed.py`` и
``docs/DEMO-DATA.md``.

Запуск — там же, где работает приложение (``DATABASE_URL`` берётся из окружения)::

    cd backend && python scripts/seed_demo.py
    docker compose exec api python scripts/seed_demo.py

    python scripts/seed_demo.py --reset          # удалить прежнюю демо-организацию и завести заново
    python scripts/seed_demo.py --no-operator    # без сотрудника платформы
    python scripts/seed_demo.py --public         # публичное демо «Посмотреть демо» (L2)
    python scripts/seed_demo.py --public --reset # удалить публичное демо и завести заново

**Публичное демо** (``--public``) — отдельная организация, которую смотрят посетители
сайта кнопкой «Посмотреть демо», без регистрации. Пароли его учётных записей случайные и
нигде не печатаются, поэтому ``--public`` работает и на боевой установке без
``--allow-production``. Признаки демо ставятся записью в базу последним шагом.

**В продакшене** (``APP_ENV=production``) скрипт по умолчанию отказывает: известный
всем пароль на боевой установке — дыра. Там нужен явный ``--allow-production`` и свой
``--password`` (один на обе учётные записи), а сотрудник платформы не заводится вовсе:
учётная запись с властью над всеми клиентами не должна появляться из демо-скрипта.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Скрипт идёт через маршруты приложения в своём процессе, и два десятка запросов подряд
# с одного адреса уперлись бы в ограничитель регистрации и входа. Работающий сервер
# это не затрагивает: переменная живёт только в процессе скрипта.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app import crud  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.demo_seed import (  # noqa: E402
    ANALYST,
    OPERATOR,
    OWNER,
    PUBLIC_ACCOUNTS,
    PUBLIC_OWNER,
    DemoAccount,
    SeedError,
    SeedReport,
    _Api,
    make_operator,
    random_password,
    seed,
    seed_public,
)
from app.main import app  # noqa: E402
from app.password_policy import check_password  # noqa: E402
from app.security import hash_password  # noqa: E402


def _production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def _make_operator(password: str) -> str:
    with SessionLocal() as db:
        return make_operator(db, password)


def _exists() -> bool:
    with SessionLocal() as db:
        return crud.get_user_by_email(db, OWNER.email) is not None


def _reset(client: TestClient, passwords: dict[str, str],
           accounts: tuple[DemoAccount, ...] = (OWNER, ANALYST, OPERATOR),
           owner: DemoAccount = OWNER) -> None:
    """Удалить прежнюю демо-организацию и учётные записи — теми же дверями, что у
    человека (F6 и C3): по паролю, с планом удаления, собранным сервером."""
    api = _Api(client)
    for account in accounts:
        with SessionLocal() as db:
            if crud.get_user_by_email(db, account.email) is None:
                continue
        try:
            token = api.call("POST", "/auth/login", {
                "email": account.email, "password": passwords[account.email]})["access_token"]
        except SeedError as exc:
            raise SeedError(
                f"Не удалось войти как {account.email}: пароль, видимо, изменён. Удалите "
                "организацию и учётные записи в интерфейсе (Организация → Удаление, "
                "Профиль → Удалить учётную запись) или передайте прежний пароль "
                "через --password.") from exc
        me = api.as_(token)
        if account is owner:
            for org in me.call("GET", "/organizations"):
                me.call("DELETE", f"/organizations/{org['id']}",
                        {"password": passwords[account.email]})
        me.call("POST", "/auth/delete", {"password": passwords[account.email]})


def _public_exists() -> bool:
    with SessionLocal() as db:
        return crud.get_user_by_email(db, PUBLIC_OWNER.email) is not None


def _mark_demo(org_id: str, email: str) -> None:
    with SessionLocal() as db:
        user = crud.get_user_by_email(db, email)
        if user is None:
            raise SeedError(f"демо: нет учётной записи {email}")
        crud.mark_demo(db, org_id, user.id)


def _reset_public(client: TestClient) -> None:
    """Удалить публичное демо теми же дверями, что у человека. Паролей никто не знает,
    поэтому скрипт ставит новые случайные записью в базу и снимает признаки демо
    (иначе удаление учётной записи закрыл бы демо-шлюз) — и дальше идёт маршрутами."""
    passwords: dict[str, str] = {}
    with SessionLocal() as db:
        for account in PUBLIC_ACCOUNTS:
            user = crud.get_user_by_email(db, account.email)
            if user is None:
                continue
            passwords[account.email] = random_password()
            user.hashed_password = hash_password(passwords[account.email])
            user.is_demo = False
        for org_id in crud.demo_organization_ids(db):
            org = crud.get_organization(db, org_id)
            if org is not None:
                org.is_demo = False
        db.commit()
    _reset(client, passwords, accounts=PUBLIC_ACCOUNTS, owner=PUBLIC_OWNER)


def _public(reset: bool) -> int:
    with TestClient(app) as client:
        try:
            if _public_exists():
                if not reset:
                    print("Публичное демо уже заведено. Повторный запуск не плодит "
                          "дубликаты; --public --reset — удалить и завести заново.")
                    return 0
                _reset_public(client)
            report = seed_public(client, mark_demo=_mark_demo)
        except SeedError as exc:
            print(f"Не удалось: {exc}", file=sys.stderr)
            return 1
    print(f"\nПубличное демо: {report.org_name}")
    print("Учётные записи (пароли случайные и нигде не сохранены):")
    for acc in report.accounts:
        print(f"  {acc.role:9s} {acc.email}")
    print(f"Проектов: {len(report.projects)}, дел: {len(report.cases)}; баланс каждого "
          "проекта сверен помесячно.")
    for note in report.notes:
        print(f"\n{note}")
    return 0


def _print_report(report: SeedReport, passwords: dict[str, str]) -> None:
    print(f"\nОрганизация: {report.org_name}")
    print("\nУчётные записи:")
    for acc in report.accounts:
        print(f"  {acc.role:9s} {acc.email:28s} {passwords[acc.email]}")
    print("\nПроекты «Финанс-Элита» (расчёт тем же маршрутом, что и экран):")
    print(f"  {'проект':44s} {'мес':>3s} {'NPV, ₽':>15s} {'IRR':>7s} {'окуп.':>5s} "
          f"{'выручка 1-го года':>18s}  баланс")
    for p in report.projects:
        irr = f"{p.irr_annual * 100:.1f}%" if p.irr_annual is not None else "—"
        pb = str(p.pb_months) if p.pb_months is not None else "—"
        ok = "сходится" if p.max_balance_gap < 1 else f"РАЗРЫВ {p.max_balance_gap}"
        print(f"  {p.name:44s} {p.months:3d} {p.npv:15,.0f} {irr:>7s} {pb:>5s} "
              f"{p.revenue_first_year:18,.0f}  {ok}")
    print("\nДела «Финанс-Аудита» (сводка тем же разбором, что и экран «Вердикт»):")
    for c in report.cases:
        value = f"{c.equity_value:,.0f}" if c.equity_value is not None else "—"
        ask = f"{c.asking_price:,.0f}" if c.asking_price is not None else "—"
        print(f"  {c.name:38s} {c.verdict:8s} флаги: {c.risk_flags} риск, "
              f"{c.warning_flags} внимание; доля: {value} против цены {ask} тыс. ₽")
        print(f"      {c.headline}")
    for note in report.notes:
        print(f"\n{note}")
    print("\nПодробности и проверки, которые можно повторить руками, — docs/DEMO-DATA.md.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Демо-организация для проверки продукта")
    parser.add_argument("--reset", action="store_true",
                        help="удалить прежнюю демо-организацию и завести заново")
    parser.add_argument("--no-operator", action="store_true",
                        help="не заводить сотрудника платформы")
    parser.add_argument("--password", help="свой пароль для владельца и аналитика")
    parser.add_argument("--allow-production", action="store_true",
                        help="разрешить запуск при APP_ENV=production (нужен --password)")
    parser.add_argument("--public", action="store_true",
                        help="публичное демо «Посмотреть демо» (пароли случайные — годится "
                             "и для продакшена)")
    args = parser.parse_args(argv)
    if args.public:
        return _public(args.reset)

    production = _production()
    if production and not (args.allow_production and args.password):
        print("APP_ENV=production: демо-данные с известным паролем на боевой установке — "
              "дыра. Нужны --allow-production и свой --password.", file=sys.stderr)
        return 2
    passwords = {a.email: a.password for a in (OWNER, ANALYST, OPERATOR)}
    if args.password:
        problem = check_password(args.password, email=OWNER.email)
        if problem:
            print(f"Пароль не проходит политику входа: {problem}", file=sys.stderr)
            return 2
        passwords[OWNER.email] = passwords[ANALYST.email] = args.password
    with_operator = not args.no_operator and not production

    with TestClient(app) as client:  # lifespan — тот же, что у сервера (init_db)
        try:
            if _exists():
                if not args.reset:
                    print(f"Демо-организация уже заведена ({OWNER.email}). Повторный "
                          "запуск не плодит дубликаты; --reset — удалить и завести "
                          "заново.")
                    return 0
                _reset(client, passwords)
            report = seed(client, passwords=passwords,
                          operator=(lambda: _make_operator(passwords[OPERATOR.email]))
                          if with_operator else None)
        except SeedError as exc:
            print(f"Не удалось: {exc}", file=sys.stderr)
            return 1
    if production:
        report.notes.append("Продакшен: сотрудник платформы не заводился. Назначить его "
                            "себе — scripts/set_staff.py --email <ваш адрес>.")
    _print_report(report, passwords)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
