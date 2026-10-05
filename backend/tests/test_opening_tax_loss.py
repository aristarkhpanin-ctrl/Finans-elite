"""Стартовый налоговый убыток (пакет H, H3; 0.9.48; SPEC §11).

У действующего бизнеса почти всегда есть неиспользованный налоговый убыток прошлых лет, а
модель его не принимала: налог первых лет такого проекта был завышен. Теперь это поле
модели: оно открывает пул убытков прошлых лет и гасит базу под той же долей (п. 2.1
ст. 283), что и убытки, понесённые в горизонте. Ноль инертен.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from calc_core import ProjectModel, run
from calc_core.methodology import methodology_map
from calc_core.models import (
    Company,
    Financing,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.reports.statements import profit_tax

D = Decimal
RATE = D("0.20")


def test_the_opening_loss_is_a_prior_year_loss_under_the_limit():
    """Стартовый убыток 1000 и прибыль по 100 в месяц: зачёт — половина нарастающей базы
    (50 в месяц), пока пул не исчерпан, а не вся база сразу."""
    bases = [D(100)] * 24
    block = profit_tax(bases, limit=D("0.5"), year_offset=0, rate=RATE, opening_loss=D(1000))
    assert block.carried[:12] == [D(50)] * 12          # первый год: 600 из 1000
    assert block.carried[12:20] == [D(50)] * 8         # второй: остаток 400 за 8 месяцев
    assert block.carried[20:] == [D(0)] * 4
    assert sum(block.carried) == D(1000)               # весь убыток — и не больше
    free = profit_tax(bases, limit=D(1), year_offset=0, rate=RATE, opening_loss=D(1000))
    assert sum(free.tax[:10]) == 0 and free.tax[10] == D(20)   # без ограничения — сразу


def test_zero_is_inert():
    bases = [D(-300), D(500), D(200)] * 8
    with_zero = profit_tax(bases, limit=D("0.5"), year_offset=0, rate=RATE, opening_loss=D(0))
    without = profit_tax(bases, limit=D("0.5"), year_offset=0, rate=RATE)
    assert with_zero == without


def _model(opening: str, limit: str = "0.5") -> ProjectModel:
    n = 12
    return ProjectModel(
        header=ProjectHeader(name="Действующий", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=RATE,
                                 property_tax_rate=D(0), vat_rate=D(0),
                                 loss_carryforward_limit=D(limit), opening_tax_loss=D(opening)),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Услуга")],
            sales=[SalesLine(product_id="p1", volume=[D(10)] * n, price=[D(100)] * n)],
        ),
        financing=Financing(common_shares=D(1000)),
    )


def test_the_engine_takes_it_from_the_settings():
    plain = run(_model("0")).income
    opened = run(_model("3000")).income
    assert sum(plain["I22"]) == 0
    assert opened["I22"] == [D(500)] * 6 + [D(0)] * 6     # половина базы 1000, пока пул есть
    assert sum(plain["I27"]) == D(2400)
    assert sum(opened["I27"]) == D(1800)                  # 20% от 12000 − 3000
    for b20, b34 in zip(run(_model("3000")).balance["B20"], run(_model("3000")).balance["B34"],
                        strict=True):
        assert abs(b20 - b34) < D("0.01")                # на баланс не влияет


def test_a_negative_opening_loss_is_rejected():
    with pytest.raises(ValueError):
        ProjectModel.model_validate({"settings": {"opening_tax_loss": "-1"}})


def test_the_methodology_map_recomputes_at_the_norm_with_the_same_opening_loss():
    """Доля выше нормы — расхождение, только если числа при норме другие. Пересчёт идёт
    с тем же стартовым убытком: без него «другие числа» были бы от забытого убытка, а не
    от доли, и предупреждение появлялось бы там, где его нет."""
    def item(model):
        return next(c for c in methodology_map(model, run(model)).choices
                    if c.id == "tax.loss_carryforward")

    at_norm = item(_model("3000", "0.5"))
    assert at_norm.engaged and at_norm.evidence["opening_tax_loss"] == "3000"
    assert at_norm.divergence == ""
    above = item(_model("3000", "1"))
    assert "выше нормы" in above.divergence
    # Стартовый убыток 300 меньше половины базы месяца: при любой доле он гасится в первом
    # же месяце, числа при норме те же — расхождения нет. Пересчёт без стартового убытка
    # дал бы здесь нули и ложное предупреждение.
    same = item(_model("300", "1"))
    assert same.divergence == "" and "i22_at_norm_total" not in same.evidence
    silent = item(_model("0"))
    assert not silent.engaged and "ни на старте" in silent.silent_because


def test_an_opening_loss_with_nothing_to_offset_is_named_not_hidden():
    """«Задействовано» доказывается числом: убыток, который не во что зачесть, отчётов не
    меняет. Но причина молчания обязана его назвать, а не сказать «убытка нет»."""
    model = _model("5000")
    model.operating_plan.sales[0].volume = [D(0)] * 12          # прибыли нет вовсе
    item = next(c for c in methodology_map(model, run(model)).choices
                if c.id == "tax.loss_carryforward")
    assert not item.engaged
    assert "5 000 ₽" in item.silent_because and "не во что" in item.silent_because
