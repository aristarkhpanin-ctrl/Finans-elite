"""Анализ чувствительности (7.3; SPEC §20).

Варьируем выбранный параметр модели мультипликативным коэффициентом и наблюдаем, как
меняются показатели эффективности (NPV, IRR). Множество варьируемых параметров
расширяемо.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from .engine import run
from .models import ProjectModel
from .money import D


def _scale_prices(m: ProjectModel, f: Decimal) -> None:
    for s in m.operating_plan.sales:
        s.price = [p * f for p in s.price]


def _scale_volume(m: ProjectModel, f: Decimal) -> None:
    for s in m.operating_plan.sales:
        s.volume = [v * f for v in s.volume]


def _scale_direct(m: ProjectModel, f: Decimal) -> None:
    for d in m.operating_plan.direct_costs:
        d.amount = [a * f for a in d.amount]


def _scale_fixed(m: ProjectModel, f: Decimal) -> None:
    for c in m.operating_plan.fixed_costs:
        c.amount = [a * f for a in c.amount]


def _scale_discount(m: ProjectModel, f: Decimal) -> None:
    m.settings.discount_rate_annual = m.settings.discount_rate_annual * f


#: Доступные параметры чувствительности → функция применения коэффициента.
SENSITIVITY_PARAMS: dict[str, Callable[[ProjectModel, Decimal], None]] = {
    "sales_price": _scale_prices,
    "sales_volume": _scale_volume,
    "direct_costs": _scale_direct,
    "fixed_costs": _scale_fixed,
    "discount_rate": _scale_discount,
}


@dataclass
class SensitivityPoint:
    factor: Decimal
    npv: Decimal
    irr_annual: Optional[Decimal]


def run_sensitivity(model: ProjectModel, param: str, factors: list) -> list[SensitivityPoint]:
    """Прогнать модель при разных значениях параметра (коэффициентах)."""
    if param not in SENSITIVITY_PARAMS:
        raise ValueError(f"Неизвестный параметр чувствительности: {param}")
    apply = SENSITIVITY_PARAMS[param]
    points: list[SensitivityPoint] = []
    for raw in factors:
        f = D(raw)
        m = model.model_copy(deep=True)
        apply(m, f)
        r = run(m)
        points.append(SensitivityPoint(factor=f, npv=r.metrics.npv, irr_annual=r.metrics.irr_annual))
    return points
