"""Налоговый год и кварталы уплаты — календарные (пакет H, H1; 0.9.46; SPEC §11).

До 0.9.46 год считался от старта проекта: при старте в июле убыток декабря гасил прибыль
января как «свой», хотя по календарю он уже убыток прошлого года (ст. 285 НК РФ — под
ограничение доли, п. 2.1 ст. 283), а квартальный налог платился в сентябре, декабре,
марте — месяцы, которыми ни один квартал не кончается... кроме случайно совпавших.

Граница — одна функция (`tax_year_offset`) на перенос убытков и на график уплаты
профильных и настраиваемых налогов. При старте в январе ничего не меняется.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from calc_core import ProjectModel, run
from calc_core.engine.taxes import _payment_schedule
from calc_core.models import (
    Company,
    CostFunction,
    Financing,
    FixedCostLine,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.environment import Tax
from calc_core.money import almost_equal
from calc_core.reports.statements import carry_losses, tax_year_offset

D = Decimal
RATE = D("0.20")


@pytest.mark.parametrize(("month", "offset"), [(1, 0), (2, 1), (7, 6), (12, 11)])
def test_the_offset_is_the_months_of_the_calendar_year_already_gone(month, offset):
    assert tax_year_offset(date(2026, month, 1)) == offset
    assert tax_year_offset(date(2026, month, 28)) == offset     # день месяца не важен


def test_a_loss_of_the_previous_calendar_year_is_limited_even_within_twelve_months():
    """Старт в июле: убыток июля–декабря — убыток прошлого года уже в январе, и гасит
    январскую прибыль не больше чем наполовину. «Год от старта» считал бы его своим."""
    bases = [D(-100)] * 6 + [D(100)] * 6          # июль–декабрь убыток, январь–июнь прибыль
    calendar = carry_losses(bases, D("0.5"), year_offset=6)
    from_start = carry_losses(bases, D("0.5"), year_offset=0)
    assert calendar[6:] == [D(50)] * 6            # прошлый год — не больше половины базы
    assert from_start[6:] == [D(100)] * 6         # прежняя конвенция: «свой» год целиком


def test_january_start_is_the_old_convention():
    """Старт в январе: граница года — ровно двенадцатый месяц, как было до 0.9.46."""
    s = carry_losses([D(-100)] * 12 + [D(100)] * 12, D("0.5"), year_offset=0)
    assert s[12:] == [D(50)] * 12


@pytest.mark.parametrize(("offset", "quarter_ends"), [
    (0, [2, 5, 8, 11]),        # январь: март, июнь, сентябрь, декабрь
    (1, [1, 4, 7, 10]),        # февраль: первый квартал неполный — платится в марте
    (6, [2, 5, 8, 11]),        # июль: сентябрь, декабрь, март, июнь
    (10, [1, 4, 7, 10]),       # ноябрь: декабрь, март, июнь, сентябрь
])
def test_a_quarter_ends_in_march_june_september_or_december(offset, quarter_ends):
    accrual = [D(1)] * 12
    paid = _payment_schedule(accrual, "quarter", 12, offset=offset)
    assert [t for t, v in enumerate(paid) if v] == quarter_ends
    assert sum(paid) + (12 - 1 - quarter_ends[-1]) == 12      # хвост — неуплата в B21
    first = quarter_ends[0]
    assert paid[first] == D(first + 1)            # первый период — с месяца старта


def test_a_year_ends_in_december():
    paid = _payment_schedule([D(1)] * 24, "year", 24, offset=9)   # старт в октябре
    assert [t for t, v in enumerate(paid) if v] == [2, 14]
    assert paid[2] == D(3)                        # октябрь–декабрь — неполный первый год
    assert paid[14] == D(12)


def _project(start: date, *, vat="0", profit="month", vat_period="month",
             taxes: list[Tax] | None = None) -> ProjectModel:
    """Полгода убытков (издержки без продаж), затем прибыль."""
    n = 24
    model = ProjectModel(
        header=ProjectHeader(name="Календарь", start_date=start, duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=RATE,
                                 property_tax_rate=D(0), vat_rate=D(vat),
                                 profit_tax_periodicity=profit, vat_periodicity=vat_period),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(0)] * 6 + [D(20)] * 18,
                             price=[D(100)] * n)],
            # Убыток полугодия (6000) больше половины месячной базы: ограничение видно.
            fixed_costs=[FixedCostLine(name="Администрация", function=CostFunction.ADMIN,
                                       amount=[D(1000)] * 6 + [D(100)] * (n - 6))],
        ),
        financing=Financing(common_shares=D(10000)),
    )
    if taxes:
        model.environment.taxes = taxes
    return model


def test_the_engine_carries_losses_by_the_calendar():
    """Проект с июля: убытки полугодия в январе — прошлого года, перенос ограничен."""
    july = run(_project(date(2026, 7, 1)))
    january = run(_project(date(2026, 1, 1)))
    base_jan = july.income["I23"][6] + july.income["I25"][6]
    assert base_jan > 0
    assert july.income["I22"][6] == base_jan * D("0.5")     # прошлый год — половина
    assert january.income["I22"][6] == base_jan             # свой год — целиком


def test_quarterly_profit_and_vat_are_paid_at_calendar_quarter_ends():
    model = _project(date(2026, 8, 1), vat="0.20", profit="quarter", vat_period="quarter")
    r = run(model)
    monthly = run(_project(date(2026, 8, 1), vat="0.20"))
    # Разница кассы налогов относительно помесячной уплаты: ненулевые «доплаты» — только
    # в месяцы, которыми кончается календарный квартал (сентябрь = t1, декабрь = t4, …).
    ends = {t for t in range(r.n) if (t + tax_year_offset(model.header.start_date)) % 3 == 2}
    assert ends == {1, 4, 7, 10, 13, 16, 19, 22}
    for t in range(r.n):
        if t not in ends:
            assert r.cashflow["C12"][t] <= monthly.cashflow["C12"][t]
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_custom_taxes_follow_the_same_calendar():
    tax = Tax(name="Сбор", rate=D("0.01"), base="revenue", periodicity="quarter",
              allocation="expense")
    r = run(_project(date(2026, 5, 1), taxes=[tax]))
    items = next(d.items for d in r.details if d.code == "C12")
    series = next(i.values for i in items if i.name == "Сбор")
    # Старт в мае, выручка — с ноября (t6): платится в декабре (t7), марте, июне, сентябре.
    paid_months = [t for t, v in enumerate(series) if v]
    assert paid_months[:4] == [7, 10, 13, 16]
    assert all((t + 4) % 3 == 2 for t in paid_months)       # только концы кварталов
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
