"""Пороги правил ревью (дефолты; глобальные — здесь, per-org — позже)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ReviewConfig:
    # Ликвидность / структура капитала
    current_ratio_min: Decimal = Decimal("1.0")
    debt_equity_max: Decimal = Decimal("2.0")
    interest_coverage_min: Decimal = Decimal("1.5")   # < 1.0 → risk
    financing_to_equity_max: Decimal = Decimal("3.0")
    # Структура доходов/издержек
    revenue_concentration_max: Decimal = Decimal("0.70")
    thin_gross_margin: Decimal = Decimal("0.10")
    cost_outlier_iqr_k: Decimal = Decimal("1.5")
    cost_outlier_rev_share: Decimal = Decimal("0.30")
    # Дивергенция (план ↔ вероятное будущее)
    prob_positive_min: Decimal = Decimal("0.60")
    dispersion_max: Decimal = Decimal("1.0")           # σ / |mean|
    sensitivity_flip_band: Decimal = Decimal("0.10")   # ±10%
    # Дефолт-прогон стохастики внутри ревью (divergence)
    mc_iterations: int = 300
    mc_seed: int = 42
    mc_spread: Decimal = Decimal("0.15")               # ±15% uniform по цене/объёму


DEFAULT_CONFIG = ReviewConfig()
