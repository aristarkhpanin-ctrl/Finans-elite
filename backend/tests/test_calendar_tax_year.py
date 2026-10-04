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
    Asset,
    AssetCategory,
    Company,
    CostFunction,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.environment import Tax
from calc_core.money import almost_equal
from calc_core.reports.statements import carry_losses, profit_tax, tax_year_offset

D = Decimal
RATE = D("0.20")


@pytest.mark.parametrize(("month", "offset"), [(1, 0), (2, 1), (7, 6), (12, 11)])
def test_the_offset_is_the_months_of_the_calendar_year_already_gone(month, offset):
    assert tax_year_offset(date(2026, month, 1)) == offset
    assert tax_year_offset(date(2026, month, 28)) == offset     # день месяца не важен


def test_a_loss_of_the_previous_calendar_year_is_limited_even_within_twelve_months():
    """Старт в июле: убыток июля–декабря — убыток прошлого года уже в январе, и гасит
    январскую прибыль не больше чем наполовину. «Год от старта» счёл бы его своим и
    свернул бы в базу года целиком — налога не было бы вовсе."""
    bases = [D(-100)] * 6 + [D(100)] * 6          # июль–декабрь убыток, январь–июнь прибыль
    calendar = profit_tax(bases, limit=D("0.5"), year_offset=6, rate=RATE)
    from_start = profit_tax(bases, limit=D("0.5"), year_offset=0, rate=RATE)
    assert calendar.carried[6:] == [D(50)] * 6    # прошлый год — не больше половины базы
    assert sum(calendar.tax) == D(60)             # 20% от непокрытой половины
    assert from_start.carried == [D(0)] * 12      # «свой» год: убыток в базе, не перенос
    assert sum(from_start.tax) == 0


def test_january_start_is_the_old_convention():
    """Старт в январе: граница года — ровно двенадцатый месяц, как было до 0.9.46."""
    s = carry_losses([D(-100)] * 12 + [D(100)] * 12, D("0.5"), year_offset=0)
    assert s[12:] == [D(50)] * 12


@pytest.mark.parametrize(("offset", "quarter_ends"), [
    (0, [2, 5, 8, 11]),        # январь: март, июнь, сентябрь, декабрь
    (1, [1, 4, 7, 10]),        # февраль: первый квартал неполный — кончается в марте
    (6, [2, 5, 8, 11]),        # июль: сентябрь, декабрь, март, июнь
    (10, [1, 4, 7, 10]),       # ноябрь: декабрь, март, июнь, сентябрь
])
def test_a_quarter_ends_in_march_june_september_or_december(offset, quarter_ends):
    """Период — календарный квартал; срок — месяц, следующий за ним (пакет J, J3)."""
    accrual = [D(1)] * 12
    paid = _payment_schedule(accrual, "quarter", 12, offset=offset, due="next_month")
    due_months = [e + 1 for e in quarter_ends if e + 1 < 12]
    assert [t for t, v in enumerate(paid) if v] == due_months
    first = quarter_ends[0]
    assert paid[first + 1] == D(first + 1)        # первый период — с месяца старта
    # Срок которых не наступил к концу горизонта — задолженность (B21), а не уплата.
    assert sum(paid) == quarter_ends[len(due_months) - 1] + 1


def test_a_year_ends_in_december_and_its_profit_tax_is_due_in_march():
    """Год — календарный; налог на прибыль за год — до 28 марта (п. 4 ст. 289, ст. 287)."""
    paid = _payment_schedule([D(1)] * 24, "year", 24, offset=9, due="profit")   # октябрь
    assert [t for t, v in enumerate(paid) if v] == [5, 17]    # март 2027 и март 2028
    assert paid[5] == D(3)                        # октябрь–декабрь — неполный первый год
    assert paid[17] == D(12)


def test_profit_advances_are_due_next_month_and_the_year_in_march():
    """Помесячные авансы (п. 2 ст. 286) — в следующем месяце; декабрь — это уже налог за
    год, и он платится в марте, а не в январе."""
    accrual = [D(t + 1) for t in range(24)]
    paid = _payment_schedule(accrual, "month", 24, offset=0, due="profit")
    assert paid[0] == 0
    assert paid[1] == D(1) and paid[11] == D(11)             # январь → февраль, …, ноябрь
    assert paid[12] == 0 and paid[13] == D(13)               # январь 2027: декабрь не тут
    assert paid[14] == D(12) + D(14)                         # март: год + аванс февраля
    quarterly = _payment_schedule(accrual, "quarter", 24, offset=0, due="profit")
    assert [t for t, v in enumerate(quarterly) if v] == [3, 6, 9, 14, 15, 18, 21]
    assert quarterly[14] == sum(accrual[9:12], D(0))         # IV квартал — в марте


