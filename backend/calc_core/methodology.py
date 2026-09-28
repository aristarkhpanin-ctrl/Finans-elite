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
методику картой невозможно — она о ней только рассказывает. Одно место считает сверх
прочитанного: режим НДС «по оплате» судится пересчётом **копии** модели по норме, потому
что признание по норме в его результат не попадает (:func:`_payment_basis_gap`) — тем же
движком, без второй копии правил.

**Карта не подтверждает трактовки.** Подтверждение — работа человека с профессиональным
суждением на реальных проектах; карта лишь показывает ему, что именно подтверждать, и
держит список открытых вопросов в одном месте с кодом (расхождение с SPEC §22 ловит тест).

**Восемь пунктов весили одинаково — и это была неправда.** «Какие строки усреднять в
коэффициентах» и «начисляется ли НДС с полученного аванса» стояли рядом как равные, хотя
у второго есть норма, а у первого её нет и быть не может. Из-за этого работа человека
выглядела как восемь открытых вопросов вместо трёх, а два пункта прятали в себе не
трактовку, а **расхождение с нормой** (:data:`Choice.divergence`).

Поэтому у каждого пункта есть :data:`Choice.resolution` — **как он закрывается**
(:data:`RESOLUTIONS`). Классифицируется **открытый вопрос**, а не сам выбор: то, что
трактовка переключается полем модели, видно по ``controls`` и вопроса не снимает — у
НДС выбор «по отгрузке / по оплате» есть, а вопрос про авансы остаётся.

**Классификация — предложение, а не подтверждение.** Предлагаемое основание
(``proposed_basis``) написано для того, чтобы человеку осталось прочитать и согласиться
или возразить, а не искать норму заново. Ничего оно не подтверждает: ``confirmed``
по-прежнему ложно, и версия ядра остаётся `0.x` — гейт не ослаблен.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .engine import run
from .models import ProjectModel
from .models.common import VatBasis
from .models.project import LOSS_CARRYFORWARD_NORM
from .reports.result import CalcResult
from .reports.statements import carry_losses, tax_year_offset
from .review.text import fmt_rub

#: Как закрывается **открытый вопрос** пункта. Три состояния, и все три заняты: свободных
#: «на будущее» здесь нет по той же причине, по которой закрыт перечень событий
#: пользования — состояние, которого никто не выставляет, обещает работу, которой не будет.
RESOLUTIONS: dict[str, str] = {
    "citable": "закрывается ссылкой на норму — человеку остаётся прочитать и согласиться",
    "judgement": "требует профессионального суждения: нормы, которая бы решила, нет",
    "presentation": "вопрос представления — числа от ответа не меняются",
}


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
    #: Как закрывается открытый вопрос (ключ :data:`RESOLUTIONS`). Это **предложение**:
    #: классификация никого ни к чему не обязывает и ничего не подтверждает.
    resolution: str = "judgement"
    #: Предлагаемое основание для `citable`: норма и формулировка, чтобы человеку
    #: осталось согласиться или возразить, а не искать её заново. Пусто для остальных.
    proposed_basis: str = ""
    #: Где текущее поведение движка **расходится** с предлагаемым основанием — и что это
    #: меняет в числах. Пусто, если не расходится.
    #:
    #: Отдельное поле, а не строка внутри ``open_question``: «мы ещё не договорились, как
    #: считать» и «мы считаем не так, как требует норма» — разные утверждения, и второе
    #: утонуло бы в первом. Расхождение здесь **называется, а не чинится**: правка меняет
    #: числа и требует своего бампа версии с осознанным ревью golden-диффа.
    divergence: str = ""


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
    #: Что означает разбиение по способу закрытия (и чего оно не означает).
    classification_note: str = ""

    @property
    def engaged(self) -> list[Choice]:
        return [c for c in self.choices if c.engaged]

    @property
    def needs_human(self) -> list[Choice]:
        """Пункты, которые нормой не закрываются: только они и ждут суждения.

        Число, ради которого классификация и затевалась. «Восемь открытых вопросов»
        выглядит как работа, под которую ищут аудитора надолго; сколько их на самом
        деле — видно отсюда.
        """
        return [c for c in self.choices if c.resolution == "judgement"]

    @property
    def divergences(self) -> list[Choice]:
        """Пункты, где движок считает **не так**, как требует предлагаемая норма.

        Это не трактовки: у них есть ответ, и он другой. Едут отдельно от остальных —
        на экран, в документ и в тест, — потому что в общем списке читаются как
        «ещё обсуждается».
        """
        return [c for c in self.choices if c.divergence]


