"""What-If анализ (9.1; SPEC доп. модули).

Сравнение нескольких именованных сценариев одного проекта. Сценарий — набор
мультипликативных корректировок параметров (переиспользуются аппликаторы чувствительности);
в одном сценарии можно сочетать несколько корректировок. Базовый сценарий («как есть»)
добавляется автоматически первым.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .engine import run
from .models import ProjectModel
from .money import D
from .sensitivity import SENSITIVITY_PARAMS


@dataclass
class ScenarioAdjustment:
    param: str          # один из SENSITIVITY_PARAMS
    factor: Decimal


@dataclass
class Scenario:
    name: str
    adjustments: list[ScenarioAdjustment] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    npv: Decimal
    irr_annual: Optional[Decimal]
    pi: Optional[Decimal]
    pb_months: Optional[int]


def _evaluate(model: ProjectModel, name: str, adjustments: list[ScenarioAdjustment]) -> ScenarioResult:
    m = model.model_copy(deep=True)
    for adj in adjustments:
        if adj.param not in SENSITIVITY_PARAMS:
            raise ValueError(f"Неизвестный параметр сценария: {adj.param}")
        SENSITIVITY_PARAMS[adj.param](m, D(adj.factor))
    r = run(m)
    return ScenarioResult(
        name=name, npv=r.metrics.npv, irr_annual=r.metrics.irr_annual,
        pi=r.metrics.pi, pb_months=r.metrics.pb_months,
    )


def run_what_if(model: ProjectModel, scenarios: list[Scenario],
                include_base: bool = True) -> list[ScenarioResult]:
    """Рассчитать базовый сценарий и заданные сценарии; вернуть показатели для сравнения."""
    results: list[ScenarioResult] = []
    if include_base:
        results.append(_evaluate(model, "Базовый", []))
    for sc in scenarios:
        results.append(_evaluate(model, sc.name, sc.adjustments))
    return results
