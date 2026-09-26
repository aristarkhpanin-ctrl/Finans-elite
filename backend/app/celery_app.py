"""Celery-приложение: фоновые задачи тяжёлого анализа (Фаза D) и планировщик (пакет G).

Брокер и бэкенд результатов — Redis (``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND``).
Тяжёлые прогоны (Монте-Карло) выносятся из воркеров API, чтобы не занимать их надолго.

В тестах включается eager-режим (``CELERY_TASK_ALWAYS_EAGER=1``): задачи выполняются
синхронно в процессе, без брокера/воркера; результат хранится в бэкенде для опроса.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


celery_app = Celery(
    "finans",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    task_always_eager=_truthy(os.getenv("CELERY_TASK_ALWAYS_EAGER")),
    task_store_eager_result=True,      # eager-результат доступен через AsyncResult
    task_eager_propagates=False,       # ошибка eager → FAILURE, а не исключение в запросе
    # Расписание планировщика (пакет G, G3). Часовой пояс назван явно: «в три ночи» без
    # пояса значило бы разное время на разных серверах. Процесс beat — ровно один.
    timezone="UTC",
    beat_schedule={
        # Сверка неоплаты — ночью, когда нагрузка ниже; идемпотентна, пропуск дня не
        # страшен: выведенный статус и так ограничивает, сверка лишь оставляет след.
        "expire-subscriptions": {
            "task": "scheduler.expire_subscriptions",
            "schedule": crontab(hour=3, minute=10),
        },
        # Письма о деньгах — после ночной сверки и к началу рабочего дня по Москве
        # (06:00 UTC = 09:00 МСК): письмо о закрытии записи, пришедшее ночью, прочли бы
        # утром, уже упёршись в закрытую запись.
        "billing-reminders": {
            "task": "scheduler.billing_reminders",
            "schedule": crontab(hour=6, minute=0),
        },
        # Автопродление (G5) — после сверки неоплаты и до писем: списание, прошедшее в
        # 04:00, продлевает период раньше, чем письмо 09:00 МСК успело бы назвать его
        # закончившимся.
        "renew-subscriptions": {
            "task": "scheduler.renew_subscriptions",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
