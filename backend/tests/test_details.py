"""Тесты детализации строк отчётов (drill-down, пакет №6, G2).

Главный инвариант (Q4): Σ слагаемых детализации = строка отчёта, точно (Decimal).
Детализация не входит в golden-снимок (Q5) — корректность доказывается здесь.
"""
from decimal import Decimal

from calc_core import run
from calc_core.models import ProjectModel
from calc_core.models.investment import Asset, InvestmentPlan
from calc_core.models.operating import (
    CostFunction,
    DirectCostKind,
    DirectCostLine,
    FixedCostLine,
    OperatingPlan,
    Product,
    SalesLine,
    StaffPosition,
)
from calc_core.samples import build_sample_project


def _detail(result, code):
    return next((d for d in result.details if d.code == code), None)


def _sum_items(detail, n):
    total = [Decimal(0)] * n
    for item in detail.items:
        for t in range(n):
            total[t] += item.values[t]
    return total


def test_details_sum_to_statement_lines_on_sample():
    """На демо-проекте Σ слагаемых каждого кода равна строке отчёта помесячно."""
    result = run(build_sample_project())
    checked = 0
    for code, stmt in [("I1", result.income), ("I16", result.income),
                       ("C1", result.cashflow), ("C2", result.cashflow),
                       ("C3", result.cashflow), ("C14", result.cashflow)]:
        d = _detail(result, code)
        if d is None:
            continue
        assert _sum_items(d, result.n) == stmt[code], f"Σ слагаемых != {code}"
        checked += 1
    assert checked >= 4                                # демо наполнено: продажи/издержки/активы


def test_details_i1_by_product_names():
    result = run(build_sample_project())
    d = _detail(result, "I1")
    assert d is not None
    names = {i.name for i in d.items}
    model = build_sample_project()
    assert names == {p.name for p in model.operating_plan.products
                     if any(s.product_id == p.id for s in model.operating_plan.sales)}


def test_details_merge_lines_of_same_product():
    """Две строки сбыта одного продукта сливаются в одно слагаемое."""
    model = ProjectModel()
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[
            SalesLine(product_id="p1", volume=[Decimal(1)] * 12, price=[Decimal(100)] * 12),
            SalesLine(product_id="p1", volume=[Decimal(2)] * 12, price=[Decimal(100)] * 12),
        ],
    )
    result = run(model)
    d = _detail(result, "I1")
    assert d is not None and len(d.items) == 1
    assert d.items[0].name == "Товар"
    assert d.items[0].values == result.income["I1"]


def test_details_staff_and_assets_and_costs():
    """Штат виден в I16 («Штат: …»), активы — в C14, статьи — в C2/C3; суммы сходятся."""
    model = ProjectModel()
    model.settings.vat_rate = Decimal("0.20")
    model.operating_plan = OperatingPlan(
        products=[Product(id="p1", name="Товар")],
        sales=[SalesLine(product_id="p1", volume=[Decimal(10)] * 12,
                         price=[Decimal(500)] * 12)],
        direct_costs=[
            DirectCostLine(name="Сырьё А", amount=[Decimal(100)] * 12),
            DirectCostLine(name="Сдельная", kind=DirectCostKind.PIECE_WAGES,
                           amount=[Decimal(50)] * 12),
        ],
        fixed_costs=[FixedCostLine(name="Аренда", function=CostFunction.ADMIN,
                                   amount=[Decimal(200)] * 12)],
        staff=[StaffPosition(name="Директор", function=CostFunction.STAFF_ADMIN,
                             monthly_salary=Decimal(1000), headcount=1)],
    )
    model.investment_plan = InvestmentPlan(assets=[
        Asset(name="Станок", cost=Decimal(12000), purchase_month=1, life_months=12),
    ])
    result = run(model)

    i16 = _detail(result, "I16")
    assert {i.name for i in i16.items} == {"Аренда", "Штат: Директор"}
    assert _sum_items(i16, 12) == result.income["I16"]

    c14 = _detail(result, "C14")
    assert [i.name for i in c14.items] == ["Станок"]
    assert c14.items[0].values[1] == Decimal(12000) * Decimal("1.20")   # с НДС
    assert _sum_items(c14, 12) == result.cashflow["C14"]

    assert {i.name for i in _detail(result, "C2").items} == {"Сырьё А"}
    assert {i.name for i in _detail(result, "C3").items} == {"Сдельная"}
    assert _sum_items(_detail(result, "C2"), 12) == result.cashflow["C2"]
    assert _sum_items(_detail(result, "C3"), 12) == result.cashflow["C3"]


def test_details_empty_model_inert():
    result = run(ProjectModel())
    assert result.details == []


def test_details_order_canonical():
    result = run(build_sample_project())
    codes = [d.code for d in result.details]
    order = ["I1", "I16", "C1", "C2", "C3", "C12", "C14"]
    assert codes == [c for c in order if c in codes]   # канонический порядок


def test_details_c12_sums_to_line():
    """Детализация C12 (профильные налоги): Σ слагаемых = строка C12."""
    result = run(build_sample_project())
    d = _detail(result, "C12")
    assert d is not None
    assert _sum_items(d, result.n) == result.cashflow["C12"]


def test_details_in_calc_response(client, auth_headers):
    """/calculate отдаёт details; Σ слагаемых I1 равна строке I1 ответа."""
    sample = client.get("/api/v1/sample").json()
    r = client.post("/api/v1/calculate", json=sample)
    assert r.status_code == 200
    body = r.json()
    codes = {d["code"] for d in body["details"]}
    assert "I1" in codes
    d = next(d for d in body["details"] if d["code"] == "I1")
    i1 = next(line for line in body["income"]["lines"] if line["code"] == "I1")
    total = [sum(Decimal(i["values"][t]) for i in d["items"]) for t in range(body["n"])]
    assert total == [Decimal(v) for v in i1["values"]]
