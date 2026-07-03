"""Мост между схемами запроса и конфигом ядра анализа (общий код sync и фоновой задачи)."""
from __future__ import annotations

from calc_core.montecarlo import Distribution, MonteCarloConfig, UncertainParam

from .schemas import MonteCarloRequest


def build_mc_config(body: MonteCarloRequest) -> MonteCarloConfig:
    return MonteCarloConfig(
        iterations=body.iterations,
        seed=body.seed,
        uncertain=[
            UncertainParam(param=u.param, distribution=Distribution(
                kind=u.distribution.kind, low=u.distribution.low, high=u.distribution.high,
                mean=u.distribution.mean, std=u.distribution.std, mode=u.distribution.mode))
            for u in body.uncertain
        ],
    )
