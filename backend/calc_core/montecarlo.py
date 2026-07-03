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
from .money import ZERO, D
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
class HistogramBin:
    """Столбец гистограммы распределения NPV: [from_, to) и число попаданий."""

    from_: Decimal
    to: Decimal
    count: int


@dataclass
class MonteCarloResult:
    iterations: int
    npv_mean: Decimal
    npv_std: Decimal
    npv_sem: Decimal          # стандартная ошибка среднего = σ/√N (достаточно ли итераций)
    npv_min: Decimal
    npv_max: Decimal
    npv_p5: Decimal           # 5-й перцентиль = VaR при доверии 95%
    npv_p10: Decimal
    npv_p50: Decimal
    npv_p90: Decimal
    npv_p95: Decimal
    npv_cvar_5: Decimal       # CVaR/ES 95%: среднее худших 5% исходов
    probability_npv_positive: Decimal
    histogram: list[HistogramBin]


# Число столбцов гистограммы распределения NPV (B5).
HISTOGRAM_BINS = 20

# Доля худшего хвоста для VaR/CVaR (5% → доверие 95%).
TAIL_DENOM = 20


def _req(value: Decimal | None, param: str, kind: str) -> float:
    """Обязательный параметр распределения → float (иначе понятная ошибка вместо float(None))."""
    if value is None:
        raise ValueError(f"Распределение «{kind}»: не задан параметр «{param}»")
    return float(value)


def _sample_factor(rng: random.Random, d: Distribution) -> Decimal:
    if d.kind == "uniform":
        f = rng.uniform(_req(d.low, "low", d.kind), _req(d.high, "high", d.kind))
    elif d.kind == "normal":
        f = rng.gauss(_req(d.mean, "mean", d.kind), _req(d.std, "std", d.kind))
    elif d.kind == "triangular":
        f = rng.triangular(_req(d.low, "low", d.kind), _req(d.high, "high", d.kind),
                           _req(d.mode, "mode", d.kind))
    else:
        raise ValueError(f"Неизвестное распределение: {d.kind}")
    return max(ZERO, D(str(f)))  # коэффициент не может быть отрицательным


def _percentile(sorted_vals: list[Decimal], p: int) -> Decimal:
    if not sorted_vals:
        return ZERO
    idx = (p * (len(sorted_vals) - 1) + 50) // 100  # ближайший ранг
    return sorted_vals[idx]


def _histogram(ordered: list[Decimal], bins: int = HISTOGRAM_BINS) -> list[HistogramBin]:
    """Гистограмма из ``bins`` равных столбцов от min до max (B5).

    Границы — Decimal (точность сохраняется). Каждое значение попадает ровно в один
    столбец (последний — полузакрытый справа, чтобы max не выпал); сумма count = len.
    """
    lo, hi = ordered[0], ordered[-1]
    if hi == lo:
        # Все NPV равны — один столбец на все итерации, остальные пустые.
        result = [HistogramBin(from_=lo, to=hi, count=0) for _ in range(bins)]
        result[0] = HistogramBin(from_=lo, to=hi, count=len(ordered))
        return result
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in ordered:
        idx = int((x - lo) / width)
        if idx >= bins:
            idx = bins - 1  # max попадает в последний столбец
        counts[idx] += 1
    return [
        HistogramBin(from_=lo + width * k, to=lo + width * (k + 1), count=counts[k])
        for k in range(bins)
    ]


def _statistics(npvs: list[Decimal]) -> MonteCarloResult:
    n = len(npvs)
    total = sum(npvs, ZERO)
    mean = total / n
    var = sum(((x - mean) ** 2 for x in npvs), ZERO) / n
    std = var.sqrt()
    sem = std / D(n).sqrt() if n > 0 else ZERO
    positive = sum(1 for x in npvs if x > 0)
    ordered = sorted(npvs)
    # CVaR/Expected Shortfall 95%: среднее худших 5% исходов (хвост ≥ 1 наблюдение).
    tail = max(1, n // TAIL_DENOM)
    cvar_5 = sum(ordered[:tail], ZERO) / tail
    return MonteCarloResult(
        iterations=n,
        npv_mean=mean,
        npv_std=std,
        npv_sem=sem,
        npv_min=ordered[0],
        npv_max=ordered[-1],
        npv_p5=_percentile(ordered, 5),
        npv_p10=_percentile(ordered, 10),
        npv_p50=_percentile(ordered, 50),
        npv_p90=_percentile(ordered, 90),
        npv_p95=_percentile(ordered, 95),
        npv_cvar_5=cvar_5,
        probability_npv_positive=D(positive) / n,
        histogram=_histogram(ordered),
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
