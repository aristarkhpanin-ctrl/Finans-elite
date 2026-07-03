"""Celery-приложение: фоновые задачи тяжёлого анализа (Фаза D).

Брокер и бэкенд результатов — Redis (``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND``).
Тяжёлые прогоны (Монте-Карло) выносятся из воркеров API, чтобы не занимать их надолго.

В тестах включается eager-режим (``CELERY_TASK_ALWAYS_EAGER=1``): задачи выполняются
синхронно в процессе, без брокера/воркера; результат хранится в бэкенде для опроса.
"""
from __future__ import annotations

import os

from celery import Celery


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
)
