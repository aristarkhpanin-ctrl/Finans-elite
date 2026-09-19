"""Записать в базу подписки, у которых льготный срок уже вышел (OPEN-DECISIONS §1).

**Доступ этот скрипт ничего не решает.** Режим чтения и выгрузки считается из даты конца
периода на каждом запросе (``app/billing_period.effective_status``), и запускать его
ради ограничения не нужно: пока скрипт не запущен, неплательщик всё равно ограничен —
просто в базе у него по-прежнему написано ``active``.

Нужен он ради **следа**. Вывод состояния отвечает «как сейчас» и не отвечает «когда это
произошло»: отток тарифов — вопрос о переходах, а переходы существуют только записанными.
Скрипт приводит хранимое состояние к выведенному и пишет строку в журнал организации;
по этим строкам метрика оттока и считается, когда её заведут.

Почему скрипт, а не фоновая задача внутри приложения: фоновых задач у платформы нет
вовсе. Заводить планировщик ради одной ежесуточной сверки — это новая точка отказа,
которую надо разворачивать, мониторить и чинить; крон эксплуатации делает то же самое и
уже существует у любого хостинга. Решение о том, **чем** его запускать, принадлежит
эксплуатации, и скрипт его не навязывает.

Идемпотентен: повторный запуск в тот же день ничего не меняет и ничего не пишет.

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

from sqlalchemy import select  # noqa: E402

from app import crud  # noqa: E402
from app.billing_period import (  # noqa: E402
    OVERDUE_STATUS,
    days_overdue,
    effective_status,
)
from app.database import SessionLocal, as_tenant  # noqa: E402
from app.db_models import Subscription  # noqa: E402


def overdue_subscriptions(db, now: datetime) -> list[Subscription]:
    """Подписки, у которых выведенный статус разошёлся с хранимым.

    Отбор идёт по **выведенному** состоянию, а не по SQL-условию на дату: условие было
    бы второй копией правила, и разойтись с ``effective_status`` ему ничего не мешает.
    """
    rows = db.execute(select(Subscription)).scalars().all()
    return [s for s in rows
            if effective_status(s.status, s.current_period_end, now) != s.status]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Просроченные подписки → past_due")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что изменилось бы, и ничего не писать")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        stale = overdue_subscriptions(db, now)
        if not stale:
            print("Просроченных подписок нет.")
            return 0

        for sub in stale:
            days = days_overdue(sub.current_period_end, now)
            print(f"{sub.organization_id} · {sub.product} · {sub.plan_code}: "
                  f"{sub.status} → {OVERDUE_STATUS} (просрочено {days} дн.)")
            if args.dry_run:
                continue
            sub.status = OVERDUE_STATUS
            db.commit()
            # Журнал под RLS, а запись идёт в чужую организацию: заходим в неё той же
            # дверью, что и все остальные (правило C3), и выходим обратно.
            with as_tenant(db, sub.organization_id):
                crud.log_action(
                    db, sub.organization_id, None, "billing.overdue",
                    entity_type="organization", entity_id=sub.organization_id,
                    entity_name=sub.plan_code,
                    details=f"{sub.product}: оплаченный период и льготный срок истекли "
                            f"({days} дн. с конца периода)")
        if args.dry_run:
            print(f"\n--dry-run: изменений не внесено ({len(stale)} шт.)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
