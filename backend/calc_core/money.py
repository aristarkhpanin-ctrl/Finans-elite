"""Денежная арифметика расчётного ядра.

Все денежные суммы — :class:`decimal.Decimal` в едином контексте. Никакого ``float``
в финансовых величинах (см. CALC-ENGINE-SPEC.md §3). ``float`` допускается только в
стохастическом анализе (Монте-Карло), который сюда не входит.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal, getcontext
from typing import Union

#: Единый контекст вычислений ядра. Точность с запасом (округление результата — только
#: на границе отображения через :func:`quantize`), округление зафиксировано явно. Контекст
#: применяется вокруг ``run()`` через ``localcontext`` — результат не зависит ни от потока
#: (``getcontext()`` thread-local: воркеры FastAPI иначе считали бы с дефолтным prec=28),
#: ни от хоста. Менять prec/rounding — только через golden-master.
CALC_CONTEXT = Context(prec=34, rounding=ROUND_HALF_EVEN)

# Дефолт текущего потока — тот же контекст (для Decimal-операций вне run()).
getcontext().prec = CALC_CONTEXT.prec
getcontext().rounding = CALC_CONTEXT.rounding

Number = Union[Decimal, int, str]

#: Допуск для проверки балансовых тождеств (см. SPEC §16).
EPSILON = Decimal("0.01")

# Часто используемые константы.
ZERO = Decimal(0)
ONE = Decimal(1)


def D(value: Number) -> Decimal:
    """Привести значение к :class:`Decimal` безопасно (через ``str`` для float-литералов)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):  # защищаемся от двоичного дрейфа float
        return Decimal(str(value))
    return Decimal(value)


def quantize(value: Decimal, places: int = 2) -> Decimal:
    """Округлить к указанному числу знаков (``ROUND_HALF_UP``) — для отображения."""
    exp = Decimal(1).scaleb(-places)  # 10**-places
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def almost_equal(a: Decimal, b: Decimal, eps: Decimal = EPSILON) -> bool:
    """Сравнение с допуском на округление."""
    return abs(a - b) <= eps