#: Пока трактовки не подтверждены на реальных проектах профессиональным суждением,
#: `engine_version` остаётся `0.x`. Это утверждение о **состоянии работы**, а не о
#: качестве расчёта: числа считаются одинаково и до, и после подтверждения.
PRELIMINARY_NOTE = (
    "Версия расчётного ядра предварительная (0.x): перечисленные трактовки реализованы, "
    "но не подтверждены на реальных проектах профессиональным суждением бухгалтера или "
    "аудитора. Подтверждение — работа человека; платформа за него его не делает."
)

#: Оговорка к классификации. Едет вместе с ней: «закрывается ссылкой на норму» без этой
#: строки читается как «уже закрыто», а это ровно то, чего классификация не делает.
CLASSIFICATION_NOTE = (
    "Разбиение по способу закрытия и предлагаемые основания — **предложение платформы**, "
    "а не подтверждение. Норма названа для того, чтобы её прочитали и согласились или "
    "возразили; пока этого не произошло, пункт остаётся открытым, а версия ядра — "
    "предварительной."
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
                          confirmed=False, note=PRELIMINARY_NOTE,
                          classification_note=CLASSIFICATION_NOTE)


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
        # Вторая половина вопроса — «частичный учёт сверх ставки рефинансирования» —
        # закрыта нормированием процентов (0.9.31) и убрана отсюда: список открытых
        # вопросов, в котором висит сделанное, завышает объём работы человека.
        open_question="Подача невычитаемых издержек через строки использования прибыли (P) "
                      "вместо I28.",
        resolution="presentation",
        engaged=amount > 0,
        silent_because="" if amount > 0 else
                       "В модели нет издержек за счёт прибыли: I24 равен нулю во всех периодах.",
        evidence={"i24_total": str(amount), "sources": sources},
    )


def _vat_paid(result: CalcResult) -> list[Decimal]:
    """НДС в кассе по месяцам — слагаемое C12, сохранённое конвейером (без него — нули)."""
    for detail in result.details:
        if detail.code == "C12":
            for item in detail.items:
                if item.name == "НДС к уплате":
                    return list(item.values)
    return [Decimal(0)] * result.n


def _payment_basis_gap(model: ProjectModel, result: CalcResult) -> Decimal:
    """Насколько режим «по оплате» уводит НДС к уплате от нормы — по числам.

    Норма (п. 1 ст. 167, п. 1 ст. 172) — это режим «по отгрузке» с 0.9.45, поэтому судить
    можно только пересчётом: признание по отгрузке в результат режима «по оплате» не
    попадает. Пересчитывается **копия** модели тем же движком — ни модель, ни результат
    не меняются, второй копии правил здесь нет. Ответ — наибольшее расхождение по месяцам
    накопленного НДС к уплате и балансовых строк НДС (B7, B21): при большом входном
    кредите касса в обоих режимах может быть нулевой, а баланс — разным. Ноль — режим в
    этой модели ничего не сдвигает.
    """
    at_norm = model.model_copy(deep=True)
    at_norm.settings.vat_basis = VatBasis.SHIPMENT
    norm_result = run(at_norm)
    gap, acc = Decimal(0), Decimal(0)
    for a, b in zip(_vat_paid(result), _vat_paid(norm_result), strict=True):
        acc += b - a
        gap = max(gap, abs(acc))
    for code in ("B7", "B21"):
        for a, b in zip(_line(result, "balance", code), _line(norm_result, "balance", code),
                        strict=True):
            gap = max(gap, abs(b - a))
    return gap


