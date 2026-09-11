"""Оценка стоимости и мост EV → цена (Финанс-Аудит, «Экран 4»; методика — SPEC, Прил. П).

Сводка (Прил. Н) отказывалась показывать дисконт к цене: выводить его было не из чего.
Этот модуль даёт недостающее — и ровно теми средствами, которыми платформа располагает.

Четыре решения задают модуль.

**Прогноз вводится.** В деле есть только прошлое; экстраполировать выручку «как росла,
так и будет» значило бы выдать регрессию за прогноз. Единственная связь с проверкой —
**база прогноза берётся нормализованной** (Прил. К), ради чего нормализация и делалась.

**Без амортизации оценка не считается.** ``FCFF = EBIT × (1 − t) + Амортизация −
Капвложения − ΔОК``; амортизация — из справочной строки, той же, без которой не
существует EBITDA. Подставить ноль значило бы занизить поток ровно на неё и выдать
заниженную стоимость за расчётную.

**Долг в мосте — из реестра обязательств** (Прил. Л): это именно процентный долг,
названный по договорам. Реестра нет — берётся агрегат ``P_LONG + P_SHORT`` **с
оговоркой**, что он включает кредиторку и завышает чистый долг. Забалансовые
обязательства из EV **не вычитаются** (Л.1): условное ещё не наступило.

**Дисконт существует только с запрошенной ценой.** Не введена — дисконта нет, а не
«ноль процентов».

Чистые функции над готовыми результатами. **В ``AuditResult`` не входят.**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .earnings import EarningsQuality
from .models import AuditSubjectModel
from .obligations import ObligationRegister
from .result import AuditResult

D = Decimal

#: Сетка чувствительности: отклонения WACC и роста в постпрогнозе от заданных.
WACC_STEPS = [D("-0.04"), D("-0.02"), D(0), D("0.02"), D("0.04")]
GROWTH_STEPS = [D("-0.02"), D("-0.01"), D(0), D("0.01"), D("0.02")]


@dataclass
class ForecastYear:
    """Год прогноза: показатель, поток и его приведённая стоимость."""

    year: int
    ebit: Decimal
    depreciation: Decimal
    capex: Decimal
    nwc_change: Decimal
    fcff: Decimal
    discount_factor: Decimal
    present_value: Decimal


@dataclass
class BridgeItem:
    """Слагаемое моста EV → цена: подпись, знак и величина."""

    label: str
    amount: Decimal
    #: add — прибавляется к EV, subtract — вычитается, total — итог.
    kind: str
    note: str = ""


@dataclass
class Valuation:
    """Оценка: дисконтированный поток, мост к цене и чувствительность.

    ``enabled=False`` либо непустой ``blockers`` — оценка **не посчитана**. Это не
    «ноль рублей»: величины, для которой не хватает входных данных, не существует.
    """

    enabled: bool = False
    #: Почему оценка не посчитана. Пусто — посчитана.
    blockers: list[str] = field(default_factory=list)
    #: Показатель, к которому считается мультипликатор (EBITDA либо EBIT — Прил. К).
    base_code: str = "EBIT"
    #: База FCFF — **всегда нормализованный EBIT**, даже когда мультипликатор к EBITDA:
    #: амортизация стоит в формуле отдельным слагаемым, и держать её ещё и в базе
    #: значило бы учесть её дважды. Поле названо показателем во избежание путаницы.
    base_ebit: Decimal = D(0)
    wacc: Decimal = D(0)
    terminal_growth: Decimal = D(0)
    years: list[ForecastYear] = field(default_factory=list)
    pv_forecast: Decimal = D(0)
    terminal_value: Optional[Decimal] = None
    pv_terminal: Optional[Decimal] = None
    enterprise_value: Optional[Decimal] = None
    #: Доля терминальной стоимости в EV — мера того, насколько оценка держится на ней.
    terminal_share: Optional[Decimal] = None
    bridge: list[BridgeItem] = field(default_factory=list)
    equity_value: Optional[Decimal] = None
    #: Подразумеваемый **нами** мультипликатор EV / показатель, не рыночный ориентир.
    implied_multiple: Optional[Decimal] = None
    asking_price: Optional[Decimal] = None
    #: 1 − цена / запрошенная. ``None`` — цена продавца не введена (Прил. П.4).
    discount: Optional[Decimal] = None
    #: Матрица цены за долю: строки — WACC, столбцы — рост в постпрогнозе.
    sensitivity: list[list[Optional[Decimal]]] = field(default_factory=list)
    sensitivity_wacc: list[Decimal] = field(default_factory=list)
    sensitivity_growth: list[Decimal] = field(default_factory=list)
    equity_min: Optional[Decimal] = None
    equity_max: Optional[Decimal] = None
    #: Оговорки: долг взят агрегатом, забалансовое не вычтено и т.п.
    warnings: list[str] = field(default_factory=list)
    #: Чего оценка не делает (Прил. П.6) — называется, а не умалчивается.
    not_computed: list[str] = field(default_factory=list)


NOT_COMPUTED = [
    "Сопоставимые сделки — базы сделок-аналогов у платформы нет; таблица «сделки-аналоги» "
    "была бы выдуманной. Мультипликатор ниже — наш собственный подразумеваемый, а не "
    "рыночный ориентир.",
    "IRR сделки — считается от предположения о выходе (срок владения и мультипликатор "
    "продажи); таких допущений в деле нет.",
]


def _line(lines, code: str) -> list[Decimal]:
    for ln in lines:
        if ln.code == code:
            return list(ln.values)
    return []


def _at(row: list[Decimal], i: int, default: Decimal = D(0)) -> Decimal:
    """Значение ряда допущений на год ``i``; за пределом — последнее заданное.

    Ряд короче горизонта — обычная ситуация: человек задал рост на три года из пяти.
    Продлить последним значением честнее, чем обнулить хвост: обнуление подставило бы
    наше допущение вместо незаполненного.
    """
    if not row:
        return default
    return row[i] if i < len(row) else row[-1]


def _terminal(fcff: Decimal, wacc: Decimal, growth: Decimal) -> Optional[Decimal]:
    """Терминальная стоимость по Гордону. ``None`` при ``g ≥ WACC`` (Прил. П.2).

    При равенстве формула делит на ноль, при превышении даёт отрицательную величину,
    которая читается как «бизнес стоит меньше нуля» — оба ответа бессмысленны.
    """
    if growth >= wacc:
        return None
    return fcff * (D(1) + growth) / (wacc - growth)


def _enterprise_value(base: Decimal, horizon: int, wacc: Decimal,
                      growth_row: list[Decimal], capex_row: list[Decimal],
                      nwc_row: list[Decimal], depreciation: Decimal, tax: Decimal,
                      terminal_growth: Decimal) -> tuple[Optional[Decimal],
                                                         list[ForecastYear],
                                                         Decimal, Optional[Decimal]]:
    """EV, годы прогноза, PV прогноза и PV терминальной стоимости."""
    years: list[ForecastYear] = []
    ebit, dep = base, depreciation
    pv_total = D(0)
    for i in range(horizon):
        g = _at(growth_row, i)
        ebit = ebit * (D(1) + g)
        # Амортизация растёт вместе с показателем: отдельного прогноза для неё нет,
        # а держать её постоянной при растущем EBIT — тоже допущение, только скрытое.
        dep = dep * (D(1) + g)
        capex, nwc = _at(capex_row, i), _at(nwc_row, i)
        fcff = ebit * (D(1) - tax) + dep - capex - nwc
        factor = D(1) / (D(1) + wacc) ** (i + 1)
        pv = fcff * factor
        pv_total += pv
        years.append(ForecastYear(year=i + 1, ebit=ebit, depreciation=dep, capex=capex,
                                  nwc_change=nwc, fcff=fcff, discount_factor=factor,
                                  present_value=pv))

    terminal = _terminal(years[-1].fcff, wacc, terminal_growth) if years else None
    pv_terminal = (terminal / (D(1) + wacc) ** horizon) if terminal is not None else None
    ev = pv_total + pv_terminal if pv_terminal is not None else None
    return ev, years, pv_total, pv_terminal


def build_valuation(model: AuditSubjectModel, result: AuditResult,
                    earnings: Optional[EarningsQuality] = None,
                    obligations: Optional[ObligationRegister] = None) -> Valuation:
    """Оценка стоимости по введённым допущениям и нормализованному показателю.

    Оценка выключена или входных данных не хватает → ``blockers`` называет причину.
    Молчаливый ноль здесь недопустим: покупатель увидел бы «бизнес стоит 0» вместо
    «оценка не посчитана».
    """
    earnings = earnings if earnings is not None else EarningsQuality()
    obligations = obligations if obligations is not None else ObligationRegister()
    a = model.valuation
    val = Valuation(enabled=a.enabled, wacc=a.wacc, terminal_growth=a.terminal_growth,
                    base_code=earnings.base_code, not_computed=list(NOT_COMPUTED),
                    asking_price=a.asking_price)

    if not a.enabled:
        val.blockers.append("Оценка выключена: включите её и задайте допущения прогноза.")
        return val

    n = result.n
    if n == 0 or not earnings.normalized:
        val.blockers.append("Отчётность не введена — базы прогноза не существует.")
        return val
    if not model.has_income_row("M_DEPRECIATION"):
        # Ноль вместо амортизации занизил бы поток ровно на неё (Прил. П.2).
        val.blockers.append(
            "Не введена справочная строка «в т.ч. амортизация»: без неё свободный "
            "поток теряет слагаемое, а подставить ноль значило бы занизить стоимость "
            "ровно на амортизацию. Это та же строка, без которой не считается EBITDA.")
    if a.wacc <= 0:
        val.blockers.append("Ставка дисконтирования (WACC) не задана.")

    # База берётся нормализованной: отчётный показатель для оценки не годится (П.1).
    # Нормализован EBITDA — вычитаем амортизацию: в формуле FCFF она стоит отдельным
    # слагаемым, и оставить её внутри базы значило бы учесть её дважды.
    depreciation = model.income_row("M_DEPRECIATION")
    base = (earnings.normalized[n - 1] - depreciation[n - 1]
            if earnings.base_code == "EBITDA" else earnings.normalized[n - 1])
    if base <= 0:
        val.blockers.append(
            "Нормализованный показатель прибыли не положителен — дисконтировать поток "
            "от убытка бессмысленно: любая положительная стоимость была бы выдумкой.")
    val.base_ebit = base
    if val.blockers:
        return val

    ev, years, pv_forecast, pv_terminal = _enterprise_value(
        base, a.horizon_years, a.wacc, list(a.growth), list(a.capex),
        list(a.nwc_change), depreciation[n - 1], a.tax_rate, a.terminal_growth)
    val.years, val.pv_forecast, val.pv_terminal = years, pv_forecast, pv_terminal
    val.terminal_value = _terminal(years[-1].fcff, a.wacc, a.terminal_growth)
    if ev is None:
        val.blockers.append(
            f"Рост в постпрогнозе ({a.terminal_growth * 100:.1f}%) не меньше ставки "
            f"дисконтирования ({a.wacc * 100:.1f}%): терминальная стоимость по Гордону "
            "не существует — формула даёт бесконечность или отрицательную величину.")
        return val

    val.enterprise_value = ev
    val.terminal_share = pv_terminal / ev if ev and pv_terminal is not None else None
    last_measure = earnings.normalized[n - 1]
    val.implied_multiple = ev / last_measure if last_measure else None

    # ── Мост EV → цена (Прил. П.3) ───────────────────────────────────────────
    if obligations.has_rows:
        debt, debt_note = obligations.balance_debt, "из реестра обязательств"
    else:
        long_, short = _line(result.balance, "P_LONG"), _line(result.balance, "P_SHORT")
        debt = (long_[n - 1] + short[n - 1]) if long_ and short else D(0)
        debt_note = "агрегат P_LONG + P_SHORT (включает кредиторку)"
        val.warnings.append(
            "Реестр обязательств не заполнен: долг взят агрегатом баланса, а он включает "
            "кредиторскую задолженность и завышает чистый долг — цена за долю получается "
            "заниженной. Заполните реестр («Обязательства и залоги»), чтобы в мост попал "
            "именно процентный долг.")

    cash_line = _line(result.balance, "A_CASH")
    cash = cash_line[n - 1] if cash_line else D(0)
    equity = ev - debt + cash - a.minority_interest
    val.equity_value = equity
    val.bridge = [
        BridgeItem("Enterprise Value", ev, "add"),
        BridgeItem("Долг и займы", debt, "subtract", debt_note),
        BridgeItem("Денежные средства", cash, "add"),
        BridgeItem("Доля миноритариев", a.minority_interest, "subtract",
                   "вводится: в аналитической форме её нет"),
        BridgeItem("Цена за 100% доли", equity, "total"),
    ]
    if obligations.off_balance > 0:
        # Условное обязательство ещё не наступило — вычитать его из цены нельзя (Л.1),
        # но и промолчать о нём нельзя: покупатель обязан учесть его сам.
        val.warnings.append(
            f"Забалансовые обязательства ({obligations.off_balance}) в мост не входят: "
            "условное обязательство ещё не наступило, и уменьшать на него цену значило бы "
            "утверждать обратное. Учтите его при торге отдельно.")

    if a.asking_price is not None and a.asking_price > 0:
        # Оценка выше запрошенной даёт отрицательный дисконт — премию. Она показывается
        # знаком, а не обнуляется: «дисконта нет» и «продавец просит меньше» — разное.
        val.discount = D(1) - equity / a.asking_price

    # ── Чувствительность (Прил. П.5) ─────────────────────────────────────────
    val.sensitivity_wacc = [a.wacc + s for s in WACC_STEPS]
    val.sensitivity_growth = [a.terminal_growth + s for s in GROWTH_STEPS]
    equities: list[Decimal] = []
    for w in val.sensitivity_wacc:
        row: list[Optional[Decimal]] = []
        for g in val.sensitivity_growth:
            cell_ev = None if w <= 0 else _enterprise_value(
                base, a.horizon_years, w, list(a.growth), list(a.capex),
                list(a.nwc_change), depreciation[n - 1], a.tax_rate, g)[0]
            if cell_ev is None:
                row.append(None)              # рост ≥ ставки: клетки не существует
                continue
            cell_equity = cell_ev - debt + cash - a.minority_interest
            row.append(cell_equity)
            equities.append(cell_equity)
        val.sensitivity.append(row)
    if equities:
        val.equity_min, val.equity_max = min(equities), max(equities)

    return val
