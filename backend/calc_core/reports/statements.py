"""Структуры отчётов и их сборка из «листовых» строк по формулам спецификации.

Итоговые (subtotal) строки вычисляются строго по формулам CALC-ENGINE-SPEC.md §12–§15,
поэтому остаются корректными по мере наполнения листовых строк в следующих фазах.
"""
from __future__ import annotations

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


def build_income(leaves: dict[str, list[Decimal]], n: int, profit_tax_rate: Decimal,
                 benefit_share: Decimal = Decimal(0)) -> Statement:
    """Собрать ОПУ (I1–I28). ``leaves`` содержит листовые строки; итоги вычисляются здесь.

    Налоговый блок (SPEC §11, §22.7) считается **последовательно**: убыток периода
    накапливается и уменьшает налоговую базу будущих прибыльных периодов (перенос убытков,
    `I22`); доля ``benefit_share`` налогооблагаемой прибыли освобождается от налога (льгота).
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

    # --- Налоговый блок: перенос убытков (I22) + льгота + налог (последовательно) ---
    # База до переноса = I23 + I25 (I24 — невычитаемые, в базу не входят, см. §22.1).
    i22 = zeros(n)
    i26 = zeros(n)
    i27 = zeros(n)
    loss_pool = Decimal(0)  # накопленные непокрытые убытки (хранятся как ≥0)
    for t in range(n):
        base = s["I23"][t] + s["I25"][t]
        if base < 0:
            loss_pool += -base                       # убыток периода → в пул
            taxable = base                           # I26 < 0, налога нет
        else:
            applied = min(loss_pool, base)           # покрываем прибыль накопленным убытком
            i22[t] = applied
            loss_pool -= applied
            taxable = base - applied
        exempt = benefit_share * taxable if taxable > 0 else Decimal(0)  # льгота
        i26[t] = taxable - exempt
        i27[t] = max(Decimal(0), i26[t]) * profit_tax_rate
    s["I22"] = i22
    s["I26"] = i26
    s["I27"] = i27
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