def _vat(model: ProjectModel, result: CalcResult) -> Choice:
    basis = str(getattr(model.settings.vat_basis, "value", model.settings.vat_basis))
    rate = model.settings.vat_rate
    # Доказательство — строки **самого НДС**, а не C12: там же налог на прибыль и
    # имущество, и при выключенном НДС непустая C12 читалась бы как «НДС всё-таки есть».
    receivable = _nonzero(_line(result, "balance", "B7"))
    payable = _nonzero(_line(result, "balance", "B21"))
    evidence: dict = {"vat_rate": str(rate), "vat_receivable_b7": str(receivable),
                      "vat_payable_b21": str(payable)}
    # НДС с полученных авансов в режиме «по отгрузке» начисляется с 0.9.45 (G11) — там
    # расхождения больше нет. Режим «по оплате» — упрощение: норма признаёт НДС по
    # наиболее ранней дате, а вычет — по принятию на учёт, и где есть отсрочки оплаты,
    # он сдвигает НДС. Называется только там, где сдвиг действительно есть.
    divergence = ""
    if rate > 0 and basis == "payment":
        gap = _payment_basis_gap(model, result)
        if gap > 0:
            evidence["vat_gap_vs_norm_max"] = str(gap)
            divergence = (
                "Режим «по оплате» признаёт НДС по деньгам: исходящий — при получении "
                "оплаты, входной — при оплате поставщику. Норма иначе: база — на наиболее "
                "раннюю из дат отгрузки и оплаты (п. 1 ст. 167 НК РФ), то есть при оплате "
                "после отгрузки — в день отгрузки, а вычет входного — по принятию на учёт, "
                "без оплаты (п. 1 ст. 172). В этой модели есть отсрочки оплаты, и НДС по "
                "месяцам — к уплате или в балансе (B7, B21) — расходится с расчётом по "
                "норме, то есть с режимом «по отгрузке».")
    return Choice(
        id="vat.basis",
        number=2,
        title="Момент признания НДС",
        spec="SPEC §11",
        chosen=("По отгрузке, на наиболее раннюю из дат: НДС начисляется при реализации, а "
                "с полученного аванса — при получении денег и принимается к вычету при "
                "отгрузке; уплаченный НДС с аванса — в B7 до отгрузки."
                if basis == "shipment" else
                "По оплате: НДС признаётся по факту денег; отложенный исходящий → B21, "
                "входной вне зачёта и НДС с полученных авансов → B7."),
        controls=["settings.vat_rate", "settings.vat_basis", "settings.vat_periodicity"],
        open_question="Режим возврата переплаты НДС в C12.",
        resolution="citable",
        proposed_basis="п. 1 ст. 167 НК РФ: момент определения базы — **наиболее ранняя** "
                       "из дат отгрузки и оплаты; с полученного аванса НДС начисляется "
                       "сразу, а при отгрузке принимается к вычету (п. 8 ст. 171, п. 6 "
                       "ст. 172) — так считает режим «по отгрузке» с 0.9.45. Вычет входного "
                       "НДС — по принятию на учёт (п. 1 ст. 172). Возврат переплаты — "
                       "ст. 176 НК РФ.",
        divergence=divergence,
        engaged=rate > 0,
        silent_because="" if rate > 0 else
                       "НДС в модели выключен (ставка 0) — момент признания ни на что не влияет.",
        evidence=evidence,
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
        resolution="citable",
        proposed_basis="ПБУ 3/2006 п. 7: монетарные статьи пересчитываются на отчётную "
                       "дату, немонетарные остаются по курсу признания — выбранный "
                       "перечень этому и соответствует. Момент признания для налога — "
                       "п. 8 ст. 271 и п. 10 ст. 272 НК РФ (на последнее число месяца "
                       "и на дату погашения).",
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
        # Нормы здесь нет и быть не может: это финансовый анализ, а не учёт. Учебники
        # расходятся в том, что считать инвестицией, и спорить с ними бухгалтер не обязан.
        resolution="judgement",
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
        # Тоже не учёт: это способ моделирования. Норма его не задаёт, и «правильного»
        # ответа у неё нет — есть удобный и неудобный.
        resolution="judgement",
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
        # Нормы нет: коэффициенты — аналитический инструмент, и методики расходятся.
        resolution="judgement",
        engaged=True,
        evidence={"periods": result.n},
    )


def _percent(share: Decimal) -> str:
    """Доля словами для текста: 0.5 → «50%», 0.335 → «33,5%»."""
    return format((share * 100).normalize(), "f").replace(".", ",") + "%"


def _limit_words(limit: Decimal) -> str:
    if limit >= 1:
        return "убытки прошлых лет закрывают базу целиком — ограничение снято"
    if limit == 0:
        return "убытки прошлых лет базу не уменьшают — перенос из прошлых лет выключен"
    words = f"убытки прошлых лет уменьшают нарастающую базу не больше чем на {_percent(limit)}"
    if limit < LOSS_CARRYFORWARD_NORM:
        # Не расхождение: норма — потолок, а переносить меньше налогоплательщик вправе.
        words += (f" — строже нормы ({_percent(LOSS_CARRYFORWARD_NORM)}): переносить "
                  "меньше вправе сам налогоплательщик (п. 1 ст. 283)")
    return words


