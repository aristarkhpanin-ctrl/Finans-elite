"""Фоновые задачи анализа (Celery-воркер)."""
from __future__ import annotations

from datetime import datetime, timezone

from calc_core import ProjectModel
from calc_core.montecarlo import run_monte_carlo

from . import scheduler
from .analysis_service import build_mc_config
from .celery_app import celery_app
from .database import SessionLocal
from .schemas import MonteCarloRequest, monte_carlo_response


@celery_app.task(name="analysis.monte_carlo")
def monte_carlo_task(model_json: dict, request_json: dict) -> dict:
    """Прогнать Монте-Карло в фоне. Возвращает JSON-словарь MonteCarloResponse.

    Вход — сериализованные модель проекта и тело запроса (Decimal строками), чтобы
    аргументы задачи были JSON-совместимы. Реконструкция через те же схемы даёт тот
    же результат, что и синхронный эндпоинт.
    """
    model = ProjectModel.model_validate(model_json)
    body = MonteCarloRequest.model_validate(request_json)
    result = run_monte_carlo(model, build_mc_config(body))
    return monte_carlo_response(result).model_dump(mode="json")


# --- Задачи планировщика (пакет G, G3) ---
#
# Тонкие обёртки: работа живёт в ``app.scheduler``, её же зовут скрипты эксплуатации.
# Имя каждой задачи начинается с ``scheduler.`` и стоит в ``beat_schedule`` — перечень
# сверяется тестом в обе стороны.

@celery_app.task(name="scheduler.expire_subscriptions")
def expire_subscriptions_task() -> int:
    """Суточная сверка неоплаты. Возвращает, сколько подписок переведено в неоплату."""
    with SessionLocal() as db:
        return len(scheduler.expire_overdue(db, datetime.now(timezone.utc)))


@celery_app.task(name="scheduler.billing_reminders")
def billing_reminders_task() -> int:
    """Письма о деньгах (G4). Возвращает, скольким подпискам письмо ушло."""
    with SessionLocal() as db:
        return scheduler.send_billing_reminders(db, datetime.now(timezone.utc)).sent
