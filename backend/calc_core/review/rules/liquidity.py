"""Правила «ликвидность / структура капитала» (см. декомпозицию §2.B)."""
from __future__ import annotations

from ...money import ZERO
from ..aggregates import ebit_total, interest_total, series, total
from ..config import ReviewConfig
from ..text import fmt_num, fmt_rub
from ..types import Finding, ReviewContext, Severity


def cash_gap(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Денежные средства уходят в минус при выключенном автоподборе — план не обеспечен."""
    if ctx.model.financing.auto_financing.enabled:
        return []
    b1 = series(ctx.result.balance, "B1")
    negatives = [(t, v) for t, v in enumerate(b1) if v < 0]
    if not negatives:
        return []
    worst_t, worst_v = min(negatives, key=lambda tv: tv[1])
    return [Finding(
        id="liquidity.cash_gap", category="liquidity", severity="risk",
        title="Кассовый разрыв: денежные средства уходят в минус",
        detail=f"В {len(negatives)} мес. остаток денежных средств отрицателен; наибольший дефицит "
               f"{fmt_rub(worst_v)} ₽ в месяце {worst_t + 1}. Автоподбор финансирования выключен — "
               "план деньгами не обеспечен.",
        recommendation="Включите автоподбор финансирования, добавьте кредитную линию или взнос "
                       "капитала, либо сдвиньте платежи, чтобы закрыть разрыв.",
        evidence={"worst_month": worst_t + 1, "worst_balance": str(worst_v),
                  "months_negative": len(negatives)},
    )]


def financing_dependency(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Пиковая потребность в финансировании многократно превышает собственный капитал."""
    peak = ctx.result.metrics.peak_financing_need
    if peak is None or peak <= 0:
        return []
    equity = total(ctx.result.cashflow, "C21")
    if equity <= 0 or peak <= config.financing_to_equity_max * equity:
        return []
    ratio = peak / equity
    return [Finding(
        id="liquidity.financing_dependency", category="liquidity", severity="warning",
        title="Высокая зависимость от привлечённого финансирования",
        detail=f"Пиковая потребность в финансировании {fmt_rub(peak)} ₽ превышает собственный "
               f"капитал {fmt_rub(equity)} ₽ в {fmt_num(ratio)}× (порог "
               f"{fmt_num(config.financing_to_equity_max)}×).",
        recommendation="Увеличьте долю собственных средств или пересмотрите график вложений, "
                       "чтобы снизить нагрузку на заёмное финансирование.",
        evidence={"peak_financing_need": str(peak), "equity": str(equity), "ratio": str(ratio)},
    )]


def current_ratio_low(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Текущие активы не покрывают краткосрочные обязательства в худшем месяце."""
    b8 = series(ctx.result.balance, "B8")
    b25 = series(ctx.result.balance, "B25")
    ratios = [(t, b8[t] / b25[t]) for t in range(min(len(b8), len(b25))) if b25[t] > 0]
    if not ratios:
        return []
    worst_t, worst = min(ratios, key=lambda tv: tv[1])
    if worst >= config.current_ratio_min:
        return []
    return [Finding(
        id="liquidity.current_ratio_low", category="liquidity", severity="warning",
        title="Низкая текущая ликвидность",
        detail=f"Коэффициент текущей ликвидности опускается до {fmt_num(worst)} в месяце "
               f"{worst_t + 1} (порог {fmt_num(config.current_ratio_min)}): текущие активы "
               "не покрывают краткосрочные обязательства.",
        recommendation="Нарастите оборотный капитал или сократите краткосрочные обязательства "
                       "в проблемные периоды.",
        evidence={"min_current_ratio": str(worst), "month": worst_t + 1},
    )]


def overleverage(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Заёмные средства на конец горизонта многократно превышают собственный капитал."""
    b22 = series(ctx.result.balance, "B22")
    b26 = series(ctx.result.balance, "B26")
    b33 = series(ctx.result.balance, "B33")
    if not b33:
        return []
    equity = b33[-1]
    if equity <= 0:
        return []
    debt = (b22[-1] if b22 else ZERO) + (b26[-1] if b26 else ZERO)
    de = debt / equity
    if de <= config.debt_equity_max:
        return []
    return [Finding(
        id="liquidity.overleverage", category="liquidity", severity="warning",
        title="Высокий финансовый рычаг",
        detail=f"На конец горизонта заёмные средства превышают собственный капитал в "
               f"{fmt_num(de)}× (порог {fmt_num(config.debt_equity_max)}×): долг {fmt_rub(debt)} ₽ "
               f"против капитала {fmt_rub(equity)} ₽.",
        recommendation="Увеличьте капитализацию или гасите займы быстрее, чтобы снизить рычаг.",
        evidence={"debt_to_equity": str(de), "debt": str(debt), "equity": str(equity)},
    )]


def interest_coverage_low(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """EBIT слабо покрывает проценты по кредитам (risk при покрытии < 1)."""
    interest = interest_total(ctx.result)
    if interest <= 0:
        return []
    ebit = ebit_total(ctx.result)
    coverage = ebit / interest
    if coverage >= config.interest_coverage_min:
        return []
    severity: Severity = "risk" if coverage < 1 else "warning"
    return [Finding(
        id="liquidity.interest_coverage_low", category="liquidity", severity=severity,
        title="Низкое покрытие процентов прибылью",
        detail=f"Покрытие процентов {fmt_num(coverage)}× (EBIT/проценты) ниже порога "
               f"{fmt_num(config.interest_coverage_min)}×: операционная прибыль слабо покрывает "
               "обслуживание долга.",
        recommendation="Снизьте долговую нагрузку или повысьте операционную прибыль; "
                       "пересмотрите ставку и график займов.",
        evidence={"interest_coverage": str(coverage), "ebit": str(ebit), "interest": str(interest)},
    )]


RULES = [cash_gap, financing_dependency, current_ratio_low, overleverage, interest_coverage_low]
