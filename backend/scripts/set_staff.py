"""Назначить или снять признак сотрудника платформы (ADMIN-DECOMPOSITION.md, B1).

Зачем скрипт, а не эндпоинт. Маршрут, повышающий права, сам становится главной мишенью:
защищать его придётся сильнее всего остального вместе взятого, а первый же промах в этой
защите отдаёт служебный контур целиком. Признак ставится тем, у кого и так есть доступ к
базе, — то есть тем, кто в этом случае уже может всё.

Запуск (из каталога ``backend``)::

    python scripts/set_staff.py --email operator@example.com
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
from app.db_models import User  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Признак сотрудника платформы")
    parser.add_argument("--email", help="адрес пользователя")
    parser.add_argument("--off", action="store_true", help="снять признак")
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
                print(f"{user.email}\t{user.full_name}")
            return 0

        if not args.email:
            parser.error("нужен --email или --list")
        user = crud.get_user_by_email(db, args.email)
        if user is None:
            # Молча создавать пользователя нельзя: опечатка в адресе завела бы
            # сотрудника платформы, о котором никто не знает.
            print(f"Пользователь {args.email} не найден.", file=sys.stderr)
            return 1
        crud.set_staff(db, user, is_staff=not args.off)
        print(f"{user.email}: признак сотрудника "
              + ("снят" if args.off else "установлен"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
