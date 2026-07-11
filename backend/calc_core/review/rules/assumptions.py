"""Правила «допущения»: мягкие info-нахождения о рискованных упрощениях (декомпозиция §2.D)."""
from __future__ import annotations

from ...models.operating import SalesLine
from ..config import ReviewConfig
from ..text import fmt_pct
from ..types import Finding, ReviewContext


def zero_tax(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Ставка налога на прибыль равна нулю — чистая прибыль/поток могут быть завышены."""
    rate = ctx.model.settings.profit_tax_rate
    if rate != 0:
        return []
    return [Finding(
        id="assumptions.zero_tax", category="assumptions", severity="info",
        title="Налог на прибыль не заложен",
        detail="Ставка налога на прибыль равна 0%. Если проект не на льготном режиме, "
               "чистая прибыль и денежный поток завышены на сумму налога.",
        recommendation="Укажите фактическую ставку налога на прибыль (или подтвердите льготный "
                       "режим), чтобы прогноз был реалистичным.",
        evidence={"profit_tax_rate": str(rate)},
    )]


def discount_below_inflation(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Ставка дисконтирования ниже инфляции цен сбыта — реальная доходность отрицательна."""
    disc = ctx.model.settings.discount_rate_annual
    infl = ctx.model.settings.inflation_sales
    if infl <= 0 or disc >= infl:
        return []
    return [Finding(
        id="assumptions.discount_below_inflation", category="assumptions", severity="info",
        confidence="medium",
        title="Ставка дисконтирования ниже инфляции",
        detail=f"Ставка дисконтирования {fmt_pct(disc)} ниже инфляции цен сбыта {fmt_pct(infl)}: "
               "реальная требуемая доходность отрицательна, а NPV может быть завышен.",
        recommendation="Обычно ставка дисконтирования выше инфляции (реальная доходность > 0) — "
                       "проверьте её обоснованность.",
        evidence={"discount_rate_annual": str(disc), "inflation_sales": str(infl)},
    )]


def instant_settlement(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Во всех статьях расчёты мгновенные — оборотный капитал (дебиторка/кредиторка) не виден."""
    op = ctx.model.operating_plan
    if not (op.sales or op.direct_costs or op.fixed_costs):
        return []

    def _instant_sale(s: SalesLine) -> bool:
        p = s.payment
        return (p.prepayment_share == 0 and p.advance_lead_months == 0
                and p.payment_delay_months == 0)

    all_instant = (
        all(_instant_sale(s) for s in op.sales)
        and all(d.payment_delay_months == 0 and d.stock_lead_months == 0 for d in op.direct_costs)
        and all(f.payment_delay_months == 0 for f in op.fixed_costs)
    )
    if not all_instant:
        return []
    return [Finding(
        id="assumptions.instant_settlement", category="assumptions", severity="info",
        confidence="medium",
        title="Расчёты предполагаются мгновенными",
        detail="Во всех статьях нет отсрочек и предоплат: оплата совпадает с начислением. "
               "Дебиторка, кредиторка и авансы не моделируются — возможные кассовые разрывы "
               "из-за реальных отсрочек платежей не видны.",
        recommendation="Если по факту есть отсрочки, задайте их в условиях оплаты — это точнее "
                       "покажет потребность в оборотном капитале.",
        evidence={},
    )]


RULES = [zero_tax, discount_below_inflation, instant_settlement]
