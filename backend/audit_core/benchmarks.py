"""Свои отраслевые ориентиры организации (SPEC, Приложение Ф).

Макеты трижды обещают сравнение с отраслью, и трижды платформа отказывала: рыночной
статистики сделок у неё нет и взять её неоткуда. Но у фонда есть **своя** история — и
сравнить дело с собственными ориентирами честно, если ни на секунду не выдавать их за
рынок.

Отсюда все правила модуля:

* ориентир **вводится человеком** и всегда подписан источником и датой — «медиана по
  трём сделкам фонда, 09.2026» это утверждение автора, а не факт рынка;
* сравнение идёт **только при совпадении базы**: мультипликатор к EBITDA и к EBIT —
  разные величины, и «4,6× против 6,3×» между ними было бы бессмыслицей;
* отрасль сопоставляется **точным совпадением** после нормализации регистра и пробелов:
  угадывать, что «Перевозки» и «Грузоперевозки» — одно и то же, платформа не вправе;
* оговорка «это ваш ориентир, а не рынок» выводится **всегда**, а не при отклонении.

Слой чистый: читает готовую оценку и список ориентиров, в `AuditResult` не входит.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .earnings import EarningsQuality
from .valuation import Valuation

D = Decimal

#: Метрики, для которых ориентир имеет смысл. Ключ несёт **базу**: сравнивать
#: мультипликатор можно только с ориентиром той же базы.
METRICS: dict[str, str] = {
    "ev_ebitda": "EV / EBITDA",
    "ev_ebit": "EV / EBIT",
    "ev_revenue": "EV / Выручка",
}

#: Какой метрике соответствует база нормализованного показателя дела.
_BASE_METRIC = {"EBITDA": "ev_ebitda", "EBIT": "ev_ebit"}

#: Оговорка, без которой блок читался бы как рыночная статистика.
OWN_DATA = ("Это ориентир вашей организации, а не рынок: платформа не собирает "
            "статистику сделок и не знает отраслевых медиан.")

NOT_COMPUTED = [
    "Рыночные медианы мультипликаторов — платформа не собирает статистику сделок; "
    "сравнить можно только с ориентирами, которые ведёт сама организация.",
    "Подбор сделок-аналогов — базы сделок у платформы нет.",
]


@dataclass
class Benchmark:
    """Ориентир организации: отрасль, метрика, значение и **кто его назвал**."""

    industry: str
    metric: str
    value: Decimal
    source: str = ""
    updated_at: Optional[date] = None


@dataclass
class BenchmarkView:
    """Сопоставление дела с ориентиром организации.

    ``available=False`` — сравнивать не с чем или не с тем; причина в ``blockers``,
    а не в нулях.
    """

    available: bool = False
    blockers: list[str] = field(default_factory=list)
    industry: str = ""
    metric: str = ""
    metric_label: str = ""
    benchmark: Optional[Decimal] = None
    case_multiple: Optional[Decimal] = None
    #: Отклонение дела от ориентира в долях: (дело − ориентир) / ориентир.
    deviation: Optional[Decimal] = None
    source: str = ""
    updated_at: Optional[date] = None
    caveats: list[str] = field(default_factory=lambda: [OWN_DATA])
    not_computed: list[str] = field(default_factory=lambda: list(NOT_COMPUTED))


def _key(industry: str) -> str:
    """Отрасль для сопоставления: регистр и лишние пробелы не считаются различием."""
    return " ".join(industry.split()).casefold()


def compare_to_benchmark(valuation: Valuation, earnings: EarningsQuality,
                         benchmarks: list[Benchmark], industry: str) -> BenchmarkView:
    """Сопоставить мультипликатор дела с ориентиром организации по его отрасли."""
    view = BenchmarkView(industry=industry)

    if not benchmarks:
        view.blockers.append(
            "Ориентиры организации не заведены: сравнивать не с чем. Их ведут в разделе "
            "«Участники и тариф» — платформа своих отраслевых чисел не имеет.")
        return view
    if not industry.strip():
        view.blockers.append("У дела не указана отрасль — ориентир не с чем сопоставить.")
        return view
    if valuation.implied_multiple is None:
        view.blockers.append(
            "Мультипликатор дела не посчитан: без оценки сравнивать нечего.")
        return view

    metric = _BASE_METRIC.get(earnings.base_code)
    if metric is None:
        view.blockers.append(
            f"Для базы «{earnings.base_code}» ориентир не предусмотрен.")
        return view

    found = [b for b in benchmarks
             if _key(b.industry) == _key(industry) and b.metric == metric]
    if not found:
        # Отрасль есть, ориентира по ней нет — это разные причины, и вторая
        # называется отдельно: иначе пользователь ищет ошибку в отрасли дела.
        same_industry = [b for b in benchmarks if _key(b.industry) == _key(industry)]
        view.blockers.append(
            f"По отрасли «{industry}» нет ориентира {METRICS[metric]}"
            + (" — заведён ориентир по другой базе, а базы несопоставимы."
               if same_industry else
               ": ориентира по этой отрасли в организации нет.")
        )
        return view

    # Несколько ориентиров на одну пару «отрасль + метрика» невозможны (уникальность
    # в хранилище), но если пришли — берём последний по дате: он свежее.
    best = sorted(found, key=lambda b: (b.updated_at or date.min))[-1]
    view.available = True
    view.metric, view.metric_label = metric, METRICS[metric]
    view.benchmark, view.case_multiple = best.value, valuation.implied_multiple
    view.source, view.updated_at = best.source, best.updated_at
    if best.value:
        view.deviation = (valuation.implied_multiple - best.value) / best.value
    else:
        # Нулевой ориентир — не «дело дороже в бесконечность раз»: доли нет.
        view.caveats.append("Ориентир равен нулю — отклонение в долях не считается.")
    return view
