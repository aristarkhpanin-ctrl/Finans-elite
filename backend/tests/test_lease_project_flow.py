"""Лизинг в потоке проекта (0.9.50, пакет J — найдено на демо-данных).

В кэш-фло лизинговые платежи стоят в финансовой деятельности (``C25``), а показатели
считались по ``C13 + C20``: ни аренда оборудования, ни стоимость предмета финансового
лизинга в NPV/IRR и в оценку не попадали. Шаблон «Грузоперевозки» с тремя тягачами в
лизинге показывал IRR 170%.

Правило: операционный лизинг — издержка потока проекта (это аренда), финансовый —
покупка в долг: стоимость предмета — вложение в месяц начала, платежи — финансирование.
Тесты — эквивалентности: лизинг обязан давать проекту тот же поток, что и его
экономический двойник, а не «правдоподобное число».
"""
from __future__ import annotations

from decimal import Decimal

from calc_core import run
from calc_core.engine.pipeline import finance_lease_value
from calc_core.integrator import consolidate
from calc_core.models import (
    Asset,
    AssetCategory,
    CostFunction,
    EquityInjection,
    Financing,
    FixedCostLine,
    InvestmentPlan,
    Lease,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
)

d = Decimal
N = 24


def _base(**settings) -> ProjectModel:
    """Сервис без НДС: выручка, одно оборудование на капитал."""
    return ProjectModel(
        header=ProjectHeader(name="Лизинг", duration_months=N),
        settings=ProjectSettings(discount_rate_annual=d("0.18"), **settings),
        operating_plan=OperatingPlan(
            products=[Product(id="p", name="Услуга")],
            sales=[SalesLine(product_id="p", volume=[d(100)] * N, price=[d(3000)] * N)]),
        investment_plan=InvestmentPlan(assets=[Asset(
            name="Станок", cost=d(1_000_000), purchase_month=0, life_months=60,
            category=AssetCategory.EQUIPMENT)]),
        financing=Financing(equity=[EquityInjection(amount=d(2_000_000))]),
    )


def _with(model: ProjectModel, **financing) -> ProjectModel:
    return model.model_copy(update={"financing": model.financing.model_copy(update=financing)})


def _close(a: list[Decimal], b: list[Decimal]) -> bool:
    return all(abs(x - y) < d("1e-9") for x, y in zip(a, b, strict=True))


def test_without_leases_the_project_flow_is_the_pre_financing_flow():
    """Без лизинга поток проекта — C13 + C20; последний месяц несёт ещё закрытие расчётов
    конца горизонта (0.9.57, пакет K)."""
    r = run(_base(profit_tax_rate=d("0.25")))
    cf = r.cashflow
    pre = [cf["C13"][t] + cf["C20"][t] for t in range(N)]
    assert r.project_flow[:-1] == pre[:-1]
    release = r.working_capital_release.total
    assert abs(r.project_flow[-1] - pre[-1] - release) < d("0.00001")


def test_operating_lease_counts_like_rent():
    """Операционный лизинг — аренда: проекту он обходится ровно как общая издержка той же
    суммы (без НДС оба вычитаемы). До 0.9.50 аренда в показатели не попадала вовсе."""
    lease = _with(_base(profit_tax_rate=d("0.25")),
                  leases=[Lease(name="Погрузчик", monthly_payment=d(40_000), term_months=18)])
    rent = _base(profit_tax_rate=d("0.25"))
    rent.operating_plan.fixed_costs = [FixedCostLine(
        name="Аренда погрузчика", function=CostFunction.ADMIN,
        amount=[d(40_000)] * 18 + [d(0)] * (N - 18))]
    a, b = run(lease), run(rent)
    assert _close(a.project_flow, b.project_flow)
    assert abs(a.metrics.npv - b.metrics.npv) < d("1e-6")
    assert a.metrics.irr_annual is not None and b.metrics.irr_annual is not None
    assert abs(a.metrics.irr_annual - b.metrics.irr_annual) < d("1e-9")
    # и в оценке бизнеса — тот же свободный поток
    assert abs(a.valuation.gordon_value - b.valuation.gordon_value) < d("1e-6")


def test_finance_lease_counts_like_a_purchase():
    """Финансовый лизинг — покупка в долг: проекту он обходится как предмет той же
    стоимости, купленный на свои (без налога и НДС поток от способа оплаты не зависит).
    Стоимость — та же приведённая, что уходит в баланс (B19)."""
    lease_terms = dict(name="Тягач", monthly_payment=d(90_000), start_month=2,
                       term_months=12, finance=True, annual_rate=d("0.19"))
    leased = _with(_base(profit_tax_rate=d(0)), leases=[Lease(**lease_terms)])
    value = finance_lease_value(Lease(**lease_terms))
    bought = _base(profit_tax_rate=d(0))
    bought.investment_plan.assets.append(Asset(
        name="Тягач", cost=value, purchase_month=2, life_months=12,
        category=AssetCategory.EQUIPMENT))
    a, b = run(leased), run(bought)
    assert _close(a.project_flow, b.project_flow)
    assert abs(a.metrics.npv - b.metrics.npv) < d("1e-6")
    # Баланс лизинга — та же стоимость предмета на конец месяца начала (до амортизации
    # следующих): одна формула на баланс и на поток.
    assert abs(a.balance["B19"][2] - (value - value / 12)) < d("1e-6")


def test_lease_insurance_is_a_project_cost_for_both_kinds():
    base = _base(profit_tax_rate=d(0))
    for finance in (False, True):
        with_ins = _with(base, leases=[Lease(name="Предмет", monthly_payment=d(10_000),
                                             term_months=6, finance=finance,
                                             insurance_monthly=d(1_500))])
        without = _with(base, leases=[Lease(name="Предмет", monthly_payment=d(10_000),
                                            term_months=6, finance=finance)])
        diff = [x - y for x, y in zip(run(without).project_flow,
                                      run(with_ins).project_flow, strict=True)]
        assert _close(diff, [d(1_500)] * 6 + [d(0)] * (N - 6)), finance


def test_holding_takes_the_leases_of_its_projects():
    """Свод холдинга — сумма потоков проектов: из суммарного C13 + C20 лизинг не
    восстановить (он в C25), и группа снова стала бы бесплатно арендующей."""
    m = _with(_base(profit_tax_rate=d("0.25")),
              leases=[Lease(name="Тягач", monthly_payment=d(90_000), term_months=12,
                            finance=True, annual_rate=d("0.19"))])
    single = run(m)
    group = consolidate([m, m], group_discount_rate=d("0.18"))
    assert abs(group.metrics.npv - 2 * single.metrics.npv) < d("1e-6")
