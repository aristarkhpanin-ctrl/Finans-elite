"""Структуры отчётов и их сборка из «листовых» строк по формулам спецификации.

Итоговые (subtotal) строки вычисляются строго по формулам CALC-ENGINE-SPEC.md §12–§15,
поэтому остаются корректными по мере наполнения листовых строк в следующих фазах.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..series import add, sub, zeros
from . import lines as L


class Statement:
    """Отчёт: упорядоченный набор строк (код → помесячный ряд) с метками."""

    def __init__(self, catalog: list[tuple[str, str]], n: int):
        self.n = n
        self.labels: dict[str, str] = {code: label for code, label in catalog}
        self.order: list[str] = [code for code, _ in catalog]
        self.lines: dict[str, list[Decimal]] = {code: zeros(n) for code, _ in catalog}

    def __getitem__(self, code: str) -> list[Decimal]:
        return self.lines[code]

    def __setitem__(self, code: str, series: list[Decimal]) -> None:
        if code not in self.lines:
            raise KeyError(f"Неизвестная строка отчёта: {code}")
        if len(series) != self.n:
            raise ValueError(f"Длина ряда {len(series)} != {self.n} для {code}")
        self.lines[code] = series

    def set(self, code: str, series: list[Decimal]) -> None:
        self[code] = series


#: Налоговый год — календарный (ст. 285 НК РФ), 12 месяцев с 1 января. Граница года и
#: квартала одна на перенос убытков и на периоды уплаты (``engine.taxes``), чтобы «год» в
#: модели значил одно и то же.
TAX_YEAR_MONTHS = 12


def tax_year_offset(start: date) -> int:
    """Сколько месяцев календарного года прошло к старту проекта (0 — старт в январе).

    Одна дверь для всего, что зависит от границы налогового года или квартала: базы и
    переноса убытков (:func:`profit_tax`) и графика уплаты профильных и настраиваемых налогов
    (``engine.taxes._payment_schedule``). До 0.9.46 год считался от старта проекта, и при
    старте не в январе налоговый период модели расходился с календарным: убыток декабря
    гасил прибыль января как «свой», а квартальный налог платился в месяцы, которые ни
    одним кварталом не кончаются.
    """
    return start.month - 1


@dataclass(frozen=True)
class ProfitTax:
    """Налоговый блок ОПУ по месяцам — **приросты** годовых нарастающих величин.

    ``carried`` (`I22`) — зачтённый убыток прошлых лет, ``taxable`` (`I26`) —
    налогооблагаемая прибыль после переноса и льготы, ``tax`` (`I27`) — начисленный
    налог. Сумма месяцев года — годовая величина; внутри года прирост бывает
    отрицательным: убыток после прибыли того же года уменьшает уже начисленный налог.
    """

    carried: list[Decimal]
    taxable: list[Decimal]
    tax: list[Decimal]


def profit_tax(bases: list[Decimal], *, limit: Decimal, year_offset: int,
               benefit_share: Decimal = Decimal(0),
               rate: Decimal = Decimal(0)) -> ProfitTax:
    """Налог на прибыль по базе до переноса ``bases`` (`I23 + I25`) — SPEC §11.

    База считается **нарастающим итогом календарного года** (ст. 274, 286 НК РФ) и в
    январе начинается заново (``year_offset`` — :func:`tax_year_offset`; обязателен, как
    и доля). Убыток месяца внутри года просто уменьшает нарастающую базу: убыток,
    пришедший после обложенной прибыли, уменьшает и начисленный налог — до 0.9.47 база
    была помесячной, и такой убыток налога не уменьшал. Непокрытый убыток года в декабре
    уходит в пул **прошлых** лет; он гасит положительную нарастающую базу следующих лет не
    больше чем на долю ``limit`` (п. 2.1 ст. 283 — ограничение действует на базу отчётного
    периода, то есть нарастающую), остаток переносится бессрочно (п. 2 ст. 283). Льгота —
    доля ``benefit_share`` базы после переноса; налог — ставка от остатка.

    Месячные строки — разности нарастающих величин: так делает и бухгалтер, у которого
    отчётный период — месяц.
    """
    n = len(bases)
    carried, taxable, tax = zeros(n), zeros(n), zeros(n)
    pool = Decimal(0)                       # непокрытые убытки прошлых лет (≥ 0)
    cum = cum_carried = cum_taxable = Decimal(0)
    for t, base in enumerate(bases):
        if (t + year_offset) % TAX_YEAR_MONTHS == 0:
            # Январь: год закрыт. Зачтённое уходит из пула, непокрытый убыток года — в пул.
            pool = pool - cum_carried + max(Decimal(0), -cum)
            cum = cum_carried = cum_taxable = Decimal(0)
        cum += base
        positive = max(Decimal(0), cum)
        cap = positive if limit >= 1 else positive * limit
        now_carried = min(pool, cap)
        now_taxable = positive - now_carried
        now_taxable -= benefit_share * now_taxable          # льгота
        carried[t] = now_carried - cum_carried
        taxable[t] = now_taxable - cum_taxable
        tax[t] = taxable[t] * rate
        cum_carried, cum_taxable = now_carried, now_taxable
    return ProfitTax(carried=carried, taxable=taxable, tax=tax)


def carry_losses(bases: list[Decimal], limit: Decimal, *, year_offset: int) -> list[Decimal]:
    """Перенос убытков прошлых лет (`I22`) — та же операция, что в :func:`profit_tax`.

    Её зовёт карта методики, чтобы пересчитать перенос при другой доле: второй копии
    правила там нет.
    """
    return profit_tax(bases, limit=limit, year_offset=year_offset).carried


def build_income(leaves: dict[str, list[Decimal]], n: int, profit_tax_rate: Decimal,
                 benefit_share: Decimal = Decimal(0), *, loss_limit: Decimal,
                 year_offset: int) -> Statement:
    """Собрать ОПУ (I1–I28). ``leaves`` содержит листовые строки; итоги вычисляются здесь.

    Налоговый блок (SPEC §11, §22.7) — :func:`profit_tax`: база нарастающим итогом
    календарного года, перенос убытков прошлых лет `I22` с ограничением доли
    ``loss_limit``, льгота ``benefit_share``; месячные `I22`, `I26`, `I27` — приросты.

    ``loss_limit`` и ``year_offset`` обязательны: умолчание здесь молча выбрало бы одну из
    двух методик за того, кто забыл передать настройку.
    """
    s = Statement(L.INCOME_LINES, n)
    for code, series in leaves.items():
        s[code] = series

    s["I4"] = sub(sub(s["I1"], s["I2"]), s["I3"])                 # I1 − I2 − I3
    s["I7"] = add(s["I5"], s["I6"])                               # I5 + I6
    s["I8"] = sub(s["I4"], s["I7"])                               # I4 − I7
    s["I16"] = add(s["I10"], s["I11"], s["I12"], s["I13"], s["I14"], s["I15"])
    s["I19"] = add(s["I17"], s["I18"])                           # I17 + I18
    # I23 = I8 − I9 − I16 − I19 + I20 − I21
    s["I23"] = add(sub(sub(sub(s["I8"], s["I9"]), s["I16"]), s["I19"]), sub(s["I20"], s["I21"]))

    # --- Налоговый блок: нарастающим итогом года (перенос I22, льгота, налог I27) ---
    # База до переноса = I23 + I25 (I24 — невычитаемые, в базу не входят, см. §22.1).
    block = profit_tax(add(s["I23"], s["I25"]), limit=loss_limit, year_offset=year_offset,
                       benefit_share=benefit_share, rate=profit_tax_rate)
    s["I22"] = block.carried
    s["I26"] = block.taxable
    s["I27"] = block.tax
    # I28 = I23 + I25 − I24 − I27  (издержки за счёт прибыли уменьшают чистую прибыль).
    s["I28"] = sub(sub(add(s["I23"], s["I25"]), s["I24"]), s["I27"])
    return s


def build_cashflow(leaves: dict[str, list[Decimal]], n: int) -> Statement:
    """Собрать Кэш-фло (C1–C29) с сальдо нарастающим итогом."""
    s = Statement(L.CASHFLOW_LINES, n)
    for code, series in leaves.items():
        s[code] = series

    s["C4"] = add(s["C2"], s["C3"])                              # прямые: C2 + C3
    s["C7"] = add(s["C5"], s["C6"])                              # постоянные: C5 + C6
    # C13 = C1 − C4 − C7 − C8 + C9 + C10 − C11 − C12
    s["C13"] = sub(
        add(sub(sub(sub(s["C1"], s["C4"]), s["C7"]), s["C8"]), s["C9"], s["C10"]),
        add(s["C11"], s["C12"]),
    )
    # C20 = C16 − C14 − C15 − C17 + C18 + C19
    s["C20"] = add(sub(sub(sub(s["C16"], s["C14"]), s["C15"]), s["C17"]), s["C18"], s["C19"])
    # C27 = C21 + C22 − C23 − C24 − C25 − C26
    s["C27"] = sub(add(s["C21"], s["C22"]), add(s["C23"], s["C24"], s["C25"], s["C26"]))

    # C28 = сальдо предыдущего периода (опорное значение для t=0 кладёт движок в leaves["C28"][0]);
    # C29 = C13 + C20 + C27 + C28 — рекуррентно.
    c28 = list(s["C28"])
    c29 = zeros(n)
    opening = c28[0] if n > 0 else Decimal(0)
    prev_close = opening
    for t in range(n):
        c28[t] = prev_close
        close = s["C13"][t] + s["C20"][t] + s["C27"][t] + c28[t]
        c29[t] = close
        prev_close = close
    s["C28"] = c28
    s["C29"] = c29
    return s


def build_profit_use(net_profit: list[Decimal], dividends: list[Decimal],
                     reserves: list[Decimal], opening_retained: Decimal, n: int) -> Statement:
    """Собрать отчёт об использовании прибыли (P1–P7) нарастающим итогом."""
    s = Statement(L.PROFIT_USE_LINES, n)
    s["P1"] = list(net_profit)
    s["P5"] = list(dividends)            # дивиденды по обыкновенным акциям (v0)
    s["P6"] = list(reserves)

    p2 = zeros(n)
    p3 = zeros(n)
    p7 = zeros(n)
    prev_retained = opening_retained
    for t in range(n):
        p2[t] = prev_retained
        p3[t] = s["P1"][t] + p2[t]
        p7[t] = p3[t] - s["P4"][t] - s["P5"][t] - s["P6"][t]
        prev_retained = p7[t]
    s["P2"] = p2
    s["P3"] = p3
    s["P7"] = p7
    return s


def build_balance(leaves: dict[str, list[Decimal]], n: int) -> Statement:
    """Собрать Баланс (B1–B34) с итоговыми строками по формулам спецификации."""
    s = Statement(L.BALANCE_LINES, n)
    for code, series in leaves.items():
        s[code] = series

    # B8 = B1..B7
    s["B8"] = add(s["B1"], s["B2"], s["B3"], s["B4"], s["B5"], s["B6"], s["B7"])
    # B11 = B12+B13+B14+B15+B16  (= B9 − B10)
    s["B11"] = add(s["B12"], s["B13"], s["B14"], s["B15"], s["B16"])
    # B20 = B8 + B11 + B17 + B18 + B19
    s["B20"] = add(s["B8"], s["B11"], s["B17"], s["B18"], s["B19"])
    # B25 = B21 + B22 + B23 + B24
    s["B25"] = add(s["B21"], s["B22"], s["B23"], s["B24"])
    # B33 = B27..B32
    s["B33"] = add(s["B27"], s["B28"], s["B29"], s["B30"], s["B31"], s["B32"])
    # B34 = B25 + B26 + B33
    s["B34"] = add(s["B25"], s["B26"], s["B33"])
    return s


def opening_balance(cash, fixed_assets_net, debt, paid_in_capital,
                    retained_earnings, foreign_monetary_base=Decimal(0),
                    receivables=Decimal(0), payables=Decimal(0),
                    raw_materials=Decimal(0), finished_goods=Decimal(0),
                    short_term_debt=Decimal(0), preferred_capital=Decimal(0),
                    reserves=Decimal(0), additional_capital=Decimal(0),
                    prepaid_expenses=Decimal(0), advances_received=Decimal(0),
                    ) -> dict[str, Decimal]:
    """Балансовые величины на начало проекта (t = −1) из стартового баланса.

    Нужны для «средних за период» в коэффициентах (SPEC §18): среднее за период t = 0
    берётся как (начало + конец)/2, где «начало» — этот стартовый баланс. Субтоталы
    (B8, B11, B20, B33…) вычисляются теми же формулами, что и обычный баланс.
    ``foreign_monetary_base`` — опорная валютная позиция в основной валюте (→ B6).
    """
    leaves = {
        "B1": [cash],
        "B2": [receivables],
        "B3": [raw_materials],
        "B5": [finished_goods],
        "B6": [foreign_monetary_base],
        "B7": [prepaid_expenses],
        "B14": [fixed_assets_net],   # остаточная стоимость ОС (v0 → оборудование)
        "B22": [short_term_debt],
        "B23": [payables],
        "B24": [advances_received],
        "B26": [debt],
        "B27": [paid_in_capital],
        "B28": [preferred_capital],
        "B30": [reserves],
        "B31": [additional_capital],
        "B32": [retained_earnings],
    }
    s = build_balance(leaves, 1)
    return {code: s[code][0] for code in s.order}
