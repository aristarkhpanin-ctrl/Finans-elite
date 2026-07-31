"""Структуры результата анализа (Финанс-Аудит) — аналог ``CalcResult`` первого продукта.

Чистые данные над введённой фактической отчётностью: аналитическая форма, тренды
(горизонтальный/вертикальный анализ) и коэффициенты по периодам.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

#: Ряд коэффициента по периодам (None — показатель не определён, напр. деление на ноль).
RatioSeries = list[Optional[Decimal]]


@dataclass
class AuditLine:
    """Строка аналитической формы: код, метка и значения по периодам."""

    code: str
    label: str
    values: list[Decimal]
    #: Подытог (итоговая строка формы) — для выделения в таблице.
    subtotal: bool = False


@dataclass
class TrendLine:
    """Горизонтальный анализ строки: изменение к предыдущему периоду и темп.

    Первый период — база (``delta``/``rate`` = None). ``rate`` — доля прироста
    (0.15 = +15%); None, если база нулевая (темп не определён).
    """

    code: str
    label: str
    delta: RatioSeries = field(default_factory=list)
    rate: RatioSeries = field(default_factory=list)


@dataclass
class ShareLine:
    """Вертикальный анализ строки: доля в базе периода (баланс — актив, ОПУ — выручка)."""

    code: str
    label: str
    share: RatioSeries = field(default_factory=list)


@dataclass
class AuditResult:
    """Полный результат анализа фактической отчётности."""

    n: int
    periods: list[str] = field(default_factory=list)          # подписи периодов
    balance: list[AuditLine] = field(default_factory=list)    # аналитическая форма баланса
    income: list[AuditLine] = field(default_factory=list)     # аналитическая форма ОПУ
    horizontal: list[TrendLine] = field(default_factory=list)
    vertical: list[ShareLine] = field(default_factory=list)
    #: Коэффициенты: группа → показатель → ряд по периодам.
    ratios: dict[str, dict[str, RatioSeries]] = field(default_factory=dict)
    #: Инвариант ввода: актив − пассив по периодам и флаг сходимости.
    balance_gap: list[Decimal] = field(default_factory=list)
    balanced: bool = True
    #: Диагностика (скоринги банкротства + нормативы + «светофор»); None при пустой модели.
    diagnostics: Optional["Diagnostics"] = None
    warnings: list[str] = field(default_factory=list)


if TYPE_CHECKING:  # только для аннотации — избегаем циклического импорта
    from .diagnostics import Diagnostics
