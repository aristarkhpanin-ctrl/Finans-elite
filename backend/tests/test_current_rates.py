"""Действующие ставки налогов (пакет J, J1).

Проверка «правильно ли посчитан налог» на шаблоне давала верный ответ «нет»: модель по
умолчанию и все шаблоны считали налог на прибыль по 20%, а с 2025 года общая ставка — 25%
(п. 1 ст. 284 НК РФ); НДС в шаблонах — 20%, а с 2026 года основная — 22% (п. 3 ст. 164).
Эталоны golden — вход теста со ставками прежних лет, их числа от закона не сдвигаются;
пользователю демонстрационные модели отдаются по действующим ставкам.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from calc_core.models import ProjectSettings
from calc_core.samples import TEMPLATES
from calc_core.templates import (
    CURRENT_PROFIT_TAX,
    CURRENT_VAT,
    INDUSTRY_TEMPLATES,
    at_current_rates,
)

client = TestClient(app)


def test_new_project_uses_the_current_profit_tax_rate():
    assert ProjectSettings().profit_tax_rate == Decimal("0.25") == CURRENT_PROFIT_TAX


def test_industry_templates_use_current_general_rates():
    for tpl in INDUSTRY_TEMPLATES.values():
        s = tpl.build().settings
        if tpl.id == "farming":          # ЕСХН 6% и НДС 10% — отраслевые, а не общие
            assert s.profit_tax_rate == Decimal("0.06") and s.vat_rate == Decimal("0.10")
            continue
        assert s.profit_tax_rate == CURRENT_PROFIT_TAX, tpl.id
        assert s.vat_rate in (CURRENT_VAT, Decimal(0)), tpl.id


def test_demo_templates_are_served_at_current_rates_but_golden_inputs_stay():
    for template_id, (_, _, build) in TEMPLATES.items():
        golden = build().settings
        served = client.get(f"/api/v1/templates/{template_id}").json()["settings"]
        assert golden.profit_tax_rate == Decimal("0.20")        # эталон не сдвинулся
        assert Decimal(served["profit_tax_rate"]) == CURRENT_PROFIT_TAX
        if golden.vat_rate == Decimal("0.20"):
            assert Decimal(served["vat_rate"]) == CURRENT_VAT
        else:                                                    # льготная/нулевая — как была
            assert Decimal(served["vat_rate"]) == golden.vat_rate


def test_only_general_rates_are_replaced():
    model = TEMPLATES["production"][2]()
    model.settings.profit_tax_rate = Decimal("0.06")
    model.settings.vat_rate = Decimal("0.10")
    same = at_current_rates(model)
    assert same.settings.profit_tax_rate == Decimal("0.06")
    assert same.settings.vat_rate == Decimal("0.10")
