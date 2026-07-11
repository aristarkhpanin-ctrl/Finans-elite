"""Правила «структура доходов и издержек» (см. декомпозицию §2.C)."""
from __future__ import annotations

from decimal import Decimal

from ...money import ZERO
from ..aggregates import (
    cost_line_totals,
    gross_margin,
    per_product_revenue,
    total_net_revenue,
)
from ..config import ReviewConfig
from ..text import fmt_pct, fmt_rub
from ..types import Finding, ReviewContext


def revenue_concentration(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Один продукт даёт непропорционально большую долю выручки (при ≥2 продуктах)."""
    rev = per_product_revenue(ctx.model)
    positive = {pid: v for pid, v in rev.items() if v > 0}
    total = sum(positive.values(), ZERO)
    # С одним продуктом концентрация тривиальна (это выбор бизнес-модели, не находка модели).
    if len(positive) < 2 or total <= 0:
        return []
    top_id, top_rev = max(positive.items(), key=lambda kv: kv[1])
    share = top_rev / total
    if share <= config.revenue_concentration_max:
        return []
    names = {p.id: p.name for p in ctx.model.operating_plan.products}
    label = names.get(top_id, top_id)
    return [Finding(
        id="structure.revenue_concentration", category="structure", severity="warning",
        title="Высокая концентрация выручки на одном продукте",
        detail=f"Продукт «{label}» даёт {fmt_pct(share)} выручки (порог "
               f"{fmt_pct(config.revenue_concentration_max)}): падение спроса по нему бьёт "
               "по всему плану.",
        recommendation="Проверьте устойчивость спроса на ключевой продукт; рассмотрите "
                       "диверсификацию ассортимента или каналов сбыта.",
        evidence={"top_product": top_id, "top_share": str(share), "products": len(positive)},
    )]


def negative_gross_margin(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Прямые издержки превышают выручку — валовая маржа отрицательна."""
    gm = gross_margin(ctx.result)
    if gm is None or gm >= 0:
        return []
    return [Finding(
        id="structure.negative_gross_margin", category="structure", severity="risk",
        title="Отрицательная валовая маржа",
        detail=f"Валовая маржа {fmt_pct(gm)}: прямые издержки превышают выручку — каждая "
               "дополнительная продажа увеличивает убыток.",
        recommendation="Поднимите цены или снизьте прямую себестоимость: при отрицательной "
                       "марже рост объёма только усугубляет убыток.",
        evidence={"gross_margin": str(gm)},
    )]


def thin_gross_margin(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Валовая маржа положительна, но очень тонкая — нет запаса прочности."""
    gm = gross_margin(ctx.result)
    if gm is None or gm < 0 or gm >= config.thin_gross_margin:
        return []
    return [Finding(
        id="structure.thin_gross_margin", category="structure", severity="warning",
        title="Очень тонкая валовая маржа",
        detail=f"Валовая маржа {fmt_pct(gm)} ниже {fmt_pct(config.thin_gross_margin)}: "
               "небольшое отклонение цен или издержек уводит проект в минус.",
        recommendation="Заложите запас по марже или проверьте чувствительность к цене "
                       "и прямой себестоимости.",
        evidence={"gross_margin": str(gm)},
    )]


def _quantile(sorted_vals: list[Decimal], q: Decimal) -> Decimal:
    """Квантиль по отсортированному ряду (линейная интерполяция, как numpy type 7)."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (Decimal(len(sorted_vals)) - 1) * q
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac
    return sorted_vals[lo]


def cost_line_outlier(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Статья издержек выпадает из общего ряда (верхний выброс IQR) и весома к выручке.

    Внутренняя относительная проверка (без внешнего бенчмарка): статья должна быть и
    статистическим выбросом среди других статей, и существенной (> порога доли выручки).
    """
    lines = cost_line_totals(ctx.model)
    if len(lines) < 4:                       # IQR неустойчив на малой выборке
        return []
    revenue = total_net_revenue(ctx.result)
    if revenue <= 0:
        return []
    values = sorted(v for _, v in lines)
    q1 = _quantile(values, Decimal("0.25"))
    q3 = _quantile(values, Decimal("0.75"))
    fence = q3 + config.cost_outlier_iqr_k * (q3 - q1)
    findings: list[Finding] = []
    for name, acc in lines:
        if acc > fence and acc > config.cost_outlier_rev_share * revenue:
            findings.append(Finding(
                id="structure.cost_line_outlier", category="structure", severity="info",
                confidence="medium",
                title=f"Издержка «{name}» заметно выделяется",
                detail=f"«{name}» — {fmt_rub(acc)} ₽ за горизонт ({fmt_pct(acc / revenue)} "
                       "выручки) — выпадает из общего ряда статей издержек (верхний выброс IQR).",
                recommendation="Проверьте обоснованность статьи: норму расхода, цену, отсутствие "
                               "дубля; при возможности сравните с отраслевым ориентиром.",
                evidence={"line": name, "total": str(acc),
                          "share_of_revenue": str(acc / revenue), "iqr_upper_fence": str(fence)},
            ))
    return findings


RULES = [revenue_concentration, negative_gross_margin, thin_gross_margin, cost_line_outlier]
