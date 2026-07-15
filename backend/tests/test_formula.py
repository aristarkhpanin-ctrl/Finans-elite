"""Язык формул F0 (docs/FORMULA-TABLES-DECOMPOSITION.md): парсер, вычислитель, функции.

Числа выверены вручную; проверяются приоритеты, broadcast, ошибки и лимиты (DoS).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from calc_core.formula import FormulaError, evaluate, parse

D = Decimal


def _env(n=4):
    return {
        "I1": [D(100), D(200), D(300), D(400)][:n],
        "C13": [D(-50), D(10), D(20), D(30)][:n],
        "N": D(n),
    }


def ev(expr, n=4):
    return evaluate(expr, _env(n), n)


# --- Арифметика, приоритеты, broadcast ---

def test_arithmetic_precedence():
    assert ev("2 + 2 * 2") == D(6)
    assert ev("(2 + 2) * 2") == D(8)
    assert ev("2 ^ 3 ^ 2") == D(512)          # правоассоциативность: 2^(3^2)
    assert ev("-3 ^ 2") == D(-9)              # математическая конвенция: −(3^2)
    assert ev("(-3) ^ 2") == D(9)


def test_series_broadcast_and_scalar_ops():
    assert ev("I1 * 2") == [D(200), D(400), D(600), D(800)]
    assert ev("I1 + C13") == [D(50), D(210), D(320), D(430)]
    assert ev("I1 / N") == [D(25), D(50), D(75), D(100)]


def test_division_by_zero_is_zero():
    assert ev("1 / 0") == D(0)
    assert ev("I1 / (I1 - I1)") == [D(0)] * 4   # поэлементно


def test_comparisons_give_01():
    assert ev("I1 > 150") == [D(0), D(1), D(1), D(1)]
    assert ev("2 == 2") == D(1)


# --- Функции ---

def test_shift_cum_diff():
    assert ev("СДВИГ(I1, 1)") == [D(0), D(100), D(200), D(300)]
    assert ev("SHIFT(I1, -1)") == [D(200), D(300), D(400), D(0)]
    assert ev("АККУМ(I1)") == [D(100), D(300), D(600), D(1000)]
    assert ev("DIFF(I1)") == [D(100), D(100), D(100), D(100)]


def test_aggregates():
    assert ev("СУММ(I1)") == D(1000)
    assert ev("AVG(I1)") == D(250)
    assert ev("МИН(I1)") == D(100)
    assert ev("MAX(I1)") == D(400)
    assert ev("MIN(I1, 250)") == [D(100), D(200), D(250), D(250)]  # поэлементно при 2 аргументах


def test_if_abs_round():
    assert ev("ЕСЛИ(C13 < 0, 0, C13)") == [D(0), D(10), D(20), D(30)]
    assert ev("МОДУЛЬ(C13)") == [D(50), D(10), D(20), D(30)]
    assert ev("ОКРУГЛ(I1 / 3, 2)")[0] == D("33.33")


def test_elem_part_pow():
    assert ev("ЭЛЕМЕНТ(I1, 2)") == D(300)
    assert ev("ELEM(I1, 99)") == D(0)                       # вне диапазона → 0
    assert ev("ЧАСТЬ(I1, 1, 3)") == [D(0), D(200), D(300), D(0)]
    assert ev("POW(I1, 2)")[1] == D(40000)


def test_npv_irr_discount():
    # NPV при нулевой ставке = сумме потока.
    assert ev("ЧПС(C13, 0)") == D(10)
    # DISCOUNT при нулевой ставке — тождество.
    assert ev("ДИСК(I1, 0)") == [D(100), D(200), D(300), D(400)]
    # IRR потока (-100, 110): 10% в месяц → годовая (1.1^12 − 1); проверяем месячную базу.
    env = {"X": [D(-100), D(110)]}
    irr = evaluate("ВНД(X)", env, 2)
    assert abs((D(1) + irr) ** (D(1) / D(12)) - D("1.10")) < D("0.0001")
    # IRR не определена → 0 (прощающая семантика).
    assert evaluate("IRR(X)", {"X": [D(10), D(10)]}, 2) == D(0)


# --- Ошибки и лимиты ---

def test_unknown_identifier_and_function():
    with pytest.raises(FormulaError, match="идентификатор"):
        ev("Z99")
    with pytest.raises(FormulaError, match="функция"):
        ev("NOSUCH(I1)")


def test_syntax_errors():
    for bad in ("1 +", "(1 + 2", "SUM(I1", "1 2", "@", ""):
        with pytest.raises(FormulaError):
            ev(bad)


def test_wrong_arity():
    with pytest.raises(FormulaError, match="аргumentов|аргументов"):
        ev("SUM(I1, I1)")


def test_limits_guard_against_dos():
    with pytest.raises(FormulaError, match="длиннее"):
        parse("1+" * 300 + "1")
    with pytest.raises(FormulaError, match="узлов|Вложенность"):
        parse("+".join(["1"] * 150))          # 149 сложений → >200 узлов? — или глубина
    with pytest.raises(FormulaError, match="Вложенность"):
        parse("(" * 40 + "1" + ")" * 40)


def test_case_insensitive_idents_and_functions():
    assert ev("sum(i1)") == D(1000)
