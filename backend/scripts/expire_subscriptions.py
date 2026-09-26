"""Сверка неоплаты вручную — та же, что проводит планировщик (OPEN-DECISIONS §1, пакет G).

С пакета G сверку каждую ночь ставит планировщик (Celery beat, ``app.celery_app``), и
запускать скрипт по крону больше не нужно. Он остаётся инструментом эксплуатации:
посмотреть, что изменилось бы (``--dry-run``), или провести сверку сейчас.

**Своей копии сверки у скрипта нет** — он зовёт ``app.scheduler.expire_overdue``, ту же
функцию, что и задача планировщика: две копии одного правила однажды разошлись бы. След
запуска подписан источником («скрипт эксплуатации»), чтобы ручной запуск не выглядел
работающим планировщиком.

**Доступ этот скрипт ничего не решает.** Режим чтения и выгрузки считается из даты конца
периода на каждом запросе (``app/billing_period.effective_status``): пока сверку не
провели, неплательщик всё равно ограничен — просто в базе у него ещё ``active``.

Запуск (из каталога ``backend``)::

    python scripts/expire_subscriptions.py --dry-run
    python scripts/expire_subscriptions.py

``DATABASE_URL`` берётся из окружения — так же, как приложением.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.billing_period import OVERDUE_STATUS  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.scheduler import SOURCE_SCRIPT, expire_overdue  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Просроченные подписки → past_due")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что изменилось бы, и ничего не писать")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        changed = expire_overdue(db, datetime.now(timezone.utc), dry_run=args.dry_run,
                                 source=SOURCE_SCRIPT)
        if not changed:
            print("Просроченных подписок нет.")
            return 0
        for sub, days in changed:
            print(f"{sub.organization_id} · {sub.product} · {sub.plan_code}: "
                  f"→ {OVERDUE_STATUS} (просрочено {days} дн.)")
        if args.dry_run:
            print(f"\n--dry-run: изменений не внесено ({len(changed)} шт.)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
