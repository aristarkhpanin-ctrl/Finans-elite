"""Правила «дивергенция»: план ↔ вероятное будущее (см. декомпозицию §2.E).

Опираются на стохастику в контексте (``ctx.mc`` — Монте-Карло, ``ctx.sensitivity`` —
чувствительность). Без неё (обычное, не «глубокое» ревью) правила молчат.
"""
from __future__ import annotations

from decimal import Decimal

from ..config import ReviewConfig
from ..text import fmt_num, fmt_pct, fmt_rub
from ..types import Finding, ReviewContext, Severity

_PARAM_LABELS = {
    "sales_price": "цена продаж",
    "sales_volume": "объём продаж",
    "direct_costs": "прямые издержки",
    "fixed_costs": "постоянные издержки",
}


def fragile_positive_npv(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Базовый NPV положителен, но вероятность NPV>0 по Монте-Карло низка."""
    if ctx.mc is None or ctx.result.metrics.npv <= 0:
        return []
    prob = ctx.mc.probability_npv_positive
    if prob >= config.prob_positive_min:
        return []
    # Хуже случайного: при плюсе в базовом плане будущее чаще уводит в минус.
    severity: Severity = "risk" if prob < Decimal("0.5") else "warning"
    return [Finding(
        id="divergence.fragile_positive_npv", category="divergence", severity=severity,
        confidence="medium",
        title="Положительный NPV неустойчив к колебаниям",
        detail=f"В базовом плане NPV положителен, но при разбросе цен и объёма "
               f"±{fmt_pct(config.mc_spread)} вероятность NPV>0 лишь {fmt_pct(prob)} "
               f"(порог {fmt_pct(config.prob_positive_min)}).",
        recommendation="Плюс держится на оптимистичных допущениях — заложите запас прочности "
                       "по цене и объёму или проверьте их обоснованность.",
        evidence={"prob_positive": str(prob), "base_npv": str(ctx.result.metrics.npv),
                  "iterations": ctx.mc.iterations},
    )]


def heavy_downside(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """У прибыльного в среднем проекта тяжёлый левый хвост: потери > вероятной выгоды."""
    if ctx.mc is None or ctx.result.metrics.npv <= 0:
        return []
    cvar = ctx.mc.npv_cvar_5
    mean = ctx.mc.npv_mean
    if cvar >= 0 or -cvar <= abs(mean):
        return []
    return [Finding(
        id="divergence.heavy_downside", category="divergence", severity="warning",
        confidence="medium",
        title="Тяжёлый левый хвост рисков",
        detail=f"Средний убыток в худших 5% сценариев {fmt_rub(cvar)} ₽ по модулю превышает "
               f"ожидаемый NPV {fmt_rub(mean)} ₽: потенциальные потери больше вероятной выгоды.",
        recommendation="Проработайте защиту от худших сценариев (резервы, хеджирование цен, "
                       "гибкость по объёму) или снизьте экспозицию.",
        evidence={"cvar_5": str(cvar), "npv_mean": str(mean), "npv_p5": str(ctx.mc.npv_p5)},
    )]


def sensitivity_sign_flip(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Небольшой (±band) сдвиг одного драйвера переводит NPV через ноль."""
    if ctx.sensitivity is None:
        return []
    base = ctx.result.metrics.npv
    if base == 0:
        return []
    base_positive = base > 0
    flipped: list[str] = []
    for param, points in ctx.sensitivity.items():
        for pt in points:
            if pt.factor == 1:
                continue
            if pt.npv != 0 and (pt.npv > 0) != base_positive:
                flipped.append(param)
                break
    if not flipped:
        return []
    labels = ", ".join(_PARAM_LABELS.get(p, p) for p in flipped)
    return [Finding(
        id="divergence.sensitivity_sign_flip", category="divergence", severity="warning",
        confidence="medium",
        title="NPV меняет знак при небольшом сдвиге драйвера",
        detail=f"Сдвиг всего на ±{fmt_pct(config.sensitivity_flip_band)} по параметрам "
               f"({labels}) переводит NPV через ноль — результат балансирует на грани.",
        recommendation="Уточните эти чувствительные допущения: от них зависит сам знак итога; "
                       "заложите консервативные значения.",
        evidence={"flipping_params": flipped, "band": str(config.sensitivity_flip_band)},
    )]


def wide_dispersion(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Разброс прогноза NPV (σ/|среднее|) слишком велик — низкая предсказуемость."""
    if ctx.mc is None:
        return []
    mean = ctx.mc.npv_mean
    if mean == 0:
        return []
    cv = ctx.mc.npv_std / abs(mean)
    if cv <= config.dispersion_max:
        return []
    return [Finding(
        id="divergence.wide_dispersion", category="divergence", severity="info",
        confidence="medium",
        title="Очень широкий разброс прогноза NPV",
        detail=f"Стандартное отклонение NPV в {fmt_num(cv)}× превышает средний NPV "
               f"(σ={fmt_rub(ctx.mc.npv_std)} ₽, среднее {fmt_rub(mean)} ₽): прогноз "
               "крайне неопределёнен.",
        recommendation="Сузьте ключевые допущения (диапазоны цен и объёмов) или соберите больше "
                       "данных — предсказательная ценность текущего прогноза низка.",
        evidence={"cv": str(cv), "npv_std": str(ctx.mc.npv_std), "npv_mean": str(mean)},
    )]


RULES = [fragile_positive_npv, heavy_downside, sensitivity_sign_flip, wide_dispersion]