def _loss_carryforward(model: ProjectModel, result: CalcResult) -> Choice:
    settings = model.settings
    i22 = _line(result, "income", "I22")
    carried = _nonzero(i22)
    benefit = settings.profit_tax_benefit_share
    limit = settings.loss_carryforward_limit
    opening = settings.opening_tax_loss
    # «Задействовано» доказывается числом из отчётов: стартовый убыток, который не во что
    # зачесть, отчётов не меняет — но причина молчания обязана это назвать, а не сказать
    # «убытка нет».
    engaged = carried > 0 or benefit > 0
    # Расхождения судятся по числам, а не по полям: та же функция переноса (одна дверь,
    # второй копии правила здесь нет) пересчитывается на тех же базах иначе, и
    # предупреждение появляется, только если числа действительно другие.
    bases = [a + b for a, b in zip(_line(result, "income", "I23"),
                                   _line(result, "income", "I25"), strict=True)]
    offset = tax_year_offset(model.header.start_date)
    evidence: dict = {"i22_total": str(carried), "benefit_share": str(benefit),
                      "loss_limit": str(limit), "opening_tax_loss": str(opening)}
    parts = []
    if limit > LOSS_CARRYFORWARD_NORM:
        at_norm = carry_losses(bases, LOSS_CARRYFORWARD_NORM, year_offset=offset,
                               opening_loss=opening)
        if at_norm != i22:
            evidence["i22_at_norm_total"] = str(_nonzero(at_norm))
            parts.append(
                f"Доля переноса — {_percent(limit)}, выше нормы "
                f"{_percent(LOSS_CARRYFORWARD_NORM)} (п. 2.1 ст. 283 НК РФ), и в этой модели "
                "это сказывается: убытки прошлых лет закрыли больше, чем разрешено, налог "
                "первых прибыльных лет занижен, а уплата сдвинута вперёд. Ставить долю выше "
                "нормы оправдано, только если ограничение к базе не применяется (часть "
                "пониженных ставок) или срок его действия истёк.")
    return Choice(
        id="tax.loss_carryforward",
        number=7,
        title="Перенос убытков и льгота по налогу на прибыль",
        spec="SPEC §11",
        chosen="Налоговый год — календарный (ст. 285 НК РФ): и перенос убытков, и кварталы "
               "уплаты считаются от 1 января. База — нарастающим итогом года (ст. 274, "
               "286): убыток месяца уменьшает базу своего года, в том числе после прибыли — "
               "тогда начисленный налог сторнируется; месячные I22, I26, I27 — приросты "
               "годовых величин. Непокрытый убыток года в декабре уходит в перенос: "
               f"{_limit_words(limit)}; неиспользованный остаток переносится бессрочно. "
               "Налоговый убыток прошлых лет на дату старта (поле модели) входит в тот "
               "же пул. Льгота освобождает заданную долю базы.",
        controls=["settings.profit_tax_rate", "settings.profit_tax_benefit_share",
                  "settings.loss_carryforward_limit"],
        open_question="Переплата авансов внутри года возвращается в периоде её "
                      "возникновения — зачёт в счёт будущих платежей не моделируется. "
                      "Сроки уплаты — по ст. 287 (с 0.9.51): налог, срок которого "
                      "наступает после горизонта (за год — в марте), остаётся задолженностью "
                      "B21 и в поток проекта не входит, как дебиторка и кредиторка конца "
                      "горизонта; на коротком горизонте это заметно поднимает NPV. База "
                      "года старта начинается с месяца старта: результат "
                      "того же года до старта в модель не входит. Стартовый убыток — "
                      "налоговый атрибут, отложенный налоговый актив (ПБУ 18/02) не "
                      "отражается.",
        resolution="citable",
        proposed_basis="п. 2.1 ст. 283 НК РФ: в периоды с 2017 по 2030 г. база уменьшается "
                       "на убытки прошлых лет **не более чем на 50%**; к базе по ряду "
                       "пониженных ставок ограничение не применяется. Срок переноса не "
                       "ограничен с 2017 г. (п. 2 ст. 283). Налоговый период — календарный "
                       "год (ст. 285), база — нарастающим итогом с его начала (ст. 274, "
                       "286). Ограничение временное и уже продлевалось, поэтому доля — "
                       "поле модели, а не константа расчёта.",
        divergence=" ".join(parts),
        engaged=engaged,
        silent_because="" if engaged else (
            f"Стартовый налоговый убыток {fmt_rub(opening)} ₽ задан, но зачесть его не во "
            "что: положительной нарастающей базы в горизонте нет."
            if opening > 0 else
            "Убытков прошлых лет нет — ни в горизонте, ни на старте — и льгота не задана: "
            "база налога — нарастающая прибыль года."),
        evidence=evidence,
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
        # ФСБУ 5/2019 задаёт **состав** себестоимости, но не распределение по длительному
        # циклу: это учётная политика предприятия, а не общая норма.
        resolution="judgement",
        engaged=engaged,
        silent_because="" if engaged else
                       "Запасов готовой продукции и НЗП в модели не возникает: "
                       "произведённое продаётся в том же периоде.",
        evidence={"method": method, "finished_goods": str(finished),
                  "work_in_progress": str(wip), "cycle_months": cycle},
    )
