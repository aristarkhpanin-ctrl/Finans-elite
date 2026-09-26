"""Назначить или снять признак сотрудника платформы (ADMIN-DECOMPOSITION.md, B1).

Зачем скрипт, а не эндпоинт. Маршрут, повышающий права, сам становится главной мишенью:
защищать его придётся сильнее всего остального вместе взятого, а первый же промах в этой
защите отдаёт служебный контур целиком. Признак ставится тем, у кого и так есть доступ к
базе, — то есть тем, кто в этом случае уже может всё.

Уровень внутри контура (F5) ставится здесь же и по той же причине: ``--role support``
даёт наблюдение (списки, карточки, журнал), ``--role operator`` — ещё и власть над
клиентом (приостановка организации, блокировка учётной записи, сброс второго фактора,
назначение тарифа). Умолчание — ``operator``: оно совпадает с тем, что признак значил до
разделения, и никого не понижает молча.

Запуск (из каталога ``backend``)::

    python scripts/set_staff.py --email operator@example.com
    python scripts/set_staff.py --email support@example.com --role support
    python scripts/set_staff.py --email operator@example.com --off
    python scripts/set_staff.py --list

``DATABASE_URL`` берётся из окружения — так же, как приложением.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import crud  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.db_models import STAFF_OPERATOR, STAFF_ROLES, User  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Признак сотрудника платформы")
    parser.add_argument("--email", help="адрес пользователя")
    parser.add_argument("--off", action="store_true", help="снять признак")
    parser.add_argument("--role", choices=list(STAFF_ROLES), default=STAFF_OPERATOR,
                        help="уровень внутри контура (по умолчанию operator)")
    parser.add_argument("--list", action="store_true", dest="show",
                        help="показать текущих сотрудников")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.show:
            staff = list(db.execute(select(User).where(User.is_staff.is_(True))
                                    .order_by(User.email)).scalars())
            if not staff:
                print("Сотрудников платформы нет.")
            for user in staff:
                # Пустой уровень — не «поддержка»: это сотрудник, которому уровень не
                # назначали, и власти он не получает. Называем прямо, а не подставляем.
                print(f"{user.email}\t{user.staff_role or '(уровень не назначен)'}"
                      f"\t{user.full_name}")
            return 0

        if not args.email:
            parser.error("нужен --email или --list")
        user = crud.get_user_by_email(db, args.email)
        if user is None:
            # Молча создавать пользователя нельзя: опечатка в адресе завела бы
            # сотрудника платформы, о котором никто не знает.
            print(f"Пользователь {args.email} не найден.", file=sys.stderr)
            return 1
        crud.set_staff(db, user, is_staff=not args.off, role=args.role)
        print(f"{user.email}: признак сотрудника "
              + ("снят" if args.off else f"установлен, уровень — {args.role}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
