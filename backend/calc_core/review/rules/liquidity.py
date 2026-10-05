"""Правила «ликвидность / структура капитала» (см. декомпозицию §2.B)."""
from __future__ import annotations

from decimal import Decimal

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


def _covered_years(ctx: ReviewContext):
    debt = ctx.result.debt_service
    if debt is None:
        return []
    return [y for y in debt.years if y.dscr is not None]


def dscr_below_one(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Поток не покрывает платежи по долгу (DSCR < 1) хотя бы в одном году — risk."""
    below = [y for y in _covered_years(ctx) if y.dscr is not None and y.dscr < 1]
    if not below:
        return []
    worst = min(below, key=lambda y: y.dscr if y.dscr is not None else ZERO)
    gap = sum((y.shortfall for y in below), ZERO)
    years = ", ".join(y.label for y in below)
    return [Finding(
        id="liquidity.dscr_below_one", category="liquidity", severity="risk",
        title="Поток не покрывает платежи по долгу",
        detail=f"Покрытие долга (DSCR) ниже 1 — {years}: платежи по займам и лизингу больше "
               f"потока, доступного для их обслуживания. Худший год — {worst.label}: DSCR "
               f"{fmt_num(worst.dscr or ZERO)}, не хватает {fmt_rub(worst.shortfall)} ₽; "
               f"всего за такие годы — {fmt_rub(gap)} ₽ платежей из других денег. С таким "
               "планом банк кредит обычно не выдаёт.",
        recommendation="Удлините срок займа или отсрочку погашения, уменьшите сумму долга "
                       "за счёт капитала либо сдвиньте погашение на годы с большим потоком.",
        evidence={"worst_year": worst.label, "worst_dscr": str(worst.dscr),
                  "worst_shortfall": str(worst.shortfall), "shortfall_total": str(gap),
                  "years_below": len(below)},
    )]


def dscr_below_bank_norm(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Покрытие долга не ниже 1, но ниже обычного требования банков — warning.

    Год с DSCR < 1 — это уже risk (:func:`dscr_below_one`); второе предупреждение о том же
    годе было бы шумом, поэтому здесь — только когда ниже единицы не опускается ничего.
    """
    covered = _covered_years(ctx)
    if not covered or any(y.dscr is not None and y.dscr < 1 for y in covered):
        return []
    worst = min(covered, key=lambda y: y.dscr if y.dscr is not None else ZERO)
    if worst.dscr is None or worst.dscr >= config.dscr_min:
        return []
    return [Finding(
        id="liquidity.dscr_below_bank_norm", category="liquidity", severity="warning",
        title="Покрытие долга ниже обычного требования банков",
        detail=f"Наименьшее покрытие долга (DSCR) — {fmt_num(worst.dscr)} в {worst.label}: "
               f"поток платежи покрывает, но банки обычно требуют не ниже "
               f"{fmt_num(config.dscr_min)} — запас на случай, если выручка отстанет от "
               "плана. Это практика банков, а не норма закона.",
        recommendation="Проверьте требования своего банка; запас покрытия даёт более "
                       "длинный срок займа, отсрочка погашения или больше капитала.",
        evidence={"min_dscr": str(worst.dscr), "year": worst.label,
                  "bank_norm": str(config.dscr_min)},
    )]


def leverage_high(ctx: ReviewContext, config: ReviewConfig) -> list[Finding]:
    """Долговая нагрузка выше обычного предела банков в годы погашения — warning.

    Смотрим только **полные годы с плановым погашением тела**: на стройке долг уже есть,
    а EBITDA ещё нет, и предупреждение о каждом проекте с периодом строительства было бы
    шумом. Банки и сами проверяют этот предел после выхода на погашение.
    """
    debt = ctx.result.debt_service
    if debt is None:
        return []
    flagged = []
    for y in debt.years:
        if y.months < 12 or y.principal <= 0 or y.net_debt <= 0:
            continue
        if y.ebitda <= 0 or (y.leverage is not None and y.leverage > config.leverage_max):
            flagged.append(y)
    if not flagged:
        return []
    worst = max(flagged, key=lambda y: y.leverage if y.leverage is not None
                else Decimal("Infinity"))
    if worst.leverage is None:
        what = (f"в {worst.label} чистый долг {fmt_rub(worst.net_debt)} ₽, а EBITDA не "
                f"положительна ({fmt_rub(worst.ebitda)} ₽)")
    else:
        what = (f"в {worst.label} чистый долг — {fmt_num(worst.leverage)} годовых EBITDA "
                f"({fmt_rub(worst.net_debt)} ₽ против {fmt_rub(worst.ebitda)} ₽)")
    return [Finding(
        id="liquidity.leverage_high", category="liquidity", severity="warning",
        title="Долговая нагрузка выше обычного предела банков",
        detail=f"В годы погашения {what}; банки обычно ограничивают нагрузку "
               f"{fmt_num(config.leverage_max)} годовыми EBITDA. Это практика, а не норма "
               "закона.",
        recommendation="Уменьшите долг за счёт капитала или проверьте, реалистичен ли рост "
                       "EBITDA в годы погашения.",
        evidence={"year": worst.label, "net_debt": str(worst.net_debt),
                  "ebitda": str(worst.ebitda),
                  "leverage": str(worst.leverage) if worst.leverage is not None else "",
                  "bank_limit": str(config.leverage_max)},
    )]


RULES = [cash_gap, financing_dependency, current_ratio_low, overleverage, interest_coverage_low,
         dscr_below_one, dscr_below_bank_norm, leverage_high]
