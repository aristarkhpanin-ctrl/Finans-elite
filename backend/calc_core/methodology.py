"""Карта методических трактовок расчёта (SPEC §22) — что выбрано в этой модели.

Восемь мест, где общепринятая методика допускает **несколько трактовок**, перечислены в
SPEC §22 с тех пор, как движок начали писать. Каждое реализовано; открыт не расчёт, а
**выбор**, и до его подтверждения на реальных проектах версия ядра держится как `0.x`.

Проблема была не в списке, а в том, что список жил **только в документе**. Бухгалтеру,
которого просят подтвердить трактовку, приходилось читать спецификацию и гадать, какие
пункты вообще задействованы в конкретном проекте: модель без валюты не задаёт вопроса о
курсовой разнице, модель без НДС — вопроса о моменте его признания. Эта карта отвечает на
такой вопрос по конкретной модели: **что выбрано, чем переключается, задействовано ли
здесь вообще и чем это подтверждено в числах**.

**Задействованность доказывается результатом, а не наличием поля.** «Курсовая разница
учитывается» и «курсовая разница в этой модели равна нулю» — разные ответы; первый,
сказанный про вторую модель, отправляет проверяющего искать то, чего нет. Поэтому у
каждого пункта есть ``evidence`` — число из отчётов, — и незадействованный пункт **сам
называет причину**, а не молчит.

**Слой чисто читающий.** Как ревью плана и слои due diligence: чистая функция над моделью
и готовым результатом, в ``CalcResult`` не входит, golden-снимок не двигает. Изменить
методику картой невозможно — она о ней только рассказывает.

**Карта не подтверждает трактовки.** Подтверждение — работа человека с профессиональным
суждением на реальных проектах; карта лишь показывает ему, что именно подтверждать, и
держит список открытых вопросов в одном месте с кодом (расхождение с SPEC §22 ловит тест).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import ProjectModel
from .reports.result import CalcResult


@dataclass(frozen=True)
class Choice:
    """Одна методическая развилка: что выбрано и задействовано ли это здесь."""

    #: Стабильный код (`vat.basis`) — по нему ссылаются интерфейс и документ.
    id: str
    #: Номер пункта SPEC §22 — чтобы читатель нашёл первоисточник, а не поверил на слово.
    number: int
    title: str
    #: Раздел методики, где трактовка описана целиком.
    spec: str
    #: Что выбрано **в этой модели** (а не «что бывает»).
    chosen: str
    #: Чем переключается: поля модели. Пусто — переключателя нет, трактовка одна.
    controls: list[str] = field(default_factory=list)
    #: Что осталось несогласованным по этому пункту (SPEC §22, «открыто к сверке»).
    open_question: str = ""
    #: Задействован ли выбор в этой модели — по числам, а не по наличию поля.
    engaged: bool = False
    #: Почему не задействован (пусто, если задействован). Молчание читалось бы как
    #: «всё в порядке», а это другое утверждение.
    silent_because: str = ""
    #: Число из отчётов, которым задействованность доказана.
    evidence: dict = field(default_factory=dict)


@dataclass
class MethodologyMap:
    """Все развилки расчёта разом: сколько из них живут в этой модели."""

    engine_version: str
    choices: list[Choice]
    #: Подтверждены ли трактовки (и потому зафиксирована ли версия ядра). Всегда `False`,
    #: пока подтверждение не сделано человеком: см. :func:`methodology_map`.
    confirmed: bool = False
    #: Почему версия предварительная — текстом, а не молчанием.
    note: str = ""

    @property
    def engaged(self) -> list[Choice]:
        return [c for c in self.choices if c.engaged]


#: Пока трактовки не подтверждены на реальных проектах профессиональным суждением,
#: `engine_version` остаётся `0.x`. Это утверждение о **состоянии работы**, а не о
#: качестве расчёта: числа считаются одинаково и до, и после подтверждения.
PRELIMINARY_NOTE = (
    "Версия расчётного ядра предварительная (0.x): перечисленные трактовки реализованы, "
    "но не подтверждены на реальных проектах профессиональным суждением бухгалтера или "
    "аудитора. Подтверждение — работа человека; платформа за него его не делает."
)


def _nonzero(series: list[Decimal]) -> Decimal:
    """Сумма модулей ряда: «строка вообще двигалась?» одним числом."""
    return sum((abs(v) for v in series), Decimal(0))


def _line(result: CalcResult, statement: str, code: str) -> list[Decimal]:
    return getattr(result, statement).lines.get(code, [])


def methodology_map(model: ProjectModel, result: CalcResult) -> MethodologyMap:
    """Собрать карту трактовок по модели и её посчитанному результату.

    Порядок — как в SPEC §22: читателю карты и читателю методики не приходится
    сопоставлять два разных списка.
    """
    choices = [
        _i24(model, result),
        _vat(model, result),
        _fx(model, result),
        _investment_graph(model, result),
        _auto_financing(model, result),
        _ratios(model, result),
        _loss_carryforward(model, result),
        _inventory(model, result),
    ]
    return MethodologyMap(engine_version=result.engine_version, choices=choices,
                          confirmed=False, note=PRELIMINARY_NOTE)


def _i24(model: ProjectModel, result: CalcResult) -> Choice:
    amount = _nonzero(_line(result, "income", "I24"))
    sources = []
    if any(line.from_profit for line in model.operating_plan.fixed_costs):
        sources.append("издержки с признаком «за счёт прибыли»")
    if any(loan.interest_on_profit for loan in model.financing.loans):
        sources.append("проценты по займам вне вычета")
    if model.settings.cb_refinancing_rate > 0:
        sources.append("сверхнормативные проценты (ставка ЦБ)")
    if any(tax.allocation == "profit" for tax in model.environment.taxes):
        sources.append("настраиваемые налоги за счёт прибыли")
    return Choice(
        id="profit.i24",
        number=1,
        title="Издержки, отнесённые на прибыль (I24)",
        spec="SPEC §12",
        chosen="Невычитаемы: не входят в базу налога (I26), уменьшают чистую прибыль I28 "
               "и наличность; баланс сходится.",
        controls=["operating_plan.fixed_costs[].from_profit",
                  "financing.loans[].interest_on_profit",
                  "settings.cb_refinancing_rate", "environment.taxes[].allocation"],
        open_question="Подача через строки использования прибыли (P) вместо I28; "
                      "частичный учёт «сверх ставки рефинансирования».",
        engaged=amount > 0,
        silent_because="" if amount > 0 else
                       "В модели нет издержек за счёт прибыли: I24 равен нулю во всех периодах.",
        evidence={"i24_total": str(amount), "sources": sources},
    )


def _vat(model: ProjectModel, result: CalcResult) -> Choice:
    basis = str(getattr(model.settings.vat_basis, "value", model.settings.vat_basis))
    rate = model.settings.vat_rate
    # Доказательство — строки **самого НДС**, а не C12: там же налог на прибыль и
    # имущество, и при выключенном НДС непустая C12 читалась бы как «НДС всё-таки есть».
    receivable = _nonzero(_line(result, "balance", "B7"))
    payable = _nonzero(_line(result, "balance", "B21"))
    return Choice(
        id="vat.basis",
        number=2,
        title="Момент признания НДС",
        spec="SPEC §11",
        chosen=("По отгрузке: НДС начисляется в момент реализации."
                if basis == "shipment" else
                "По оплате: НДС признаётся по факту денег; отложенный исходящий → B21, "
                "входной вне зачёта → B7."),
        controls=["settings.vat_rate", "settings.vat_basis", "settings.vat_periodicity"],
        open_question="НДС с авансов и режим возврата переплаты в C12.",
        engaged=rate > 0,
        silent_because="" if rate > 0 else
                       "НДС в модели выключен (ставка 0) — момент признания ни на что не влияет.",
        evidence={"vat_rate": str(rate), "vat_receivable_b7": str(receivable),
                  "vat_payable_b21": str(payable)},
    )


def _fx(model: ProjectModel, result: CalcResult) -> Choice:
    amount = _nonzero(_line(result, "income", "I25"))
    return Choice(
        id="fx.revaluation",
        number=3,
        title="Курсовая разница (I25)",
        spec="SPEC §5",
        chosen="Переоцениваются монетарные статьи, валютные займы, экспортная выручка, "
               "валютные услуги и кредиторка за валютное сырьё. Запас сырья и "
               "себестоимость немонетарны — по курсу закупки, без переоценки.",
        controls=["environment.fx_rate", "company.foreign_monetary",
                  "financing.loans[].foreign", "operating_plan.sales[].foreign",
                  "operating_plan.fixed_costs[].foreign",
                  "operating_plan.direct_costs[].foreign"],
        open_question="Реализационный учёт налога на курсовую разницу.",
        engaged=amount > 0,
        silent_because="" if amount > 0 else
                       "Валютных статей в модели нет: курсовая разница равна нулю.",
        evidence={"i25_total": str(amount)},
    )


def _investment_graph(model: ProjectModel, result: CalcResult) -> Choice:
    metrics = result.metrics
    return Choice(
        id="metrics.investment_graph",
        number=4,
        title="График инвестиций для показателей эффективности",
        spec="SPEC §17",
        chosen="Инвестиция периода — прирост дефицита относительно максимума предыдущих "
               "периодов; PI = 1 + NPV / PV(инвестиций). NPV от разбиения не зависит.",
        controls=["settings.discount_rate_annual"],
        open_question="Точное правило выделения прироста дефицита.",
        engaged=True,
        evidence={"npv": str(metrics.npv), "pv_investments": str(metrics.pv_investments),
                  "peak_financing_need": str(metrics.peak_financing_need)},
    )


def _auto_financing(model: ProjectModel, result: CalcResult) -> Choice:
    auto = model.financing.auto_financing
    return Choice(
        id="financing.auto",
        number=5,
        title="Автоподбор финансирования",
        spec="SPEC §19",
        chosen=("Привлечение покрывает накопленные проценты; внешняя итерация с "
                "демпфированием. Профицит " +
                ("размещается в депозит и изымается раньше привлечения кредита."
                 if auto.invest_surplus else "гасит задолженность, депозит выключен.")),
        controls=["financing.auto_financing.enabled",
                  "financing.auto_financing.annual_rate",
                  "financing.auto_financing.min_balance",
                  "financing.auto_financing.invest_surplus"],
        open_question="Точные правила генерации инструментов и размещения профицита.",
        engaged=auto.enabled,
        silent_because="" if auto.enabled else
                       "Автоподбор выключен: инструменты финансирования заданы вручную.",
        evidence={"min_balance": str(auto.min_balance),
                  "invest_surplus": auto.invest_surplus},
    )


def _ratios(model: ProjectModel, result: CalcResult) -> Choice:
    return Choice(
        id="ratios.averaging",
        number=6,
        title="База коэффициентов: средние за период или на конец",
        spec="SPEC §18",
        chosen="Оборачиваемость и ROA/ROE — на средние за период величины (начало t=0 — "
               "стартовый баланс); ликвидность, структура и «на акцию» — на конец периода.",
        controls=[],
        open_question="Какие именно строки усреднять; что считать «закупками» для "
                      "оборачиваемости кредиторки (сейчас I5).",
        engaged=True,
        evidence={"periods": result.n},
    )


def _loss_carryforward(model: ProjectModel, result: CalcResult) -> Choice:
    carried = _nonzero(_line(result, "income", "I22"))
    benefit = model.settings.profit_tax_benefit_share
    engaged = carried > 0 or benefit > 0
    return Choice(
        id="tax.loss_carryforward",
        number=7,
        title="Перенос убытков и льгота по налогу на прибыль",
        spec="SPEC §11",
        chosen="Последовательный пул убытков уменьшает базу будущих периодов без "
               "ограничения доли; льгота освобождает заданную долю базы.",
        controls=["settings.profit_tax_rate", "settings.profit_tax_benefit_share"],
        open_question="Ограничение переноса (≤50% базы, срок) и стартовый налоговый убыток.",
        engaged=engaged,
        silent_because="" if engaged else
                       "Убытков к переносу нет и льгота не задана: база налога считается "
                       "прибылью периода.",
        evidence={"i22_total": str(carried), "benefit_share": str(benefit)},
    )


def _inventory(model: ProjectModel, result: CalcResult) -> Choice:
    method = str(getattr(model.settings.inventory_method,
                         "value", model.settings.inventory_method))
    finished = _nonzero(_line(result, "balance", "B5"))
    wip = _nonzero(_line(result, "balance", "B4"))
    cycle = model.settings.production_cycle_months
    engaged = finished > 0 or wip > 0
    return Choice(
        id="inventory.valuation",
        number=8,
        title="Оценка запасов готовой продукции и НЗП",
        spec="SPEC §6",
        chosen=("Готовая продукция — по средней себестоимости."
                if method == "average" else
                "Готовая продукция — ФИФО.") +
               (f" НЗП копится по циклу производства {cycle} мес."
                if cycle else " Цикл производства не задан — НЗП не образуется."),
        controls=["settings.inventory_method", "settings.production_cycle_months"],
        open_question="Распределение затрат длительного цикла между НЗП и себестоимостью.",
        engaged=engaged,
        silent_because="" if engaged else
                       "Запасов готовой продукции и НЗП в модели не возникает: "
                       "произведённое продаётся в том же периоде.",
        evidence={"method": method, "finished_goods": str(finished),
                  "work_in_progress": str(wip), "cycle_months": cycle},
    )
