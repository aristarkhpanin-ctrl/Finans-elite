"""Каталог строк ввода фактической отчётности (аналитическая форма, РСБУ-агрегаты).

Финанс-Аудит (продукт №2). Пользователь вводит эти агрегированные статьи по периодам;
итог актива = Σ активов, итог пассива = Σ (капитал + обязательства); их равенство —
инвариант «актив = пассив». Расшифровки (Приложение А спецификации) — v2.
"""
from __future__ import annotations

# Актив (сумма = суммарный актив).
BALANCE_ASSET_LINES: list[tuple[str, str]] = [
    ("A_FIXED", "Внеоборотные активы"),
    ("A_INVENTORY", "Запасы"),
    ("A_RECEIVABLE", "Дебиторская задолженность"),
    ("A_CASH", "Денежные средства и эквиваленты"),
]

# Пассив (капитал + обязательства; сумма = суммарный пассив).
BALANCE_EQLIAB_LINES: list[tuple[str, str]] = [
    ("P_EQUITY", "Капитал и резервы"),
    ("P_LONG", "Долгосрочные обязательства"),
    ("P_SHORT", "Краткосрочные обязательства"),
]

# Отчёт о финансовых результатах (вводимые статьи; подытоги — производные, считаются движком).
INCOME_LINES: list[tuple[str, str]] = [
    ("I_REVENUE", "Выручка"),
    ("I_COGS", "Себестоимость продаж"),
    ("I_OPEX", "Коммерческие и управленческие расходы"),
    ("I_INTEREST", "Проценты к уплате"),
    ("I_OTHER", "Прочие доходы/расходы (сальдо)"),
    ("I_TAX", "Налог на прибыль"),
]

ASSET_CODES = [c for c, _ in BALANCE_ASSET_LINES]
EQLIAB_CODES = [c for c, _ in BALANCE_EQLIAB_LINES]
INCOME_CODES = [c for c, _ in INCOME_LINES]
BALANCE_CODES = ASSET_CODES + EQLIAB_CODES

LABELS: dict[str, str] = dict(BALANCE_ASSET_LINES + BALANCE_EQLIAB_LINES + INCOME_LINES)
