"""Готовность установки — из командной строки (пакет G, G9).

Та же проверка, что на вкладке «Готовность» служебного раздела: зовётся одна функция
``app.readiness.check``, своей копии перечня у скрипта нет. Только читает.

Код выхода — 1, если есть **проблема** (ошибка настройки), и 0, если всё либо в порядке,
либо выключено по решению владельца: «сбор событий не включён» — выбор, а не поломка, и
ронять им проверку перед выкаткой значило бы навязывать решение, которое продукт
принимать не вправе.

Запуск (из каталога ``backend``)::

    python scripts/check_readiness.py

``DATABASE_URL`` и прочее окружение — те же, что у приложения.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import readiness  # noqa: E402
from app.billing import get_payment_provider  # noqa: E402
from app.database import SessionLocal  # noqa: E402

MARK = {readiness.OK: "в порядке", readiness.OFF: "выключено", readiness.PROBLEM: "ПРОБЛЕМА"}


def main() -> int:
    with SessionLocal() as db:
        items = readiness.check(db, provider=get_payment_provider())
    for item in items:
        print(f"[{MARK[item.status]}] {item.title}: {item.state}")
        if item.impact:
            print(f"    не работает: {item.impact}")
        if item.how:
            print(f"    чем включить: {item.how}")
    return 1 if any(i.status == readiness.PROBLEM for i in items) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
