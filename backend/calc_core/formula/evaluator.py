"""Вычислитель AST языка формул над окружением рядов (решения Q1–Q3 декомпозиции).

Окружение — словарь «идентификатор → ряд/скаляр» (коды строк отчётов + `N`). Бинарные
операции поэлементны со broadcast скаляров; сравнения дают 0/1; деление на 0 → 0.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, Overflow

from ..money import ZERO
from .functions import Value, as_series, resolve_function
from .parser import FormulaError, parse

Env = dict[str, Value]


def _binary(op: str, left: Value, right: Value, n: int) -> Value:
    # Скаляр ∘ скаляр — без расширения до ряда.
    if not isinstance(left, list) and not isinstance(right, list):
        return _apply(op, left, right)
    a, b = as_series(left, n), as_series(right, n)
    return [_apply(op, a[t], b[t]) for t in range(n)]


def _apply(op: str, x: Decimal, y: Decimal) -> Decimal:
    if op == "+":
        return x + y
    if op == "-":
        return x - y
    if op == "*":
        return x * y
    if op == "/":
        return x / y if y != 0 else ZERO          # деление на 0 → 0 (Q2)
    if op == "^":
        if x == 0 and y < 0:
            return ZERO
        if x < 0 and y != y.to_integral_value():
            return ZERO                            # дробная степень отрицательного → 0
        return x ** y
    if op == "<":
        return Decimal(1) if x < y else ZERO
    if op == ">":
        return Decimal(1) if x > y else ZERO
    if op == "<=":
        return Decimal(1) if x <= y else ZERO
    if op == ">=":
        return Decimal(1) if x >= y else ZERO
    if op == "==":
        return Decimal(1) if x == y else ZERO
    if op == "!=":
        return Decimal(1) if x != y else ZERO
    raise FormulaError(f"Неизвестная операция «{op}»")


def _eval(node, env: Env, n: int) -> Value:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "ident":
        name = node[1]
        if name not in env:
            raise FormulaError(f"Неизвестный идентификатор «{name}» (коды строк: I1…, C1…, B1…, P1…)")
        return env[name]
    if kind == "neg":
        v = _eval(node[1], env, n)
        return -v if not isinstance(v, list) else [-x for x in v]
    if kind == "bin":
        return _binary(node[1], _eval(node[2], env, n), _eval(node[3], env, n), n)
    if kind == "call":
        name, args = node[1], node[2]
        fn = resolve_function(name)
        if fn is None:
            raise FormulaError(f"Неизвестная функция «{name}»")
        lo, hi, impl = fn
        if not lo <= len(args) <= hi:
            expected = str(lo) if lo == hi else f"{lo}–{hi}"
            raise FormulaError(f"{name}: ожидается аргументов: {expected}, получено {len(args)}")
        values = [_eval(a, env, n) for a in args]
        return impl(values, n)
    raise FormulaError("Некорректное выражение")


def evaluate(expr: str, env: Env, n: int) -> Value:
    """Разобрать и вычислить формулу над окружением; ошибки — ``FormulaError``."""
    tree = parse(expr)
    try:
        return _eval(tree, env, n)
    except (InvalidOperation, Overflow) as exc:
        raise FormulaError("Числовая ошибка вычисления (переполнение или недопустимая операция)") from exc
