"""Диагностика финансового состояния (Финанс-Аудит, фаза D).

Две части:

1. **Скоринговые модели банкротства** — общеизвестные (публичные) формулы Альтмана и
   двухфакторная модель. Считаются над аналитической формой; период с недостающими
   данными даёт ``None`` («не определён»), а не подставленный ноль.
2. **Оценка коэффициентов по нормативам** — универсальные пороги (SPEC, приложение Е):
   каждый показатель в каждом периоде получает статус ``good``/``warn``/``risk``.

Свод — «светофор» состояния (``ok``/``warning``/``risk``) **по последнему периоду**:
диагноз ставится по текущему состоянию, а не по истории (история видна в трендах).

Модификации Альтмана Z′ и Z″ считаются по учётным величинам и доступны всегда. Классическая
пятифакторная модель требует **рыночной капитализации** — величины не учётной: она есть
только у публичной компании. Поэтому классическая модель считается **только когда
капитализация введена** (строка-расшифровка ``M_MARKET_CAP``): её отсутствие — не пробел
во вводе, а факт о субъекте, и подставлять вместо неё балансовый капитал нельзя — это дало
бы другую модель под именем классической.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import RatioThreshold
from .result import AuditResult, RatioSeries

# Зоны скоринга и статусы показателей.
SAFE, GREY, DISTRESS = "safe", "grey", "distress"
GOOD, WARN, RISK = "good", "warn", "risk"


@dataclass
class ScoreModel:
    """Скоринговая модель: балл и зона по периодам (None — недостаточно данных)."""

    id: str
    name: str
    values: RatioSeries = field(default_factory=list)
    zones: list[Optional[str]] = field(default_factory=list)
    note: str = ""


@dataclass
class RatioAssessment:
    """Оценка показателя по нормативам: статус по периодам."""

    group: str
    name: str
    status: list[Optional[str]] = field(default_factory=list)


@dataclass
class Diagnostics:
    """Результат диагностики: скоринги, оценка нормативов и сводный «светофор»."""

    scores: list[ScoreModel] = field(default_factory=list)
    assessments: list[RatioAssessment] = field(default_factory=list)
    light: str = "ok"                  # ok | warning | risk
    summary: str = ""


#: Универсальные пороги (приложение Е): показатель → (направление, край риска, край нормы).
#: ``higher`` — чем больше, тем лучше; ``lower`` — наоборот. Значение между краями = warn.
_THRESHOLDS: dict[str, tuple[str, Decimal, Decimal]] = {
    "Коэффициент текущей ликвидности": ("higher", Decimal("1"), Decimal("1.5")),
    "Коэффициент срочной ликвидности": ("higher", Decimal("0.5"), Decimal("0.8")),
    "Коэффициент абсолютной ликвидности": ("higher", Decimal("0.1"), Decimal("0.2")),
    "Коэффициент автономии": ("higher", Decimal("0.3"), Decimal("0.5")),
    "Суммарные обязательства к активам": ("lower", Decimal("0.7"), Decimal("0.5")),
    "Суммарные обязательства к собств. капиталу": ("lower", Decimal("1"), Decimal("0.7")),
    "Коэффициент покрытия процентов": ("higher", Decimal("1.5"), Decimal("3")),
    "Рентабельность чистой прибыли": ("higher", Decimal("0"), Decimal("0.00000001")),
    "Рентабельность активов (ROA)": ("higher", Decimal("0"), Decimal("0.00000001")),
    "Рентабельность собств. капитала (ROE)": ("higher", Decimal("0"), Decimal("0.00000001")),
}


def _status(name: str, value: Optional[Decimal],
            overrides: dict[str, tuple[str, Decimal, Decimal]] | None = None) -> Optional[str]:
    """Статус показателя по нормативу (None — норматива нет или значение не определено).

    Свой норматив субъекта (``overrides``) имеет приоритет над универсальным.
    """
    rule = (overrides or {}).get(name) or _THRESHOLDS.get(name)
    if rule is None or value is None:
        return None
    direction, risk_edge, good_edge = rule
    if direction == "higher":
        if value < risk_edge:
            return RISK
        return GOOD if value >= good_edge else WARN
    if value > risk_edge:
        return RISK
    return GOOD if value <= good_edge else WARN


def _zone(value: Optional[Decimal], distress_edge: Decimal, safe_edge: Decimal) -> Optional[str]:
    if value is None:
        return None
    if value < distress_edge:
        return DISTRESS
    return SAFE if value > safe_edge else GREY


def _div(a: Decimal, b: Decimal) -> Optional[Decimal]:
    return None if b == 0 else a / b


def build_overrides(thresholds: list[RatioThreshold],
                    warnings: list[str]) -> dict[str, tuple[str, Decimal, Decimal]]:
    """Свои нормативы субъекта → таблица порогов; несогласованные отбрасываются с оговоркой."""
    out: dict[str, tuple[str, Decimal, Decimal]] = {}
    for th in thresholds:
        if not th.ratio:
            continue
        if not th.is_consistent():
            warnings.append(
                f"Свой норматив «{th.ratio}» задан несогласованно (граница риска и границы "
                "нормы противоречат направлению показателя) — применён универсальный порог.")
            continue
        out[th.ratio] = (th.direction, th.risk_edge, th.good_edge)
    return out


def compute_diagnostics(result: AuditResult, factors: dict[str, list[Decimal]],
                        *, has_retained: bool, has_market_cap: bool = False,
                        overrides: dict[str, tuple[str, Decimal, Decimal]] | None = None
                        ) -> Diagnostics:
    """Собрать диагностику по результату анализа и подготовленным факторам.

    ``factors`` — ряды по периодам: ``assets``, ``working_capital``, ``retained``, ``ebit``,
    ``equity``, ``liabilities``, ``revenue_annual``, ``ebit_annual``, ``market_cap``.
    ``has_market_cap`` — введена ли рыночная капитализация (публичная компания): от этого
    зависит, считается ли классическая модель Альтмана.
    """
    n = result.n
    if n == 0:
        return Diagnostics()

    assets = factors["assets"]
    x1 = [_div(factors["working_capital"][t], assets[t]) for t in range(n)]
    x2: RatioSeries = ([_div(factors["retained"][t], assets[t]) for t in range(n)]
                       if has_retained else [None] * n)
    x3 = [_div(factors["ebit_annual"][t], assets[t]) for t in range(n)]
    x4 = [_div(factors["equity"][t], factors["liabilities"][t]) for t in range(n)]
    x5 = [_div(factors["revenue_annual"][t], assets[t]) for t in range(n)]
    # Фактор классической модели: **рыночная** стоимость капитала к учётным обязательствам.
    x4_market: RatioSeries = ([_div(factors["market_cap"][t], factors["liabilities"][t])
                               for t in range(n)] if has_market_cap else [None] * n)

    def combine(weights: list[tuple[list[Optional[Decimal]], str]]) -> RatioSeries:
        out: RatioSeries = []
        for t in range(n):
            acc = Decimal(0)
            ok = True
            for series, w in weights:
                v = series[t]
                if v is None:
                    ok = False
                    break
                acc += Decimal(w) * v
            out.append(acc if ok else None)
        return out

    no_retained = ("" if has_retained else
                   " Не рассчитан: не введена нераспределённая прибыль "
                   "(строка-расшифровка в балансе).")

    # Z′ Альтмана — пятифакторная модификация для непубличных компаний (учётные величины).
    z1 = combine([(x1, "0.717"), (x2, "0.847"), (x3, "3.107"), (x4, "0.420"), (x5, "0.998")])
    # Z″ Альтмана — четырёхфакторная (непроизводственные компании; без фактора выручки).
    z2 = combine([(x1, "6.56"), (x2, "3.26"), (x3, "6.72"), (x4, "1.05")])

    # Двухфакторная модель (−0.3877 − 1.0736·Ктл + 0.0579·доля заёмных) **не включена
    # осознанно**: её максимум при любых допустимых входах равен −0.33 < 0 (граница риска),
    # то есть она структурно не способна подать сигнал — даже для явно неплатёжеспособного
    # предприятия показала бы «низкий риск». Ложное спокойствие хуже отсутствия индикатора.

    scores = [
        ScoreModel(
            id="altman_z_private", name="Z′ Альтмана (непубличные компании)",
            values=z1, zones=[_zone(v, Decimal("1.23"), Decimal("2.9")) for v in z1],
            note=("Пятифакторная модификация по учётным величинам. Зоны: < 1,23 — высокий "
                  "риск; 1,23–2,9 — неопределённость; > 2,9 — устойчивость." + no_retained),
        ),
        ScoreModel(
            id="altman_z_nonmfg", name="Z″ Альтмана (непроизводственные компании)",
            values=z2, zones=[_zone(v, Decimal("1.1"), Decimal("2.6")) for v in z2],
            note=("Четырёхфакторная модификация (без фактора оборачиваемости активов). "
                  "Зоны: < 1,1 — высокий риск; 1,1–2,6 — неопределённость; > 2,6 — "
                  "устойчивость." + no_retained),
        ),
    ]

    # Классическая модель (1968) — только для публичных компаний: её четвёртый фактор
    # берёт **рыночную** стоимость капитала. Без введённой капитализации модель не
    # показывается вовсе: у непубличной компании её нет, и строка «не рассчитана» лишь
    # создавала бы впечатление недостающих данных там, где модель просто неприменима.
    if has_market_cap:
        z0 = combine([(x1, "1.2"), (x2, "1.4"), (x3, "3.3"), (x4_market, "0.6"), (x5, "1.0")])
        scores.insert(0, ScoreModel(
            id="altman_z_public", name="Z Альтмана (публичные компании)",
            values=z0, zones=[_zone(v, Decimal("1.81"), Decimal("2.99")) for v in z0],
            note=("Классическая пятифакторная модель: капитал оценён по рыночной "
                  "капитализации, остальные факторы — учётные. Зоны: < 1,81 — высокий "
                  "риск; 1,81–2,99 — неопределённость; > 2,99 — устойчивость."
                  + no_retained),
        ))

    assessments: list[RatioAssessment] = []
    for group, series in result.ratios.items():
        for name, values in series.items():
            statuses = [_status(name, v, overrides) for v in values]
            if any(s is not None for s in statuses):
                assessments.append(RatioAssessment(group=group, name=name, status=statuses))

    light, summary = _summarize(scores, assessments, n)
    return Diagnostics(scores=scores, assessments=assessments, light=light, summary=summary)


def _summarize(scores: list[ScoreModel], assessments: list[RatioAssessment],
               n: int) -> tuple[str, str]:
    """Сводный «светофор» по **последнему периоду** (текущее состояние)."""
    last = n - 1
    zones = [s.zones[last] for s in scores if s.zones and s.zones[last] is not None]
    statuses = [a.status[last] for a in assessments if a.status and a.status[last] is not None]

    risk_ratios = sum(1 for s in statuses if s == RISK)
    warn_ratios = sum(1 for s in statuses if s == WARN)
    distress = sum(1 for z in zones if z == DISTRESS)
    grey = sum(1 for z in zones if z == GREY)

    if distress or risk_ratios:
        light = RISK
        parts = []
        if distress:
            parts.append(f"моделей в зоне высокого риска: {distress}")
        if risk_ratios:
            parts.append(f"показателей вне норматива: {risk_ratios}")
        summary = "Выявлены признаки финансовой неустойчивости (" + "; ".join(parts) + ")."
    elif grey or warn_ratios:
        light = "warning"
        parts = []
        if grey:
            parts.append(f"моделей в зоне неопределённости: {grey}")
        if warn_ratios:
            parts.append(f"показателей у границы норматива: {warn_ratios}")
        summary = "Состояние приемлемое, есть зоны внимания (" + "; ".join(parts) + ")."
    else:
        light = "ok"
        summary = "Показатели в пределах нормативов, признаков неустойчивости не выявлено."

    if not zones and not statuses:
        return "ok", "Недостаточно данных для диагностики."
    return light, summary
