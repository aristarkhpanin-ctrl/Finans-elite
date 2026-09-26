"""Анализ рисков оценки (Финанс-Аудит, «Экран 13»; методика — SPEC, Приложение Р).

Оценка (Прил. П) даёт одно число. Переговоры ведут не по числу, а по тому, **насколько
оно устойчиво**. Модуль отвечает на два вопроса: что двигает цену сильнее всего
(торнадо) и какова вероятность, что она ниже запрошенной (Монте-Карло).

Три решения задают модуль.

**Смещение — коэффициент, и оно одно для всех параметров.** `1 ± шаг` вместо смеси
«±1 п.п. для ставок, ±10% для сумм»: смесь делает столбцы несопоставимыми, а порядок
торнадо — следствием выбранных шагов. Шаг показывается рядом со столбцами, и рядом же
сказано, что порядок зависит от соглашения о нём: торнадо, скрывающий свой шаг, выдаёт
соглашение за измерение.

**Прогон без оценки не заменяется нулём.** Терминальной стоимости не существует,
показатель ушёл в минус — такой прогон считается отдельно, и его доля называется. Ноль
занизил бы медиану, тихое выбрасывание скрыло бы, что в части сценариев бизнес не
оценивается вовсе.

**Результат воспроизводим.** Фиксированный ``seed``: иначе медиана менялась бы при
каждом обновлении, и назвать её за столом переговоров было бы нельзя.

Ничего не пересчитывает своей арифметикой: каждый прогон — тот же ``build_valuation``
при смещённых допущениях, поэтому разойтись с методикой оценки модуль не может.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .earnings import EarningsQuality
from .models import RISK_PARAMS, AuditSubjectModel, RiskDistribution
from .obligations import ObligationRegister
from .result import AuditResult
from .valuation import build_valuation

D = Decimal

#: Ряды допущений: смещаются поэлементно; остальные параметры — скаляры.
ROW_PARAMS = ("growth", "capex", "nwc_change")

#: Расхождение медианы с базовой оценкой, с которого о нём сообщается (Р.3).
MEDIAN_DRIFT = D("0.10")

#: Число столбцов гистограммы распределения цены.
HISTOGRAM_BINS = 12


@dataclass
class TornadoBar:
    """Столбец торнадо: цена при смещении одного допущения вниз и вверх."""

    param: str
    label: str
    step: Decimal
    low_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_delta: Optional[Decimal] = None
    high_delta: Optional[Decimal] = None
    #: Размах — по нему столбцы упорядочены. ``None``, когда одна из сторон не считается.
    span: Optional[Decimal] = None
    note: str = ""


@dataclass
class HistogramBin:
    """Столбец гистограммы: [from_, to) и число попаданий."""

    from_: Decimal
    to: Decimal
    count: int


@dataclass
class MonteCarlo:
    """Распределение цены за 100% доли по прогонам со случайными допущениями."""

    iterations: int = 0
    #: Прогонов, в которых оценка посчиталась, и прогонов, в которых нет (Р.2).
    valued: int = 0
    unvalued: int = 0
    median: Optional[Decimal] = None
    mean: Optional[Decimal] = None
    p10: Optional[Decimal] = None
    p25: Optional[Decimal] = None
    p75: Optional[Decimal] = None
    p90: Optional[Decimal] = None
    minimum: Optional[Decimal] = None
    maximum: Optional[Decimal] = None
    histogram: list[HistogramBin] = field(default_factory=list)
    #: Доля прогонов ниже запрошенной цены. ``None`` — цена продавца не введена (Р.4).
    below_asking: Optional[Decimal] = None
    #: Расхождение медианы с детерминированной оценкой (доля); ``None`` — не с чем.
    median_drift: Optional[Decimal] = None


@dataclass
class RiskResult:
    """Анализ рисков целиком: торнадо, Монте-Карло и честные оговорки."""

    #: Оценка не посчитана — анализировать нечего.
    available: bool = False
    blockers: list[str] = field(default_factory=list)
    base_price: Optional[Decimal] = None
    step: Decimal = D("0.10")
    tornado: list[TornadoBar] = field(default_factory=list)
    monte_carlo: Optional[MonteCarlo] = None
    warnings: list[str] = field(default_factory=list)
    not_computed: list[str] = field(default_factory=list)


NOT_COMPUTED = [
    "Сценарии с вероятностями — вероятности назначает человек, и взвешенная ими "
    "«ожидаемая цена» выглядела бы расчётом, будучи суммой догадок. Разброс даёт "
    "Монте-Карло, где догадка объявлена распределением явно.",
    "Стресс-тест «потеря контрагента» — разреза выручки по контрагентам в модели нет "
    "(та же причина, что у концентрации выручки в сводке).",
]


def _shifted(model: AuditSubjectModel, param: str, factor: Decimal) -> AuditSubjectModel:
    """Копия модели со смещённым допущением. Смещение всегда мультипликативное (Р.1)."""
    m = model.model_copy(deep=True)
    a = m.valuation
    if param in ROW_PARAMS:
        setattr(a, param, [v * factor for v in getattr(a, param)])
    else:
        setattr(a, param, getattr(a, param) * factor)
    return m


def _price(model: AuditSubjectModel, result: AuditResult, earnings: EarningsQuality,
           obligations: ObligationRegister) -> Optional[Decimal]:
    """Цена за 100% доли при данных допущениях; ``None`` — оценка не считается.

    Прогон идёт через тот же ``build_valuation``, что и основная оценка: своей
    арифметики у анализа рисков нет, и разойтись с методикой он не может.
    """
    return build_valuation(model, result, earnings, obligations).equity_value


def _is_set(model: AuditSubjectModel, param: str) -> bool:
    """Задано ли допущение. Незаданное не двигает цену — и об этом надо сказать."""
    value = getattr(model.valuation, param)
    return bool(value) if param in ROW_PARAMS else value != 0


def build_tornado(model: AuditSubjectModel, result: AuditResult,
                  earnings: EarningsQuality, obligations: ObligationRegister,
                  base: Decimal, step: Decimal) -> list[TornadoBar]:
    """Смещение каждого допущения по отдельности (Р.1).

    Остальные держатся на базовом уровне: взаимодействия параметров торнадо не
    показывает и не претендует на это.
    """
    bars: list[TornadoBar] = []
    for param, label in RISK_PARAMS.items():
        bar = TornadoBar(param=param, label=label, step=step)
        if not _is_set(model, param):
            bar.note = "допущение не задано — цену не двигает"
            bar.span = D(0)
            bars.append(bar)
            continue
        low = _price(_shifted(model, param, D(1) - step), result, earnings, obligations)
        high = _price(_shifted(model, param, D(1) + step), result, earnings, obligations)
        bar.low_price, bar.high_price = low, high
        bar.low_delta = low - base if low is not None else None
        bar.high_delta = high - base if high is not None else None
        if low is None or high is None:
            # Сторона, которой не существует, не заменяется базой: смещение уводит
            # модель туда, где оценки нет, и это факт, а не «цена не изменилась».
            bar.note = ("при смещении в одну из сторон оценка не считается — "
                        "терминальной стоимости или прибыли там не существует")
        else:
            bar.span = abs(high - low)
        bars.append(bar)
    # Столбцы без размаха уходят вниз: сравнивать их не с чем.
    bars.sort(key=lambda b: (b.span is None, -(b.span or D(0))))
    return bars


def _sample(rnd: random.Random, dist: RiskDistribution) -> Optional[Decimal]:
    """Выборка коэффициента. ``None`` — распределение задано не полностью."""
    if dist.kind == "uniform":
        if dist.low is None or dist.high is None:
            return None
        return D(str(rnd.uniform(float(dist.low), float(dist.high))))
    if dist.kind == "normal":
        if dist.mean is None or dist.std is None:
            return None
        return D(str(rnd.gauss(float(dist.mean), float(dist.std))))
    if dist.low is None or dist.high is None or dist.mode is None:
        return None
    return D(str(rnd.triangular(float(dist.low), float(dist.high), float(dist.mode))))


def _percentile(values: list[Decimal], share: Decimal) -> Decimal:
    """Перцентиль по ближайшему рангу (соглашение объявлено, а не подобрано)."""
    if not values:
        raise ValueError("пустая выборка")
    index = int((share * D(len(values))).to_integral_value(rounding="ROUND_CEILING")) - 1
    return values[max(0, min(len(values) - 1, index))]


def _histogram(values: list[Decimal]) -> list[HistogramBin]:
    low, high = values[0], values[-1]
    if high == low:
        return [HistogramBin(from_=low, to=high, count=len(values))]
    width = (high - low) / D(HISTOGRAM_BINS)
    bins = [HistogramBin(from_=low + width * D(i), to=low + width * D(i + 1), count=0)
            for i in range(HISTOGRAM_BINS)]
    for v in values:
        idx = int(((v - low) / width).to_integral_value(rounding="ROUND_FLOOR"))
        bins[max(0, min(HISTOGRAM_BINS - 1, idx))].count += 1
    return bins


def run_monte_carlo(model: AuditSubjectModel, result: AuditResult,
                    earnings: EarningsQuality, obligations: ObligationRegister,
                    base: Decimal, warnings: list[str]) -> Optional[MonteCarlo]:
    """Распределение цены по прогонам со случайными коэффициентами допущений (Р.2).

    Возвращает ``None``, если неопределённых допущений не объявлено: Монте-Карло по
    нулю распределений дал бы одну и ту же цену N раз и выглядел бы анализом.
    """
    declared = [u for u in model.risk.uncertain if u.param]
    if not declared:
        return None

    usable = []
    for u in declared:
        probe = _sample(random.Random(0), u.distribution)
        if probe is None:
            # Неполное распределение не заменяется значением по умолчанию: подставить
            # своё значило бы прогнать модель по допущению, которого никто не задавал.
            warnings.append(
                f"Распределение допущения «{RISK_PARAMS.get(u.param, u.param)}» задано "
                "не полностью — в прогон оно не включено.")
            continue
        usable.append(u)
    if not usable:
        return None

    mc = MonteCarlo(iterations=model.risk.iterations)
    rnd = random.Random(model.risk.seed)
    prices: list[Decimal] = []
    for _ in range(model.risk.iterations):
        m = model.model_copy(deep=True)
        for u in usable:
            factor = _sample(rnd, u.distribution)
            assert factor is not None            # проверено выше
            a = m.valuation
            if u.param in ROW_PARAMS:
                setattr(a, u.param, [v * factor for v in getattr(a, u.param)])
            else:
                setattr(a, u.param, getattr(a, u.param) * factor)
        price = _price(m, result, earnings, obligations)
        if price is None:
            mc.unvalued += 1                     # не ноль и не молча выброшен (Р.2)
        else:
            prices.append(price)

    mc.valued = len(prices)
    if not prices:
        return mc

    prices.sort()
    mc.minimum, mc.maximum = prices[0], prices[-1]
    mc.mean = sum(prices, D(0)) / D(len(prices))
    mc.median = _percentile(prices, D("0.5"))
    mc.p10 = _percentile(prices, D("0.1"))
    mc.p25 = _percentile(prices, D("0.25"))
    mc.p75 = _percentile(prices, D("0.75"))
    mc.p90 = _percentile(prices, D("0.9"))
    mc.histogram = _histogram(prices)

    if base:
        mc.median_drift = (mc.median - base) / abs(base)
        if abs(mc.median_drift) > MEDIAN_DRIFT:
            warnings.append(
                f"Медиана прогонов ({mc.median:.0f}) расходится с базовой оценкой "
                f"({base:.0f}) на {abs(mc.median_drift) * 100:.0f}% — заданные "
                "распределения смещены относительно базовых допущений.")

    asking = model.valuation.asking_price
    if asking is not None and asking > 0:
        # Вероятность существует только против запрошенной цены (Р.4).
        below = sum(1 for p in prices if p < asking)
        mc.below_asking = D(below) / D(len(prices))
    return mc


def analyze_risk(model: AuditSubjectModel, result: AuditResult,
                 earnings: Optional[EarningsQuality] = None,
                 obligations: Optional[ObligationRegister] = None) -> RiskResult:
    """Торнадо и Монте-Карло поверх посчитанной оценки.

    Оценки нет — анализировать нечего: причины берутся из неё же, чтобы человек не
    искал их на другом экране.
    """
    earnings = earnings if earnings is not None else EarningsQuality()
    obligations = obligations if obligations is not None else ObligationRegister()
    risk = RiskResult(step=model.risk.tornado_step, not_computed=list(NOT_COMPUTED))

    valuation = build_valuation(model, result, earnings, obligations)
    if valuation.equity_value is None:
        risk.blockers = list(valuation.blockers) or [
            "Оценка не посчитана — анализировать нечего."]
        return risk

    risk.available = True
    risk.base_price = valuation.equity_value
    risk.tornado = build_tornado(model, result, earnings, obligations,
                                 valuation.equity_value, model.risk.tornado_step)
    risk.monte_carlo = run_monte_carlo(model, result, earnings, obligations,
                                       valuation.equity_value, risk.warnings)
    return risk
