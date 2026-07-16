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
from ..reports.result import ProductMargin, ProductMargins
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
