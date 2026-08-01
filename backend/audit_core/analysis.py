"""Аналитическое ядро Финанс-Аудит: аналитическая форма, тренды, коэффициенты.

Чистая детерминированная функция ``analyze(model) -> AuditResult`` над введённой
фактической отчётностью (SPEC продукта №2, приложения А–Б). Считается в фиксированном
контексте ``CALC_CONTEXT`` (как первый продукт) — результат не зависит от потока/хоста.

Соглашения:

- **Аналитическая форма** — введённые агрегаты РСБУ плюс производные подытоги (оборотные
  активы, итог актива/пассива; валовая прибыль, операционная прибыль, прибыль до налога,
  чистая прибыль). Ничего не «досочиняется»: подытоги — арифметика над введённым.
- **Годовые показатели** (рентабельность, оборачиваемость активов) приводятся к году по типу
  периода (квартал → ×4, месяц → ×12): периоды разной длины иначе несопоставимы. Показатели
  «в днях» считаются по длине периода и приведения не требуют.
- Показатель с нулевой базой → ``None`` (не 0): «не определён» и «ноль» — разные факты.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Optional

from calc_core.formula import FormulaError, evaluate
from calc_core.formula.functions import as_series
from calc_core.money import CALC_CONTEXT, ZERO

from .diagnostics import build_overrides, compute_diagnostics
from .lines import ASSET_CODES, EQLIAB_CODES, INCOME_LINES, LABELS
from .models import AuditSubjectModel
from .result import (
    AuditLine,
    AuditResult,
    RatioSeries,
    ShareLine,
    TrendLine,
    UserMetricResult,
)

#: Тип периода → (длина в днях, множитель приведения потока к году).
#: Множитель задан явно (1/4/12), а не выведен делением — так он точен для любого типа.
_PERIOD: dict[str, tuple[Decimal, Decimal]] = {
    "year": (Decimal(365), Decimal(1)),
    "quarter": (Decimal("91.25"), Decimal(4)),
    "month": (Decimal(365) / Decimal(12), Decimal(12)),
}
_DEFAULT_PERIOD = _PERIOD["year"]

# Коды производных строк аналитической формы (подытоги).
CURRENT_ASSETS = "A_CURRENT"
TOTAL_ASSETS = "A_TOTAL"
TOTAL_EQLIAB = "P_TOTAL"
GROSS_PROFIT = "I_GROSS"
OPERATING_PROFIT = "I_EBIT"
PROFIT_BEFORE_TAX = "I_EBT"
NET_PROFIT = "I_NET"

_DERIVED_LABELS = {
    CURRENT_ASSETS: "Оборотные активы",
    TOTAL_ASSETS: "СУММАРНЫЙ АКТИВ",
    TOTAL_EQLIAB: "СУММАРНЫЙ ПАССИВ",
    GROSS_PROFIT: "Валовая прибыль",
    OPERATING_PROFIT: "Операционная прибыль (EBIT)",
    PROFIT_BEFORE_TAX: "Прибыль до налогообложения",
    NET_PROFIT: "Чистая прибыль",
}


def _div(a: Decimal, b: Decimal) -> Optional[Decimal]:
    """Деление с «не определено» при нулевой базе (вместо подстановки нуля)."""
    return None if b == 0 else a / b


def _add(*rows: list[Decimal]) -> list[Decimal]:
    n = len(rows[0]) if rows else 0
    return [sum((r[t] for r in rows), ZERO) for t in range(n)]


def _sub(a: list[Decimal], b: list[Decimal]) -> list[Decimal]:
    return [a[t] - b[t] for t in range(len(a))]


def analyze(model: AuditSubjectModel) -> AuditResult:
    """Проанализировать фактическую отчётность субъекта."""
    with localcontext(CALC_CONTEXT):
        return _analyze(model)


def _analyze(model: AuditSubjectModel) -> AuditResult:
    n = model.n
    if n == 0:
        return AuditResult(n=0)

    # ── Аналитическая форма ───────────────────────────────────────────────────
    bal_raw = {code: model.balance_row(code) for code in ASSET_CODES + EQLIAB_CODES}
    inc_raw = {code: model.income_row(code) for code, _ in INCOME_LINES}

    current = _add(bal_raw["A_INVENTORY"], bal_raw["A_RECEIVABLE"], bal_raw["A_CASH"])
    total_assets = _add(*[bal_raw[c] for c in ASSET_CODES])
    total_eqliab = _add(*[bal_raw[c] for c in EQLIAB_CODES])

    gross = _sub(inc_raw["I_REVENUE"], inc_raw["I_COGS"])
    ebit = _sub(gross, inc_raw["I_OPEX"])
    ebt = _add(_sub(ebit, inc_raw["I_INTEREST"]), inc_raw["I_OTHER"])
    net = _sub(ebt, inc_raw["I_TAX"])

    def line(code: str, values: list[Decimal], subtotal: bool = False) -> AuditLine:
        return AuditLine(code=code, label=LABELS.get(code) or _DERIVED_LABELS[code],
                         values=values, subtotal=subtotal)

    balance_lines = [
        line("A_FIXED", bal_raw["A_FIXED"]),
        line("A_INVENTORY", bal_raw["A_INVENTORY"]),
        line("A_RECEIVABLE", bal_raw["A_RECEIVABLE"]),
        line("A_CASH", bal_raw["A_CASH"]),
        line(CURRENT_ASSETS, current, subtotal=True),
        line(TOTAL_ASSETS, total_assets, subtotal=True),
        line("P_EQUITY", bal_raw["P_EQUITY"]),
        line("P_LONG", bal_raw["P_LONG"]),
        line("P_SHORT", bal_raw["P_SHORT"]),
        line(TOTAL_EQLIAB, total_eqliab, subtotal=True),
    ]
    income_lines = [
        line("I_REVENUE", inc_raw["I_REVENUE"]),
        line("I_COGS", inc_raw["I_COGS"]),
        line(GROSS_PROFIT, gross, subtotal=True),
        line("I_OPEX", inc_raw["I_OPEX"]),
        line(OPERATING_PROFIT, ebit, subtotal=True),
        line("I_INTEREST", inc_raw["I_INTEREST"]),
        line("I_OTHER", inc_raw["I_OTHER"]),
        line(PROFIT_BEFORE_TAX, ebt, subtotal=True),
        line("I_TAX", inc_raw["I_TAX"]),
        line(NET_PROFIT, net, subtotal=True),
    ]

    # ── Горизонтальный анализ (Δ и темп к предыдущему периоду) ────────────────
    horizontal: list[TrendLine] = []
    for src in (balance_lines, income_lines):
        for ln in src:
            delta: RatioSeries = [None]
            rate: RatioSeries = [None]
            for t in range(1, n):
                prev, cur = ln.values[t - 1], ln.values[t]
                delta.append(cur - prev)
                # Темп на отрицательной базе не интерпретируем (знак прироста двусмыслен).
                rate.append((cur - prev) / prev if prev > 0 else None)
            horizontal.append(TrendLine(code=ln.code, label=ln.label, delta=delta, rate=rate))

    # ── Вертикальный анализ (доля в базе: актив / выручка) ────────────────────
    vertical: list[ShareLine] = []
    for ln in balance_lines:
        vertical.append(ShareLine(code=ln.code, label=ln.label,
                                  share=[_div(ln.values[t], total_assets[t]) for t in range(n)]))
    revenue = inc_raw["I_REVENUE"]
    for ln in income_lines:
        vertical.append(ShareLine(code=ln.code, label=ln.label,
                                  share=[_div(ln.values[t], revenue[t]) for t in range(n)]))

    # ── Коэффициенты ──────────────────────────────────────────────────────────
    # Приведение к году: квартальный поток ×4, месячный ×12 (сопоставимость периодов).
    spans = [_PERIOD.get(p.kind, _DEFAULT_PERIOD) for p in model.periods]
    days = [d for d, _ in spans]
    yr = [f for _, f in spans]

    liquidity: dict[str, RatioSeries] = {}
    activity: dict[str, RatioSeries] = {}
    gearing: dict[str, RatioSeries] = {}
    profitability: dict[str, RatioSeries] = {}

    def put(group: dict[str, RatioSeries], name: str, values: RatioSeries) -> None:
        group[name] = values

    short = bal_raw["P_SHORT"]
    debt = _add(bal_raw["P_LONG"], bal_raw["P_SHORT"])
    equity = bal_raw["P_EQUITY"]
    quick = _add(bal_raw["A_RECEIVABLE"], bal_raw["A_CASH"])

    put(liquidity, "Коэффициент текущей ликвидности",
        [_div(current[t], short[t]) for t in range(n)])
    put(liquidity, "Коэффициент срочной ликвидности",
        [_div(quick[t], short[t]) for t in range(n)])
    put(liquidity, "Коэффициент абсолютной ликвидности",
        [_div(bal_raw["A_CASH"][t], short[t]) for t in range(n)])
    put(liquidity, "Чистый оборотный капитал",
        [current[t] - short[t] for t in range(n)])

    put(gearing, "Коэффициент автономии", [_div(equity[t], total_assets[t]) for t in range(n)])
    put(gearing, "Суммарные обязательства к активам",
        [_div(debt[t], total_assets[t]) for t in range(n)])
    put(gearing, "Суммарные обязательства к собств. капиталу",
        [_div(debt[t], equity[t]) for t in range(n)])
    put(gearing, "Коэффициент покрытия процентов",
        [_div(ebit[t], inc_raw["I_INTEREST"][t]) for t in range(n)])

    put(activity, "Оборачиваемость активов",
        [_div(revenue[t] * yr[t], total_assets[t]) for t in range(n)])
    put(activity, "Период оборачиваемости запасов, дн.",
        [_div(bal_raw["A_INVENTORY"][t] * days[t], inc_raw["I_COGS"][t]) for t in range(n)])
    put(activity, "Период оборачиваемости дебиторки, дн.",
        [_div(bal_raw["A_RECEIVABLE"][t] * days[t], revenue[t]) for t in range(n)])

    put(profitability, "Рентабельность валовой прибыли",
        [_div(gross[t], revenue[t]) for t in range(n)])
    put(profitability, "Рентабельность операционной прибыли",
        [_div(ebit[t], revenue[t]) for t in range(n)])
    put(profitability, "Рентабельность чистой прибыли",
        [_div(net[t], revenue[t]) for t in range(n)])
    put(profitability, "Рентабельность активов (ROA)",
        [_div(net[t] * yr[t], total_assets[t]) for t in range(n)])
    put(profitability, "Рентабельность собств. капитала (ROE)",
        [_div(net[t] * yr[t], equity[t]) for t in range(n)])

    gap = model.balance_gap()
    warnings: list[str] = []
    if any(g != 0 for g in gap):
        warnings.append("Баланс не сходится: актив ≠ пассив в одном или нескольких периодах — "
                        "показатели считаются по введённым данным как есть.")

    result = AuditResult(
        n=n,
        periods=[p.label or f"Период {i + 1}" for i, p in enumerate(model.periods)],
        balance=balance_lines,
        income=income_lines,
        horizontal=horizontal,
        vertical=vertical,
        ratios={
            "liquidity": liquidity,
            "activity": activity,
            "gearing": gearing,
            "profitability": profitability,
        },
        balance_gap=gap,
        balanced=all(g == 0 for g in gap),
        warnings=warnings,
    )

    # ── Диагностика (фаза D): скоринги банкротства + нормативы + «светофор» ───
    # Свои нормативы субъекта (v2) имеют приоритет над универсальными.
    overrides = build_overrides(model.thresholds, warnings)
    result.diagnostics = compute_diagnostics(
        result,
        {
            "assets": total_assets,
            "working_capital": [current[t] - short[t] for t in range(n)],
            "retained": model.balance_row("M_RETAINED"),
            "equity": equity,
            "liabilities": debt,
            "market_cap": model.balance_row("M_MARKET_CAP"),
            "ebit_annual": [ebit[t] * yr[t] for t in range(n)],
            "revenue_annual": [revenue[t] * yr[t] for t in range(n)],
        },
        has_retained=model.has_balance_row("M_RETAINED"),
        has_market_cap=model.has_balance_row("M_MARKET_CAP"),
        overrides=overrides,
    )

    # ── Пользовательские методики (фаза G): формулы над аналитической формой ──
    result.user_metrics = _user_metrics(model, balance_lines + income_lines, n)
    return result


def _user_metrics(model: AuditSubjectModel, lines: list[AuditLine],
                  n: int) -> list[UserMetricResult]:
    """Вычислить пользовательские показатели; ошибка формулы не роняет анализ."""
    if not model.user_metrics:
        return []
    # Окружение — коды строк аналитической формы + число периодов N.
    env: dict[str, list[Decimal] | Decimal] = {ln.code: ln.values for ln in lines}
    env["M_RETAINED"] = model.balance_row("M_RETAINED")
    env["M_MARKET_CAP"] = model.balance_row("M_MARKET_CAP")
    env["N"] = Decimal(n)

    out: list[UserMetricResult] = []
    for metric in model.user_metrics:
        try:
            value = evaluate(metric.formula, env, n)
            out.append(UserMetricResult(name=metric.name, values=as_series(value, n)))
        except FormulaError as exc:
            out.append(UserMetricResult(name=metric.name, values=[ZERO] * n, error=str(exc)))
    return out
