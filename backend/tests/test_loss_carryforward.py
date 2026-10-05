"""Налог на прибыль: перенос убытков и база нарастающим итогом (G10, H1, H2; SPEC §11).

G10 ограничил перенос убытков прошлых лет долей базы (п. 2.1 ст. 283 НК РФ: периоды
2017–2030 гг.), H1 сделал налоговый год календарным, H2 (0.9.47) — базу нарастающим
итогом года (ст. 274, 286): до него база была помесячной, и убыток после обложенной
прибыли того же года начисленного налога не уменьшал.

Правила, которые здесь проверяются:

* налоговый год — календарный (здесь старт в январе, поэтому это те же 12 месяцев от
  старта — календарь проверяет ``test_calendar_tax_year.py``);
* внутри года база — нарастающий итог: убыток уменьшает базу своего года в любом месяце,
  в том числе после прибыли — тогда месячный налог отрицателен (сторно);
* непокрытый убыток года становится убытком **прошлых** лет и уменьшает нарастающую базу
  следующих лет не больше чем на долю ``loss_carryforward_limit`` (по умолчанию 0,5);
  неиспользованное переходит дальше — бессрочно (п. 2 ст. 283);
* годовые суммы совпадают с годовой формулой закона (эталон — ниже, по годам, без
  месяцев); без убытка после прибыли внутри года месячный налог — тот же, что до H2.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import pytest

from calc_core import ProjectModel, run
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
from calc_core.models.project import LOSS_CARRYFORWARD_NORM
from calc_core.reports.statements import build_income
from calc_core.templates import INDUSTRY_TEMPLATES

D = Decimal
RATE = D("0.20")


def _income(bases: list[Decimal], limit: Decimal, benefit: Decimal = D(0)):
    """ОПУ, где налоговая база месяца — ровно ``bases``: прочие строки нулевые."""
    return build_income({"I1": list(bases)}, len(bases), RATE, benefit,
                        loss_limit=limit, year_offset=0, opening_loss=D(0))


def _annual_norm(bases: list[Decimal], limit: Decimal, benefit: Decimal = D(0)) -> list[Decimal]:
    """Эталон по закону, **по годам**: база года — сумма месяцев; убытки прошлых лет гасят
    её не больше чем на долю ``limit``; непокрытый убыток года уходит в пул. Месяцев
    здесь нет вовсе — это и отличает эталон от движка."""
    pool, out = D(0), []
    for y in range(0, len(bases), 12):
        base = sum(bases[y:y + 12], D(0))
        positive = max(D(0), base)
        carried = min(pool, positive if limit >= 1 else positive * limit)
        taxable = positive - carried
        out.append((taxable - benefit * taxable) * RATE)
        pool = pool - carried + max(D(0), -base)
    return out


def _monthly_before_h2(bases: list[Decimal], limit: Decimal) -> list[Decimal]:
    """Налог по помесячной базе, как считал движок 0.9.44–0.9.46 (эталон для сравнения)."""
    pool, this_year, tax = D(0), D(0), []
    for t, base in enumerate(bases):
        if t % 12 == 0:
            this_year = D(0)
        if base < 0:
            pool += -base
            this_year += -base
            tax.append(D(0))
            continue
        own = min(this_year, base)
        cap = base if limit >= 1 else own + (base - own) * limit
        applied = min(pool, cap)
        pool -= applied
        this_year -= min(this_year, applied)
        tax.append((base - applied) * RATE)
    return tax


def _yearly(series: list[Decimal]) -> list[Decimal]:
    return [sum(series[y:y + 12], D(0)) for y in range(0, len(series), 12)]


@pytest.mark.parametrize("limit", [D(0), D("0.5"), D(1)])
def test_every_year_is_taxed_by_the_annual_formula(limit):
    """Годовой налог движка — годовая формула закона на случайных рядах с убытками в любых
    местах года, при любой доле и с льготой."""
    rng = random.Random(20260928)
    for _ in range(60):
        bases = [D(rng.randint(-500, 500)) for _ in range(rng.randint(1, 60))]
        benefit = D(rng.choice(["0", "0.25"]))
        s = _income(bases, limit, benefit)
        for got, want in zip(_yearly(s["I27"]), _annual_norm(bases, limit, benefit), strict=True):
            assert abs(got - want) < D("1e-20")


def test_without_a_loss_after_profit_the_monthly_tax_is_what_it_was():
    """Изменилось только то, что было расхождением: если внутри года убытки идут раньше
    прибыли, месячный налог тот же, что при помесячной базе до H2."""
    rng = random.Random(28)
    for _ in range(40):
        bases = []
        for _year in range(rng.randint(1, 4)):
            losses = rng.randint(0, 11)
            bases += [D(-rng.randint(0, 500)) for _ in range(losses)]
            bases += [D(rng.randint(0, 500)) for _ in range(12 - losses)]
        for limit in (D(0), D("0.5"), D(1)):
            assert _income(bases, limit)["I27"] == _monthly_before_h2(bases, limit)


def test_a_loss_after_taxed_profit_reverses_the_tax_already_accrued():
    """Прибыль полгода, затем убыток: налог месяцев убытка отрицателен, годовой — от
    итога года. При помесячной базе налог полугодия остался бы начисленным целиком."""
    bases = [D(100)] * 6 + [D(-100)] * 3 + [D(0)] * 3
    s = _income(bases, D("0.5"))
    assert s["I27"][:6] == [D(20)] * 6
    assert s["I27"][6:9] == [D(-20)] * 3
    assert sum(s["I27"]) == D(60)                          # 20% от итога года 300
    assert sum(_monthly_before_h2(bases, D("0.5"))) == D(120)
    assert s["I22"] == [D(0)] * 12                         # это не перенос: база года


def test_a_loss_of_the_same_year_is_not_a_carryforward():
    """Убыток текущего года уменьшает базу года и в перенос (`I22`) не попадает."""
    bases = [D(-100)] * 6 + [D(100)] * 6
    s = _income(bases, D("0.5"))
    assert s["I22"] == [D(0)] * 12
    assert sum(s["I26"]) == 0 and sum(s["I27"]) == 0


def test_prior_year_losses_reduce_the_base_by_half_at_most():
    bases = [D(-100)] * 12 + [D(100)] * 24
    s = _income(bases, D("0.5"))
    assert s["I22"][12:24] == [D(50)] * 12            # второй год: половина базы
    assert s["I26"][12:24] == [D(50)] * 12
    assert s["I22"][24:36] == [D(50)] * 12            # остаток пула — дальше, бессрочно
    assert sum(s["I22"]) == D(1200)                   # за горизонт — весь убыток


def test_the_limit_moves_tax_earlier_not_in_total():
    """Разница во времени, а не в сумме: налог растёт в первых прибыльных годах, а за
    длинный горизонт, где весь убыток успевает зачесться, сумма налога та же."""
    bases = [D(-100)] * 12 + [D(100)] * 36
    limited, free = _income(bases, D("0.5")), _income(bases, D(1))
    assert sum(limited["I27"][12:24]) > sum(free["I27"][12:24])
    assert sum(limited["I27"]) == sum(free["I27"])


def test_prior_years_are_limited_on_the_cumulative_base():
    """Второй год: сначала свой убыток 300, потом прибыль по 200. Прошлые убытки гасят
    **нарастающую** базу года не больше чем наполовину — от неё, а не от месяца."""
    bases = [D(-100)] * 12 + [D(-300)] + [D(200)] * 11
    s = _income(bases, D("0.5"))
    assert s["I22"][12:14] == [D(0), D(0)]      # нарастающая база −300, −100 — гасить нечего
    assert s["I22"][14] == D(50)                # база +100 → половина
    assert s["I22"][15:] == [D(100)] * 9        # каждый месяц база растёт на 200


def _project(limit: Decimal) -> ProjectModel:
    """Год убытков (−100 в месяц), затем прибыль 2000 в месяц; всё прочее выключено."""
    n = 24
    return ProjectModel(
        header=ProjectHeader(name="loss", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=RATE,
                                 property_tax_rate=D(0), vat_rate=D(0),
                                 loss_carryforward_limit=limit),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(0)] * 12 + [D(20)] * 12,
                             price=[D(100)] * n)],
            fixed_costs=[FixedCostLine(name="Администрация", function=CostFunction.ADMIN,
                                       amount=[D(100)] * 12 + [D(0)] * 12)],
        ),
        financing=Financing(common_shares=D(2000)),
    )


def test_the_setting_reaches_the_tax_block_through_the_pipeline():
    limited = run(_project(D("0.5"))).income
    assert limited["I22"][12:14] == [D(1000), D(200)]     # половина базы 2000, потом остаток
    assert limited["I27"][12] == D(200)                    # 20% от 1000, а не ноль
    free = run(_project(D(1))).income
    assert free["I22"][12:14] == [D(1200), D(0)]           # прежнее: пул закрыл базу разом
    assert sum(limited["I27"]) == sum(free["I27"])         # за горизонт — та же сумма


@pytest.mark.parametrize("limit", [D(0), D("0.5"), D(1)])
def test_the_balance_converges_under_any_limit(limit):
    for key, template in INDUSTRY_TEMPLATES.items():
        model: ProjectModel = template.build()
        model.settings.loss_carryforward_limit = limit
        result = run(model)
        for b20, b34 in zip(result.balance["B20"], result.balance["B34"], strict=True):
            assert abs(b20 - b34) < D("0.01"), key


def test_the_default_follows_the_norm():
    """Умолчание — норма, и проект, сохранённый до G10 (поля в нём нет), при пересчёте
    получает её же: это и есть смена методики с бампом версии, а не молчаливый выбор."""
    assert LOSS_CARRYFORWARD_NORM == D("0.5")
    saved_before = ProjectModel().model_dump(mode="json")
    del saved_before["settings"]["loss_carryforward_limit"]
    assert ProjectModel.model_validate(saved_before).settings.loss_carryforward_limit \
        == LOSS_CARRYFORWARD_NORM
    for key, template in INDUSTRY_TEMPLATES.items():
        assert template.build().settings.loss_carryforward_limit == LOSS_CARRYFORWARD_NORM, key


@pytest.mark.parametrize("bad", ["-0.1", "1.5"])
def test_a_limit_outside_zero_to_one_is_rejected(bad):
    with pytest.raises(ValueError):
        ProjectModel.model_validate({"settings": {"loss_carryforward_limit": bad}})


def test_a_custom_profit_tax_is_reversed_with_the_profile_one():
    """Пресет «прибыль» настраиваемого налога — та же нарастающая база (`I26`), а не
    `МАКС(I26, 0)`: иначе при сторно внутри года налог поверх профильного остался бы
    начисленным и переплаченным."""
    from calc_core.models.environment import Tax

    n = 12
    model = ProjectModel(
        header=ProjectHeader(name="Сторно", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=RATE,
                                 property_tax_rate=D(0), vat_rate=D(0)),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(20)] * 6 + [D(0)] * 6,
                             price=[D(100)] * n)],
            fixed_costs=[FixedCostLine(name="Администрация", function=CostFunction.ADMIN,
                                       amount=[D(500)] * n)],
        ),
        financing=Financing(common_shares=D(10000)),
    )
    model.environment.taxes = [Tax(name="Надбавка", rate=D("0.05"), base="profit",
                                   allocation="profit")]
    r = run(model)
    items = next(d.items for d in r.details if d.code == "C12")
    surcharge = next(i.values for i in items if i.name == "Надбавка")
    assert any(v < 0 for v in r.income["I27"])                   # сторно есть
    # Уплата — в следующем месяце: декабрьское (сторно) начисление — за горизонтом.
    assert sum(surcharge, D(0)) == sum(r.income["I26"][:-1], D(0)) * D("0.05")
