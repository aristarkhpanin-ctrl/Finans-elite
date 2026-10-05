"""Форматирование чисел для текста находок (запятая-десятичная, пробел-разряды)."""
from __future__ import annotations

from decimal import Decimal


def fmt_rub(value: Decimal) -> str:
    """Целые рубли с группировкой пробелами: -152445 → «−152 445» (типографский минус)."""
    grouped = f"{value.quantize(Decimal(1)):,}".replace(",", " ")
    return grouped.replace("-", "−")


def fmt_pct(value: Decimal) -> str:
    """Доля → проценты: 0.15 → «15,0%»."""
    return f"{value * 100:.1f}%".replace(".", ",")


def fmt_num(value: Decimal, places: int = 2) -> str:
    """Число с фиксированной точностью и запятой: 0.44 → «0,44»."""
    return f"{value:.{places}f}".replace(".", ",")