def test_vat_for_a_quarter_is_due_in_three_equal_parts():
    """НДС за квартал — равными долями не позднее 28-го числа каждого из трёх месяцев,
    следующих за ним (п. 1 ст. 174). Доли в сумме — ровно начисленное: пыль деления в B21
    не копится."""
    accrual = [D(10), D(0), D(0)] + [D(0)] * 9
    paid = _payment_schedule(accrual, "quarter", 12, offset=0, due="vat")
    assert [t for t, v in enumerate(paid) if v] == [3, 4, 5]
    assert paid[3] == paid[4] == D(10) / 3
    assert paid[3] + paid[4] + paid[5] == D(10)
    # Квартал, чьи доли выходят за горизонт, платится частично: остальное — в B21.
    tail = _payment_schedule([D(0)] * 9 + [D(9)] + [D(0)] * 3, "quarter", 13, offset=0,
                             due="vat")
    assert tail[12] == D(3) and sum(tail) == D(3)


def test_property_tax_advances_follow_the_quarter_and_the_year_is_due_in_february():
    """Налог на имущество (ст. 383 НК РФ, 0.9.53): авансы за I–III кварталы — в апреле,
    июле, октябре; налог за год — до 28 февраля следующего года."""
    accrual = [D(1)] * 24
    paid = _payment_schedule(accrual, "quarter", 24, offset=0, due="property")
    assert [t for t, v in enumerate(paid) if v] == [3, 6, 9, 13, 15, 18, 21]
    assert paid[13] == D(3)                                   # IV квартал 2026 — февраль


def test_the_engine_pays_property_tax_after_the_quarter():
    n = 16
    model = ProjectModel(
        header=ProjectHeader(name="Имущество", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=D(0),
                                 property_tax_rate=D("0.022"), vat_rate=D(0)),
        company=Company(starting_balance=StartingBalance(cash=D(2_000_000),
                                                          paid_in_capital=D(2_000_000))),
        investment_plan=InvestmentPlan(assets=[Asset(
            name="Цех", cost=D(1_200_000), purchase_month=0, life_months=120,
            category=AssetCategory.BUILDINGS)]),
        financing=Financing(common_shares=D(10000)),
    )
    r = run(model)
    paid = _c12(r, "Налог на имущество")
    i9 = r.income["I9"]
    assert [t for t, v in enumerate(paid) if v] == [3, 6, 9, 13, 15]
    assert paid[3] == sum(i9[0:3], D(0))
    assert paid[13] == sum(i9[9:12], D(0))                    # за год — в феврале
    # Начислено и не уплачено к концу горизонта — задолженность, а не пропажа.
    assert almost_equal(r.balance["B21"][n - 1], sum(i9, D(0)) - sum(paid, D(0)))
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(n))


def test_the_due_rule_is_named_explicitly():
    with pytest.raises(ValueError):
        _payment_schedule([D(1)] * 3, "month", 3, offset=0, due="last_month")  # type: ignore[arg-type]


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
    assert july.income["I27"][6] == base_jan * D("0.5") * RATE
    # Январский старт: убытки полугодия — свой год, нарастающая база ещё отрицательна.
    assert january.income["I22"][6] == 0 and january.income["I27"][6] == 0


def _c12(r, name: str) -> list[D]:
    items = next(d.items for d in r.details if d.code == "C12")
    return next(i.values for i in items if i.name == name)


def test_quarterly_profit_and_vat_are_paid_by_the_law():
    model = _project(date(2026, 8, 1), vat="0.20", profit="quarter", vat_period="quarter")
    r = run(model)
    offset = tax_year_offset(model.header.start_date)
    ends = [t for t in range(r.n) if (t + offset) % 3 == 2]
    assert ends == [1, 4, 7, 10, 13, 16, 19, 22]
    december = {e for e in ends if (e + offset) % 12 == 11}
    assert december == {4, 16}
    profit_months = {t for t, v in enumerate(_c12(r, "Налог на прибыль")) if v}
    assert profit_months and profit_months <= {e + (3 if e in december else 1) for e in ends}
    vat = _c12(r, "НДС к уплате")
    vat_months = {t for t, v in enumerate(vat) if v}
    assert vat_months and vat_months <= {e + k for e in ends for k in (1, 2, 3)}
    for e in ends:
        if e + 3 < r.n and vat[e + 1]:
            assert vat[e + 1] == vat[e + 2]                   # равные доли квартала
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))


def test_custom_taxes_follow_the_same_calendar():
    tax = Tax(name="Сбор", rate=D("0.01"), base="revenue", periodicity="quarter",
              allocation="expense")
    r = run(_project(date(2026, 5, 1), taxes=[tax]))
    series = _c12(r, "Сбор")
    # Старт в мае, выручка — с ноября (t6): IV квартал кончается в декабре (t7) и
    # платится в январе (t8), дальше — апрель, июль, октябрь.
    paid_months = [t for t, v in enumerate(series) if v]
    assert paid_months[:4] == [8, 11, 14, 17]
    assert all((t + 4) % 3 == 0 for t in paid_months)       # месяц после конца квартала
    assert all(almost_equal(r.balance["B20"][t], r.balance["B34"][t]) for t in range(r.n))
