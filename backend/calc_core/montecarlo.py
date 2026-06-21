"""Анализ Монте-Карло (7.4; SPEC §20).

Неопределённым параметрам присваиваются распределения коэффициентов; выполняется N
прогонов модели со случайной выборкой, на выходе — статистика NPV (среднее, σ, мин/макс,
перцентили) и вероятность ``NPV > 0`` («устойчивость проекта»).

Точность: базовый расчёт каждой итерации — Decimal; сэмплирование коэффициентов — через
``random`` (float, как допускает спецификация) с фиксируемым ``seed`` для воспроизводимости.
Статистика считается на Decimal.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .models import ProjectModel
from .money import D, ZERO
from .sensitivity import SENSITIVITY_PARAMS


@dataclass
class Distribution:
    """Распределение коэффициента: uniform(low, high) | normal(mean, std) | triangular(low, mode, high)."""

    kind: str
    low: Optional[Decimal] = None
    high: Optional[Decimal] = None
    mean: Optional[Decimal] = None
    std: Optional[Decimal] = None
    mode: Optional[Decimal] = None


@dataclass
class UncertainParam:
    param: str               # один из SENSITIVITY_PARAMS
    distribution: Distribution


@dataclass
class MonteCarloConfig:
    iterations: int = 500
    seed: int = 42
    uncertain: list[UncertainParam] = None  # type: ignore[assignment]


@dataclass
class MonteCarloResult:
    iterations: int
    npv_mean: Decimal
    npv_std: Decimal
    npv_min: Decimal
    npv_max: Decimal
    npv_p10: Decimal
    npv_p50: Decimal
    npv_p90: Decimal
    probability_npv_positive: Decimal


def _sample_factor(rng: random.Random, d: Distribution) -> Decimal:
    if d.kind == "uniform":
        f = rng.uniform(float(d.low), float(d.high))
    elif d.kind == "normal":
        f = rng.gauss(float(d.mean), float(d.std))
    elif d.kind == "triangular":
        f = rng.triangular(float(d.low), float(d.high), float(d.mode))
    else:
        raise ValueError(f"Неизвестное распределение: {d.kind}")
    return max(ZERO, D(str(f)))  # коэффициент не может быть отрицательным


def _percentile(sorted_vals: list[Decimal], p: int) -> Decimal:
    if not sorted_vals:
        return ZERO
    idx = (p * (len(sorted_vals) - 1) + 50) // 100  # ближайший ранг
    return sorted_vals[idx]


def _statistics(npvs: list[Decimal]) -> MonteCarloResult:
    n = len(npvs)
    total = sum(npvs, ZERO)
    mean = total / n
    var = sum(((x - mean) ** 2 for x in npvs), ZERO) / n
    std = var.sqrt()
    positive = sum(1 for x in npvs if x > 0)
    ordered = sorted(npvs)
    return MonteCarloResult(
        iterations=n,
        npv_mean=mean,
        npv_std=std,
        npv_min=ordered[0],
        npv_max=ordered[-1],
        npv_p10=_percentile(ordered, 10),
        npv_p50=_percentile(ordered, 50),
        npv_p90=_percentile(ordered, 90),
        probability_npv_positive=D(positive) / n,
    )


def run_monte_carlo(model: ProjectModel, config: MonteCarloConfig) -> MonteCarloResult:
    """Выполнить N прогонов со случайной выборкой коэффициентов; вернуть статистику NPV."""
    from .engine import run  # локальный импорт (избегаем цикла)

    if config.iterations <= 0:
        raise ValueError("Число итераций должно быть положительным")
    for up in (config.uncertain or []):
        if up.param not in SENSITIVITY_PARAMS:
            raise ValueError(f"Неизвестный параметр: {up.param}")

    rng = random.Random(config.seed)
    npvs: list[Decimal] = []
    for _ in range(config.iterations):
        m = model.model_copy(deep=True)
        for up in (config.uncertain or []):
            SENSITIVITY_PARAMS[up.param](m, _sample_factor(rng, up.distribution))
        npvs.append(run(m).metrics.npv)
    return _statistics(npvs)
