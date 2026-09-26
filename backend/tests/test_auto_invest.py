"""Тесты автоподбора инвестиций: размещение излишков кассы в депозит (SPEC §19, gap §6).

Единый решатель solve_cash_management: кредит покрывает дефицит, депозит копит излишки;
при invest_on=False совпадает с solve_credit_line (equivalence). Инъекция инертна по
умолчанию (invest_surplus=False) → golden без дрейфа чисел.
"""
from decimal import Decimal

from calc_core import run
from calc_core.engine.financing_auto import solve_cash_management, solve_credit_line
from calc_core.models import (
    AutoFinancing,
    Financing,
    OperatingPlan,
    Product,
    ProjectModel,
    SalesLine,
)
from calc_core.money import almost_equal

EPS = Decimal("0.01")


def test_equivalence_with_credit_line_when_invest_off():
    """invest_on=False, credit_on=True → графики совпадают с solve_credit_line байт-в-байт."""
    flows = [Decimal(-100), Decimal(60), Decimal(-30), Decimal(90), Decimal(50)]
    for opening, minb, rate in [(Decimal(0), Decimal(0), Decimal("0.01")),
                                (Decimal(50), Decimal(20), Decimal("0.015"))]:
        draws, principal, interest = solve_credit_line(flows, opening, minb, rate)
        plan = solve_cash_management(flows, opening, minb, rate, Decimal("0.02"),
                                     credit_on=True, invest_on=False)
        assert plan.draws == draws
        assert plan.principal == principal
        assert plan.interest == interest
        assert all(v == 0 for v in plan.deposit_placement)
        assert all(v == 0 for v in plan.deposit_income)


def test_surplus_placed_and_earns_income():
    """Профицит выше min_balance размещается в депозит и приносит доход на остаток начала."""
    plan = solve_cash_management(
        [Decimal(100), Decimal(0), Decimal(0)], Decimal(0), Decimal(0),
        Decimal("0.01"), Decimal("0.10"), credit_on=False, invest_on=True)
    assert plan.deposit_placement[0] == Decimal(100)     # весь профицит размещён
    assert plan.deposit_balance[0] == Decimal(100)
    assert plan.deposit_income[0] == Decimal(0)          # на начало t0 депозита нет
    assert plan.deposit_income[1] == Decimal(10)         # 100 × 10%
    assert plan.deposit_balance[1] == Decimal(110)       # доход реинвестируется


def test_deposit_withdrawn_before_credit_on_deficit():
    """При дефиците сперва изымается депозит, только остаток покрывается кредитом."""
    plan = solve_cash_management(
        [Decimal(100), Decimal(-160)], Decimal(0), Decimal(0),
        Decimal("0.01"), Decimal("0.00"), credit_on=True, invest_on=True)
    assert plan.deposit_placement[0] == Decimal(100)     # t0: разместили 100
    # t1: дефицит 160 → изъять 100 (депозит), привлечь 60 (кредит)
    assert plan.deposit_placement[1] == Decimal(-100)
    assert plan.deposit_balance[1] == Decimal(0)
    assert plan.draws[1] == Decimal(60)


def _model(n=12, volume=10, price=2000) -> ProjectModel:
    model = ProjectModel()
    model.header.duration_months = n
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(volume)] * n,
                         price=[Decimal(price)] * n)],
    )
    return model


def test_invest_surplus_end_to_end_invariant_and_b6():
    """Сквозной расчёт с авторазмещением: депозит виден в B6, инвариант B20=B34 держится."""
    model = _model()
    model.financing = Financing(auto_financing=AutoFinancing(
        invest_surplus=True, invest_annual_rate=Decimal("0.08"), min_balance=Decimal(0)))
    result = run(model)                                  # InvariantError не поднялся → баланс сошёлся
    assert all(almost_equal(result.balance["B20"][t], result.balance["B34"][t])
               for t in range(result.n))
    assert result.balance["B6"][-1] > 0                 # накопленный депозит в ценных бумагах
    assert result.cashflow["C9"][-1] > 0                # доход по депозиту в кассе


def test_invest_income_raises_tax():
    """Доход авто-депозита растит налогооблагаемую прибыль (I20 → I27)."""
    base = _model()
    invested = _model()
    invested.financing = Financing(auto_financing=AutoFinancing(
        invest_surplus=True, invest_annual_rate=Decimal("0.12")))
    r0, r1 = run(base), run(invested)
    assert sum(r1.income["I20"], Decimal(0)) > sum(r0.income["I20"], Decimal(0))
    assert sum(r1.income["I27"], Decimal(0)) > sum(r0.income["I27"], Decimal(0))


def test_invest_surplus_inert_when_off():
    """invest_surplus=False → числа как без автофинансирования (golden-инертность)."""
    plain = run(_model())
    off = _model()
    off.financing = Financing(auto_financing=AutoFinancing(invest_surplus=False))
    again = run(off)
    assert plain.income["I28"] == again.income["I28"]
    assert plain.balance["B6"] == again.balance["B6"]
    assert plain.cashflow["C9"] == again.cashflow["C9"]


def test_credit_and_invest_together_converge():
    """Оба контура вместе: расчёт сходится, инвариант держится."""
    model = _model(volume=5, price=1500)
    model.financing = Financing(auto_financing=AutoFinancing(
        enabled=True, annual_rate=Decimal("0.20"),
        invest_surplus=True, invest_annual_rate=Decimal("0.06"), min_balance=Decimal(10000)))
    result = run(model)
    assert all(almost_equal(result.balance["B20"][t], result.balance["B34"][t])
               for t in range(result.n))
    assert "не сошёлся" not in " ".join(result.warnings)
