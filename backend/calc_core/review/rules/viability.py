"""Правила «жизнеспособность»: NPV/IRR/PI/окупаемость (см. декомпозицию §2.A)."""
from __future__ import annotations

from decimal import Decimal

from ...money import ZERO
from ..aggregates import series
from ..config import ReviewConfig
from ..text import fmt_num, fmt_pct, fmt_rub
from ..types import Finding, ReviewContext, Severity


def npv_negative(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    npv = ctx.result.metrics.npv
    if npv >= 0:
        return []
    disc = ctx.model.settings.discount_rate_annual
    return [Finding(
        id="viability.npv_negative", category="viability", severity="risk",
        title="Отрицательный NPV — проект разрушает стоимость",
        detail=f"NPV = {fmt_rub(npv)} ₽ при ставке дисконтирования {fmt_pct(disc)}: "
               "дисконтированные притоки не покрывают вложения.",
        recommendation="Пересмотрите цены/объёмы/издержки или требуемую доходность; "
                       "проверьте реалистичность допущений.",
        evidence={"npv": str(npv), "discount_rate_annual": str(disc)},
    )]


def irr_below_hurdle(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    irr = ctx.result.metrics.irr_annual
    disc = ctx.model.settings.discount_rate_annual
    if irr is None or irr >= disc:
        return []
    severity: Severity = "risk" if ctx.result.metrics.npv <= 0 else "warning"
    return [Finding(
        id="viability.irr_below_hurdle", category="viability", severity=severity,
        title="IRR ниже требуемой доходности",
        detail=f"IRR = {fmt_pct(irr)} ниже ставки дисконтирования {fmt_pct(disc)} — "
               "проект не покрывает стоимость капитала.",
        recommendation="Повысьте маржинальность/оборачиваемость или пересмотрите барьерную ставку.",
        evidence={"irr_annual": str(irr), "discount_rate_annual": str(disc)},
    )]


def irr_undefined(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    if ctx.result.metrics.irr_annual is not None:
        return []
    return [Finding(
        id="viability.irr_undefined", category="viability", severity="info", confidence="medium",
        title="IRR не определена",
        detail="Внутренняя норма доходности не вычислена (нет корректной смены знака потока "
               "или отсутствуют притоки). Ориентируйтесь на NPV и PI.",
        recommendation="Убедитесь, что в модели есть и вложения, и последующие поступления.",
        evidence={},
    )]


def pi_below_one(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    pi = ctx.result.metrics.pi
    if pi is None or pi >= 1:
        return []
    return [Finding(
        id="viability.pi_below_one", category="viability", severity="warning",
        title="Индекс прибыльности (PI) меньше 1",
        detail=f"PI = {fmt_num(pi)}: приведённая отдача меньше приведённых вложений.",
        recommendation="Проект возвращает меньше вложенного — усильте юнит-экономику "
                       "или сократите капитальные затраты.",
        evidence={"pi": str(pi)},
    )]


def no_payback(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    if ctx.result.metrics.pb_months is not None:
        return []
    return [Finding(
        id="viability.no_payback", category="viability", severity="warning",
        title="Проект не окупается в пределах горизонта",
        detail=f"Простая окупаемость не достигнута за {ctx.result.n} мес.",
        recommendation="Удлините горизонт планирования или ускорьте выход на положительный поток.",
        evidence={"horizon_months": ctx.result.n},
    )]


def _sign_changes(flow: list[Decimal]) -> int:
    signs = [1 if x > 0 else -1 if x < 0 else 0 for x in flow]
    nonzero = [s for s in signs if s != 0]
    return sum(1 for a, b in zip(nonzero, nonzero[1:], strict=False) if a != b)


def irr_unreliable(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    if ctx.result.metrics.irr_annual is None:
        return []
    cf = ctx.result.cashflow
    n = ctx.result.n
    c13, c20 = series(cf, "C13"), series(cf, "C20")  # операционный + инвестиционный (до финанс.)
    pre = [(c13[t] if t < len(c13) else ZERO) + (c20[t] if t < len(c20) else ZERO) for t in range(n)]
    changes = _sign_changes(pre)
    if changes < 2:
        return []
    return [Finding(
        id="viability.irr_unreliable", category="viability", severity="info", confidence="medium",
        title="IRR может быть неоднозначна",
        detail=f"Поток до финансирования меняет знак {changes} раз — у уравнения IRR возможно "
               "несколько корней. Ключевой критерий — NPV.",
        recommendation="Трактуйте единственное значение IRR осторожно; опирайтесь на NPV.",
        evidence={"sign_changes": changes},
    )]


RULES = [npv_negative, irr_below_hurdle, irr_undefined, pi_below_one, no_payback, irr_unreliable]
