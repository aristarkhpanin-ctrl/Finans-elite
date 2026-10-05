"""Стохастика для категории divergence: прогон Монте-Карло и чувствительности.

Дорого (пере-прогоны движка), поэтому считается лениво — только при «глубоком» ревью
(``run_review(..., deep=True)``) и только если стохастика ещё не передана в контексте.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from ..montecarlo import Distribution, MonteCarloConfig, UncertainParam, run_monte_carlo
from ..sensitivity import run_sensitivity
from .config import ReviewConfig
from .types import ReviewContext

#: Драйверы для проверки смены знака NPV (divergence.sensitivity_sign_flip).
_SENSITIVITY_PARAMS = ["sales_price", "sales_volume", "direct_costs", "fixed_costs"]

#: Неопределённые драйверы Монте-Карло: цена и объём, равномерно ±mc_spread.
_MC_PARAMS = ["sales_price", "sales_volume"]


def enrich_context(ctx: ReviewContext, config: ReviewConfig) -> ReviewContext:
    """Вернуть контекст со стохастикой (MC + чувствительность); уже заданную — не пересчитывает."""
    mc = ctx.mc
    if mc is None:
        spread = config.mc_spread
        dist = Distribution(kind="uniform", low=Decimal(1) - spread, high=Decimal(1) + spread)
        mc_config = MonteCarloConfig(
            iterations=config.mc_iterations, seed=config.mc_seed,
            uncertain=[UncertainParam(param, dist) for param in _MC_PARAMS],
        )
        mc = run_monte_carlo(ctx.model, mc_config)
    sensitivity = ctx.sensitivity
    if sensitivity is None:
        band = config.sensitivity_flip_band
        factors = [Decimal(1) - band, Decimal(1), Decimal(1) + band]
        sensitivity = {param: run_sensitivity(ctx.model, param, factors)
                       for param in _SENSITIVITY_PARAMS}
    return replace(ctx, mc=mc, sensitivity=sensitivity)
