"""Ограничение переноса убытков (пакет G, G10; SPEC §11; п. 2.1 ст. 283 НК РФ).

Пул убытков покрывал налоговую базу **целиком**, а норма разрешает уменьшать базу на
убытки **прошлых** налоговых периодов не больше чем на 50% (2017–2026). У проекта с
убыточным стартом налог первых прибыльных лет был занижен, уплата — сдвинута вперёд.

Правила, которые здесь проверяются:

* налоговый год — 12 месяцев от старта проекта (та же конвенция, что у периодичности
  уплаты);
* убыток **текущего** года гасит прибыль того же года **полностью** — это не перенос;
* убытки **прошлых** лет уменьшают базу месяца не больше чем на долю
  ``loss_carryforward_limit`` (по умолчанию 0,5); неиспользованное переходит дальше —
  бессрочно (п. 2 ст. 283);
* ``limit = 1`` — **те же числа, что до G10** (эталон прежнего алгоритма — ниже).
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal, localcontext

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
from calc_core.money import CALC_CONTEXT
from calc_core.reports.statements import build_income
from calc_core.templates import INDUSTRY_TEMPLATES

D = Decimal
RATE = D("0.20")


def _income(bases: list[Decimal], limit: Decimal):
    """ОПУ, где налоговая база месяца — ровно ``bases``: прочие строки нулевые."""
    return build_income({"I1": list(bases)}, len(bases), RATE, loss_limit=limit)


def _old_algorithm(bases: list[Decimal]) -> list[Decimal]:
    """Прежний перенос (до G10): пул покрывает базу целиком — эталон для limit = 1."""
    pool, out = D(0), []
    for base in bases:
        if base < 0:
            pool += -base
            out.append(D(0))
        else:
            applied = min(pool, base)
            pool -= applied
            out.append(applied)
    return out


def test_no_limit_is_exactly_the_old_numbers():
    """limit = 1 — прежний алгоритм байт-в-байт, на случайных рядах с убытками."""
    rng = random.Random(20260926)
    for _ in range(50):
        bases = [D(rng.randint(-500, 500)) for _ in range(rng.randint(1, 60))]
        assert _income(bases, D(1))["I22"] == _old_algorithm(bases)


def test_no_limit_keeps_the_old_numbers_to_the_last_digit():
    """Без ограничения база закрывается **той же операцией**, что и раньше. Общая формула
    «своё + (база − своё) × 1» на полноточных числах расходится с базой в последнем
    знаке — эти два числа как раз такие (найдены перебором при точности движка,
    34 знака: ``CALC_CONTEXT``, его же ставит импорт ``calc_core``)."""
    with localcontext(CALC_CONTEXT):
        own = D("-7694248.940891811316337897712899135")
        base = D("96587676.41898487861570636214448039")
        assert -own + (base + own) * 1 != base                  # ловушка настоящая
        bases = [D(-200_000_000)] + [D(0)] * 11 + [own, base]   # пул больше базы
        assert _income(bases, D(1))["I22"] == _old_algorithm(bases)


def test_a_loss_of_the_same_year_offsets_in_full():
    """Убыток текущего года — не перенос: он гасит прибыль того же года полностью."""
    bases = [D(-100)] * 6 + [D(100)] * 6
    s = _income(bases, D("0.5"))
    assert s["I22"][6:] == [D(100)] * 6
    assert sum(s["I27"]) == 0


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


def test_current_year_first_then_prior_years_at_the_limit():
    # Первый год — убыток 1200. Во втором: сначала свой убыток 300, потом прибыль.
    bases = [D(-100)] * 12 + [D(-300)] + [D(200)] * 11
    s = _income(bases, D("0.5"))
    # Месяц 13: своя прибыль 200 гасит свой убыток 300 → остаётся 100 своего убытка.
    assert s["I22"][13] == D(200)
    # Месяц 14: свой остаток 100 целиком, затем прошлые годы — не больше половины от 100.
    assert s["I22"][14] == D(100) + D(50)


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
