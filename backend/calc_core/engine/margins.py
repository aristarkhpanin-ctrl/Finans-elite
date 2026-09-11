"""Маржа по продуктам с рецептурой (BOM) — аналитика поверх модели (SPEC §6/§8).

Отчётные формы не затрагивает: считается из модели теми же соглашениями, что движок
(индексация инфляцией, курс FX, гейт старта производства). Продукты **без** рецептуры в
отчёт не входят (их себестоимость не определена — не фейкуем аллокацию); суммовые прямые
издержки показываются одной строкой «нераспределённые».

Упрощение (осознанное): BOM-себестоимость проданного считается в ценах месяца продажи
(текущая стоимость), а не по историческим партиям пула запасов — для аналитики маржи
этого достаточно и это детерминировано воспроизводимо из модели.
"""
from __future__ import annotations

from decimal import Decimal

from ..models import DirectCostKind
from ..models.project import ProjectModel
from ..money import ZERO
from ..reports.result import DivisionMargin, ProductMargin, ProductMargins
from ..series import zeros
from .pipeline import (
    _apply_production_starts,
    _fx_series,
    _inflation_index,
    _inflation_year_rates,
    _pad,
)


def compute_product_margins(model: ProjectModel, n: int) -> ProductMargins:
    """Маржа по продуктам: выручка − BOM-материалы − сдельная ЗП (по проданному объёму)."""
    op = model.operating_plan
    specs = [p for p in op.products if p.bom or p.piece_wage_per_unit]
    if not specs:
        return ProductMargins()

    model = _apply_production_starts(model)   # гейт старта: до старта объёмы нулевые
    op = model.operating_plan
    settings = model.settings
    idx_sales = _inflation_index(
        _inflation_year_rates(settings.inflation_sales, settings.inflation_sales_series), n)
    idx_direct = _inflation_index(
        _inflation_year_rates(settings.inflation_direct, settings.inflation_direct_series), n)
    idx_wages = _inflation_index(
        _inflation_year_rates(settings.inflation_wages, settings.inflation_wages_series), n)
    fx = _fx_series(model.environment, n)
    mat_by_id = {m.id: m for m in op.materials}

    # Проданный объём и выручка по продукту (той же формулой, что движок: инфляция/курс).
    sold: dict[str, list[Decimal]] = {}
    revenue: dict[str, Decimal] = {}
    for line in op.sales:
        vol = _pad(line.volume, n)
        price = _pad(line.price, n)
        acc = sold.setdefault(line.product_id, zeros(n))
        rev = revenue.setdefault(line.product_id, ZERO)
        for t in range(n):
            acc[t] += vol[t]
            rate = fx[t] if line.foreign else idx_sales[t]
            rev += vol[t] * price[t] * rate
        revenue[line.product_id] = rev

    products: list[ProductMargin] = []
    for p in specs:
        vol = sold.get(p.id, zeros(n))
        rev = revenue.get(p.id, ZERO)
        bom_cost = ZERO
        wages = ZERO
        for t in range(n):
            if vol[t] == 0:
                continue
            unit = ZERO
            for bl in p.bom:
                m = mat_by_id.get(bl.material_id)
                if m is None:
                    continue
                rate = fx[t] if m.foreign else idx_direct[t]
                unit += bl.qty_per_unit * m.unit_price * rate
            bom_cost += vol[t] * unit
            wages += vol[t] * p.piece_wage_per_unit * idx_wages[t]
        margin = rev - bom_cost - wages
        products.append(ProductMargin(
            product_id=p.id, name=p.name, revenue=rev, bom_cost=bom_cost,
            piece_wages=wages, margin=margin,
            margin_share=(margin / rev) if rev != 0 else None,
        ))

    # Суммовые (глобальные) прямые издержки — не распределяются, показываются итогом.
    unallocated = ZERO
    for dc in op.direct_costs:
        base = _pad(dc.amount, n)
        for t in range(n):
            if dc.foreign:
                unallocated += base[t] * fx[t]
            else:
                idx = idx_direct if dc.kind == DirectCostKind.MATERIALS else idx_wages
                unallocated += base[t] * idx[t]
    return ProductMargins(products=products, unallocated_direct=unallocated)


def compute_division_margins(model: ProjectModel, margins: ProductMargins) -> list[DivisionMargin]:
    """Маржа по подразделениям (gap 4.5): свёртка маржи продуктов бизнес-единицы.

    Чисто аналитика поверх ``product_margins`` — суммирует показатели продуктов с
    рецептурой, отнесённых к подразделению (`Product.division_id`). Продукты без
    подразделения не сворачиваются (видны на уровне продуктов); без фейковой аллокации —
    суммовые издержки остаются «нераспределёнными». Пустой список подразделений инертен.
    """
    if not model.company.divisions:
        return []
    div_of = {p.id: p.division_id for p in model.operating_plan.products}
    name_of = {d.id: (d.name or d.id) for d in model.company.divisions}

    order: list[str] = []                       # порядок первого появления (стабильность)
    agg: dict[str, dict[str, Decimal]] = {}
    count: dict[str, int] = {}
    for pm in margins.products:
        did = div_of.get(pm.product_id)
        if did is None or did not in name_of:
            continue
        if did not in agg:
            order.append(did)
            agg[did] = {"revenue": ZERO, "bom_cost": ZERO, "piece_wages": ZERO, "margin": ZERO}
            count[did] = 0
        a = agg[did]
        a["revenue"] += pm.revenue
        a["bom_cost"] += pm.bom_cost
        a["piece_wages"] += pm.piece_wages
        a["margin"] += pm.margin
        count[did] += 1

    out: list[DivisionMargin] = []
    for did in order:
        a = agg[did]
        rev = a["revenue"]
        out.append(DivisionMargin(
            division_id=did, name=name_of[did], revenue=rev, bom_cost=a["bom_cost"],
            piece_wages=a["piece_wages"], margin=a["margin"],
            margin_share=(a["margin"] / rev) if rev != 0 else None,
            product_count=count[did],
        ))
    return out
