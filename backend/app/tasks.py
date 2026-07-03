"""Фоновые задачи анализа (Celery-воркер)."""
from __future__ import annotations

from calc_core import ProjectModel
from calc_core.montecarlo import run_monte_carlo

from .analysis_service import build_mc_config
from .celery_app import celery_app
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
