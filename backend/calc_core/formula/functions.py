"""Функции языка формул v1 (решение Q4 декомпозиции): латинские имена + русские алиасы.

Значение — ряд длины ``n`` (list[Decimal]) либо скаляр (Decimal). Свёртки дают скаляр,
поэлементные функции сохраняют форму. Прощающая семантика (финмодельная): деление на 0 → 0,
IRR не определена → 0, LN(x≤0) → 0, ELEM вне диапазона → 0.
"""
from __future__ import annotations

from decimal import Decimal

from ..metrics import annual_to_monthly, irr_annual, npv
from ..money import ONE, ZERO
from .parser import FormulaError

Value = Decimal | list[Decimal]


def as_series(v: Value, n: int) -> list[Decimal]:
    """Скаляр → ряд-константа; ряд — как есть."""
    if isinstance(v, list):
        return v
    return [v] * n


def _as_scalar(v: Value, what: str) -> Decimal:
    if isinstance(v, list):
        raise FormulaError(f"{what}: ожидается число, получен ряд")
    return v


def _as_int(v: Value, what: str) -> int:
    d = _as_scalar(v, what)
    if d != d.to_integral_value():
        raise FormulaError(f"{what}: ожидается целое число")
    return int(d)


def _shift(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    k = _as_int(args[1], "SHIFT")
    out = [ZERO] * n
    for t in range(n):
        s = t - k
        if 0 <= s < n:
            out[t] = x[s]
    return out


def _cum(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    out, acc = [], ZERO
    for v in x:
        acc += v
        out.append(acc)
    return out


def _diff(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    return [x[t] - (x[t - 1] if t > 0 else ZERO) for t in range(n)]


def _discount(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    m = annual_to_monthly(_as_scalar(args[1], "DISCOUNT"))
    return [x[t] / (ONE + m) ** t for t in range(n)]


def _npv(args: list[Value], n: int) -> Value:
    return npv(as_series(args[0], n), annual_to_monthly(_as_scalar(args[1], "NPV")))


def _irr(args: list[Value], n: int) -> Value:
    r = irr_annual(as_series(args[0], n))
    return r if r is not None else ZERO


def _sum(args: list[Value], n: int) -> Value:
    return sum(as_series(args[0], n), ZERO)


def _avg(args: list[Value], n: int) -> Value:
    s = as_series(args[0], n)
    return sum(s, ZERO) / Decimal(len(s)) if s else ZERO


def _minmax(pick, args: list[Value], n: int) -> Value:
    if len(args) == 1:                       # свёртка: MIN(x) → скаляр
        s = as_series(args[0], n)
        return pick(s) if s else ZERO
    a, b = as_series(args[0], n), as_series(args[1], n)   # поэлементно: MIN(x, y)
    return [pick((a[t], b[t])) for t in range(n)]


def _abs(args: list[Value], n: int) -> Value:
    return [abs(v) for v in as_series(args[0], n)]


def _round(args: list[Value], n: int) -> Value:
    places = _as_int(args[1], "ROUND") if len(args) > 1 else 0
    quantum = Decimal(1).scaleb(-places)
    return [v.quantize(quantum) for v in as_series(args[0], n)]


def _pow(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    p = _as_scalar(args[1], "POW")
    out = []
    for v in x:
        if v == 0 and p < 0:
            out.append(ZERO)
        elif v < 0 and p != p.to_integral_value():
            out.append(ZERO)     # дробная степень отрицательного — не определена → 0
        else:
            out.append(v ** p)
    return out


def _exp(args: list[Value], n: int) -> Value:
    return [v.exp() for v in as_series(args[0], n)]


def _ln(args: list[Value], n: int) -> Value:
    return [v.ln() if v > 0 else ZERO for v in as_series(args[0], n)]


def _if(args: list[Value], n: int) -> Value:
    cond, a, b = (as_series(x, n) for x in args)
    return [a[t] if cond[t] != 0 else b[t] for t in range(n)]


def _elem(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    t = _as_int(args[1], "ELEM")
    return x[t] if 0 <= t < len(x) else ZERO


def _part(args: list[Value], n: int) -> Value:
    x = as_series(args[0], n)
    lo = _as_int(args[1], "PART")
    hi = _as_int(args[2], "PART")
    return [x[t] if lo <= t < hi else ZERO for t in range(n)]


#: Реестр: имя → (мин. аргументов, макс. аргументов, реализация).
FUNCTIONS: dict[str, tuple[int, int, object]] = {
    "SHIFT": (2, 2, _shift),
    "CUM": (1, 1, _cum),
    "DIFF": (1, 1, _diff),
    "DISCOUNT": (2, 2, _discount),
    "NPV": (2, 2, _npv),
    "IRR": (1, 1, _irr),
    "SUM": (1, 1, _sum),
    "AVG": (1, 1, _avg),
    "MIN": (1, 2, lambda a, n: _minmax(min, a, n)),
    "MAX": (1, 2, lambda a, n: _minmax(max, a, n)),
    "ABS": (1, 1, _abs),
    "ROUND": (1, 2, _round),
    "POW": (2, 2, _pow),
    "EXP": (1, 1, _exp),
    "LN": (1, 1, _ln),
    "IF": (3, 3, _if),
    "ELEM": (2, 2, _elem),
    "PART": (3, 3, _part),
}

#: Русские алиасы → канонические имена.
ALIASES: dict[str, str] = {
    "СДВИГ": "SHIFT", "АККУМ": "CUM", "РАЗН": "DIFF", "ДИСК": "DISCOUNT",
    "ЧПС": "NPV", "ВНД": "IRR", "СУММ": "SUM", "СРЗНАЧ": "AVG",
    "МИН": "MIN", "МАКС": "MAX", "МОДУЛЬ": "ABS", "ОКРУГЛ": "ROUND",
    "СТЕПЕНЬ": "POW", "ЕСЛИ": "IF", "ЭЛЕМЕНТ": "ELEM", "ЧАСТЬ": "PART",
}


def resolve_function(name: str):
    """Функция по имени (или алиасу); None — не найдена."""
    canonical = ALIASES.get(name, name)
    return FUNCTIONS.get(canonical)
