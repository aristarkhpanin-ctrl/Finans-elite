"""Пакет для проверки методики (пакет L, L6) — собирается из кода.

Бухгалтеру или аудитору, которого просят подтвердить трактовки, нужен не код и не
спецификация, а по каждому пункту: что делает движок, какие есть альтернативы, **сколько
это стоит в числах**, что предлагает платформа, что спрашивают у него — и место для
подписи. Пакет собирается из того же кода, что считает (:func:`methodology_map` и движок
на демонстрационных моделях): числа примеров не набраны руками и не могут разойтись с
расчётом — свежесть файла стережёт тест, как у фикстур зеркал.

Альтернативы считаются **тем же движком** на копии модели с другой настройкой — второй
копии правил здесь нет. Где переключателя нет (вопрос представления, конвенция
коэффициентов), альтернатива выводится из строк того же результата, и так и сказано.
Модели примеров — шаблоны и демо-проекты платформы с выдуманными числами: они показывают
механику трактовки, а не отраслевую норму.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .engine import run
from .methodology import CONFIRMATIONS, RESOLUTIONS, Choice, methodology_map
from .models import ProjectModel
from .models.common import InventoryMethod, VatBasis
from .reports.result import CalcResult
from .review.text import fmt_rub
from .samples import build_sample_project, build_showcase_project
from .templates import INDUSTRY_TEMPLATES, at_current_rates
from .version import ENGINE_VERSION

#: Куда пишется пакет (относительно корня репозитория).
PACKET_PATH = "docs/METHODOLOGY-REVIEW-PACKET.md"

DAYS = Decimal(365)
YEAR = Decimal(12)


@dataclass(frozen=True)
class Example:
    """Пример в числах: на какой модели, варианты и как читать."""

    base: ProjectModel
    model_name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, tuple[str, ...]], ...]
    reading: str


@dataclass(frozen=True)
class Proposal:
    """Что предлагает платформа и что спрашивается у проверяющего."""

    proposal: str
    question: str
    example: Callable[[], Example]


# --- Помощники ---

def _template(key: str) -> ProjectModel:
    build = INDUSTRY_TEMPLATES[key].build
    assert build is not None, f"у шаблона {key} нет модели"
    return at_current_rates(build())


def _variant(model: ProjectModel, change: Callable[[ProjectModel], None]) -> CalcResult:
    """Тот же движок на копии модели с другой настройкой: модель примера не меняется."""
    copy = model.model_copy(deep=True)
    change(copy)
    return run(copy)


def _total(result: CalcResult, statement: str, code: str) -> Decimal:
    return sum(getattr(result, statement).lines.get(code, []), Decimal(0))


def _rub(value: Decimal | None) -> str:
    return "—" if value is None else f"{fmt_rub(value)} ₽"


def _num(value: Decimal | None, places: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{places}f}".replace(".", ",")


def _c12(result: CalcResult, name: str) -> Decimal:
    for detail in result.details:
        if detail.code == "C12":
            for item in detail.items:
                if item.name == name:
                    return sum(item.values, Decimal(0))
    return Decimal(0)


# --- Примеры по пунктам ---

def _example_i24() -> Example:
    base = at_current_rates(build_showcase_project())
    engine = run(base)

    def deductible(m: ProjectModel) -> None:
        for line in m.operating_plan.fixed_costs:
            line.from_profit = False
        for loan in m.financing.loans:
            loan.interest_on_profit = False

    alt = _variant(base, deductible)
    i24 = _total(engine, "income", "I24")
    i27, i28 = _total(engine, "income", "I27"), _total(engine, "income", "I28")
    return Example(
        base=base, model_name="демо-проект платформы «Витрина» (12 месяцев)",
        columns=("I24 за горизонт", "Налог на прибыль I27", "Чистая прибыль I28"),
        rows=(
            ("Как считает движок: невычитаемые расходы в I24, уменьшают I28",
             (_rub(i24), _rub(i27), _rub(i28))),
            ("Вопрос пункта: те же расходы — строкой использования прибыли (P)",
             (f"0 ₽ (в строке P: {_rub(i24)})", _rub(i27), _rub(i28 + i24))),
            ("Для сравнения: те же суммы вычитаемыми",
             (_rub(_total(alt, "income", "I24")), _rub(_total(alt, "income", "I27")),
              _rub(_total(alt, "income", "I28")))),
        ),
        reading="Ответ на вопрос пункта не меняет ни налога, ни денег: меняется строка, в "
                "которой видна сумма, — чистая прибыль или её использование. Третья строка "
                "показывает цену самой невычитаемости: она задана законом, а не трактовкой.",
    )


def _example_vat() -> Example:
    base = _template("farming")
    engine = run(base)

    def payment(m: ProjectModel) -> None:
        m.settings.vat_basis = VatBasis.PAYMENT

    def fast_refund(m: ProjectModel) -> None:
        m.settings.vat_refund_lag_months = 2

    def carry(m: ProjectModel) -> None:
        m.settings.vat_refund = False

    def row(label: str, r: CalcResult) -> tuple[str, tuple[str, ...]]:
        paid = _c12(r, "НДС к уплате")
        refunded = -_c12(r, "Возмещение НДС")
        return label, (_rub(paid), _rub(refunded), _rub(paid - refunded), _rub(r.metrics.npv))

    return Example(
        base=base, model_name="шаблон «Растениеводство» (36 месяцев)",
        columns=("НДС уплачено в бюджет", "Возмещено из бюджета", "Нетто за горизонт", "NPV"),
        rows=(
            row("Как считает движок: по отгрузке, возмещение через 4 мес. после квартала",
                engine),
            row("По оплате (режим модели, расходится с нормой при отсрочках)",
                _variant(base, payment)),
            row("По отгрузке, возмещение через 2 мес. (заявительный порядок, ст. 176.1)",
                _variant(base, fast_refund)),
            row("По отгрузке, излишек переносится в зачёт (п. 1.1 ст. 172)",
                _variant(base, carry)),
        ),
        reading="У вариантов «по отгрузке» нетто за горизонт одно — меняется срок "
                "возмещения, а с ним касса и NPV. Режим «по оплате» оставляет часть НДС на "
                "конец горизонта неуплаченной (B21): это и есть сдвиг, который пункт называет "
                "расхождением с нормой. Срок возмещения — допущение модели: у камеральной "
                "проверки есть срок по закону, но продлённая проверка и отказ бывают.",
    )


def _example_fx() -> Example:
    base = at_current_rates(build_showcase_project())
    engine = run(base)

    def constant(m: ProjectModel) -> None:
        m.environment.fx_rate = [m.environment.fx_open] * m.header.duration_months

    alt = _variant(base, constant)
    return Example(
        base=base, model_name="демо-проект платформы «Витрина» (12 месяцев)",
        columns=("Курсовая разница I25", "Налог на прибыль I27", "NPV"),
        rows=(
            ("Как считает движок: курс по модели, переоценка монетарных статей",
             (_rub(_total(engine, "income", "I25")), _rub(_total(engine, "income", "I27")),
              _rub(engine.metrics.npv))),
            ("Для сравнения: курс постоянный — переоценки нет",
             (_rub(_total(alt, "income", "I25")), _rub(_total(alt, "income", "I27")),
              _rub(alt.metrics.npv))),
        ),
        reading="Переоцениваются долг, деньги и расчёты во второй валюте; запас сырья и "
                "себестоимость остаются по курсу закупки. Постоянный курс меняет и пересчёт "
                "валютной выручки и затрат, поэтому разница в налоге и NPV больше самой "
                "курсовой разницы: переоценка — только строка I25. Вопрос пункта — момент "
                "признания курсовой разницы для налога; переключателя у него нет.",
    )


def _example_investment() -> Example:
    base = _template("saas")
    engine = run(base)

    def off(m: ProjectModel) -> None:
        m.settings.release_working_capital = False

    alt = _variant(base, off)

    def row(label: str, r: CalcResult) -> tuple[str, tuple[str, ...]]:
        release = r.working_capital_release
        closing = _rub(release.total) if release is not None and release.enabled else "нет"
        return label, (_rub(r.metrics.npv), _rub(r.metrics.pv_investments),
                       _num(r.metrics.pi, 2), closing)

    return Example(
        base=base, model_name="шаблон «Сервис по подписке» (48 месяцев)",
        columns=("NPV", "PV инвестиций", "PI", "Закрытие расчётов в последнем месяце"),
        rows=(row("Как считает движок: с закрытием расчётов конца горизонта", engine),
              row("Без закрытия расчётов (переключатель модели)", alt)),
        reading="NPV здесь меняет закрытие расчётов: открытые на конец горизонта долги, "
                "запасы и налоги входят в поток последнего месяца или не входят вовсе — это "
                "конвенция оценки, а не учёт. Разбиение потока на инвестиции и отдачу NPV не "
                "меняет, а PI меняет: его знаменатель — PV инвестиций.",
    )


def _example_auto() -> Example:
    base = _template("logistics")
    engine = run(base)

    def invest(m: ProjectModel) -> None:
        m.financing.auto_financing.invest_surplus = True

    alt = _variant(base, invest)

    def row(label: str, r: CalcResult) -> tuple[str, tuple[str, ...]]:
        return label, (_rub(_total(r, "income", "I18")), _rub(_total(r, "income", "I20")),
                       _rub(r.metrics.npv), _rub(r.metrics.peak_financing_need))

    return Example(
        base=base, model_name="шаблон «Грузоперевозки» (36 месяцев)",
        columns=("Проценты I18", "Доход от размещения I20", "NPV", "Пиковая потребность"),
        rows=(row("Как в шаблоне: автокредит, профицит гасит долг", engine),
              row("Профицит размещается в депозит", alt)),
        reading="Размещение профицита — решение о деньгах, а не о проекте: в поток проекта "
                "оно не входит, а налог с дохода входит (налоги в потоке фактические), "
                "поэтому NPV с размещением ниже. Это способ моделирования, а не учёт.",
    )


def _example_ratios() -> Example:
    base = _template("cafe")
    r = run(base)
    t = 11                                  # конец первого года
    balance, income = r.balance.lines, r.income.lines

    def avg(code: str) -> Decimal:
        return (balance[code][t - 1] + balance[code][t]) / 2

    engine_assets = r.ratios.activity["Оборачиваемость активов"][t]
    end_assets = income["I1"][t] * YEAR / balance["B20"][t]
    engine_payables = r.ratios.activity["Период оборачиваемости кредиторки, дн."][t]
    cogs_payables = DAYS * avg("B23") / (income["I7"][t] * YEAR)
    return Example(
        base=base, model_name="шаблон «Кофейня» (24 месяца), 12-й месяц",
        columns=("Как считает движок", "Альтернатива", "Что меняется"),
        rows=(
            ("Оборачиваемость активов, раз в год",
             (_num(engine_assets, 2), _num(end_assets, 2),
              "средние активы → активы на конец")),
            ("Период оборачиваемости кредиторки, дн.",
             (_num(engine_payables), _num(cogs_payables),
              "«закупки» = материалы I5 → себестоимость I7")),
        ),
        reading="Отчёты от ответа не меняются — меняются коэффициенты. Нормы нет: это "
                "аналитический инструмент, и учебники расходятся; альтернатива посчитана из "
                "строк того же результата, переключателя у неё нет.",
    )


def _example_losses() -> Example:
    base = _template("saas")

    def limit(share: str) -> Callable[[ProjectModel], None]:
        def change(m: ProjectModel) -> None:
            m.settings.loss_carryforward_limit = Decimal(share)
        return change

    def row(label: str, r: CalcResult) -> tuple[str, tuple[str, ...]]:
        i27 = r.income.lines["I27"]
        return label, (_rub(sum(i27[:24], Decimal(0))), _rub(sum(i27, Decimal(0))),
                       _rub(r.metrics.npv))

    return Example(
        base=base, model_name="шаблон «Сервис по подписке» (48 месяцев)",
        columns=("Налог на прибыль за первые 2 года", "За горизонт", "NPV"),
        rows=(row("Как считает движок: не более 50% базы (п. 2.1 ст. 283, по 2030 г.)",
                  run(base)),
              row("Без ограничения (как до 2017 г.)", _variant(base, limit("1"))),
              row("Строже нормы: 30%", _variant(base, limit("0.3")))),
        reading="Налог за горизонт один и тот же — ограничение сдвигает уплату вперёд, а с "
                "ней кассу и NPV. Доля — поле модели: ограничение временное и уже "
                "продлевалось.",
    )


def _example_inventory() -> Example:
    base = at_current_rates(build_sample_project())
    base.settings.inflation_direct = Decimal("0.24")
    engine = run(base)

    def fifo(m: ProjectModel) -> None:
        m.settings.inventory_method = InventoryMethod.FIFO

    alt = _variant(base, fifo)
    gaps = [abs(a - b) for a, b in zip(engine.balance.lines["B5"], alt.balance.lines["B5"],
                                       strict=True)]
    t = max(range(len(gaps)), key=lambda i: gaps[i])

    def row(label: str, r: CalcResult) -> tuple[str, tuple[str, ...]]:
        return label, (_rub(r.balance.lines["B5"][t]), _rub(_total(r, "income", "I28")),
                       _rub(r.metrics.npv))

    return Example(
        base=base,
        model_name="демо-проект платформы «Образец» (12 месяцев) с ростом прямых затрат "
                   "24% в год",
        columns=(f"Запас ГП (B5) на конец {t + 1}-го мес.", "Чистая прибыль I28 за горизонт",
                 "NPV"),
        rows=(row("Как в модели: средняя себестоимость", engine),
              row("ФИФО (переключатель модели)", alt)),
        reading="Метод меняет только распределение стоимости между себестоимостью проданного "
                "и остатком запаса: при росте затрат ФИФО оставляет в запасе дорогие партии. "
                "Запас распродан к концу горизонта — итог тот же. Вопрос пункта о другом: как "
                "делить затраты длительного цикла между НЗП и себестоимостью.",
    )


#: Предложение платформы и вопрос проверяющему — **на каждый пункт карты**: лишний или
#: забытый ключ роняет тест, как и у перечня событий.
PROPOSALS: dict[str, Proposal] = {
    "profit.i24": Proposal(
        proposal="Оставить подачу через I24 → I28: в отчёте о финансовых результатах "
                 "невычитаемые расходы уменьшают чистую прибыль; строки использования "
                 "прибыли (P) остаются за решениями собственников.",
        question="Согласны, что невычитаемые расходы уменьшают чистую прибыль (I28), а не "
                 "показываются использованием прибыли?",
        example=_example_i24),
    "vat.basis": Proposal(
        proposal="Принять предлагаемое основание. Срок возмещения оставить допущением модели "
                 "(по умолчанию 4 месяца после квартала, поле модели).",
        question="Подтверждаете момент признания НДС (наиболее ранняя из дат, НДС с авансов) "
                 "и порядок возмещения излишка? Подходит ли четыре месяца как умолчание?",
        example=_example_vat),
    "fx.revaluation": Proposal(
        proposal="Принять предлагаемое основание: монетарные статьи — на конец месяца, "
                 "немонетарные — по курсу признания; для налога — на последнее число месяца "
                 "и на дату погашения.",
        question="Подтверждаете перечень переоцениваемых статей и момент признания курсовой "
                 "разницы для налога?",
        example=_example_fx),
    "metrics.investment_graph": Proposal(
        proposal="Оставить: инвестиция периода — прирост дефицита над максимумом предыдущих "
                 "периодов; закрытие расчётов — в последнем месяце горизонта, с "
                 "переключателем у модели.",
        question="Приемлема ли эта конвенция для PI и закрытия расчётов — или нужна другая "
                 "(например, инвестициями считать только капитальные вложения)?",
        example=_example_investment),
    "financing.auto": Proposal(
        proposal="Оставить: автокредит покрывает дефицит сверх минимального остатка, профицит "
                 "гасит долг или размещается по выбору; казначейство вне потока проекта, "
                 "налог с дохода — в потоке.",
        question="Приемлемы ли правила автоподбора как допущение плана (это способ "
                 "моделирования, а не учёт)?",
        example=_example_auto),
    "ratios.averaging": Proposal(
        proposal="Оставить: оборачиваемость и рентабельность активов и капитала — на средних "
                 "за период, ликвидность и структура — на конец; «закупки» — материалы I5.",
        question="Согласны с конвенцией усреднения и с материалами I5 как закупками для "
                 "оборачиваемости кредиторки?",
        example=_example_ratios),
    "tax.loss_carryforward": Proposal(
        proposal="Принять предлагаемое основание: календарный год, нарастающая база, перенос "
                 "не более 50% базы по 2030 г., без срока.",
        question="Подтверждаете порядок переноса убытков и упрощения пункта (возврат "
                 "переплаты внутри года, база года старта — с месяца старта)?",
        example=_example_losses),
    "inventory.valuation": Proposal(
        proposal="Оставить выбор метода (средняя / ФИФО) за пользователем; затраты "
                 "длительного цикла копятся в НЗП по запуску и переходят в себестоимость с "
                 "выпуском.",
        question="Приемлемо ли такое распределение затрат длительного цикла между НЗП и "
                 "себестоимостью для финансовой модели?",
        example=_example_inventory),
}


# --- Сборка документа ---

INTRO = """\
Пакет для бухгалтера или аудитора, которого просят подтвердить трактовки расчёта. По
каждому из восьми пунктов: что делает движок, чем переключается, что осталось открытым,
предлагаемое основание, **пример в числах** — тот же движок на модели с другой настройкой,
— предложение платформы, вопрос к вам и место для решения и подписи.

Как пользоваться:

1. Прочитайте пункт и пример. Числа примеров посчитаны движком на демонстрационных
   моделях с выдуманными данными — они показывают механику трактовки, а не норму отрасли.
2. Отметьте решение: согласны или возражаете — и как, по-вашему, должно быть.
3. Подпишите пункт. Подписанный пакет хранится у владельца сервиса.
4. Подтверждение заносится в код (`CONFIRMATIONS` в `backend/calc_core/methodology.py`)
   вместе с **отпечатком вопроса**: изменится вопрос или основание — отпечаток не
   сойдётся, и подтверждение перестанет засчитываться, потому что вы читали другой текст.
5. Версия расчёта станет `1.0`, только когда подтверждены **все** пункты — это проверяет
   тест, а не договорённость.

Подтверждаются **трактовки**, а не допущения конкретной модели: за них отвечает тот, кто
модель заполнял."""

PILOT = """\
Подтверждать трактовки на выдуманных данных нельзя — нужны 2–3 реальных проекта.

**Отбор.** Каждый пункт должен быть задействован хотя бы в одном проекте: НДС с отсрочками
оплаты и авансами (пункт 2), убытки первых лет (7), производство с длительным циклом и
запасами (8), валютные займы или расчёты (3), автоподбор финансирования (5). Подходит
действующий бизнес с отчётностью за прошлый год — его факт и есть эталон.

**Сверка.** Модель проекта заводится в сервисе; бухгалтер считает те же величины своей
методикой (или берёт факт): налог на прибыль по годам, НДС к уплате по кварталам, запасы и
НЗП на конец года, курсовые разницы, проценты. Сравнение — по строкам отчётов сервиса.

**Протокол.** На каждый проект: шифр (название не нужно), сверенные строки, расхождения
больше 1% с причиной. Причина в трактовке — это пункт пакета, и решение по нему пишется
здесь; причина в допущениях модели (цены, объёмы) — к пакету не относится.

**Итог.** Подписанные решения по всем пунктам → запись в `CONFIRMATIONS` → обсуждение
версии `1.0`. Возражение по пункту — не провал пилота: это правка методики со своим
номером версии и ревью эталонных чисел, после которой пункт подтверждается заново."""

RECORD = """\
Подписанное решение по пункту заносит разработчик — правкой кода, с ревью:

```python
# backend/calc_core/methodology.py
CONFIRMATIONS: dict[str, Confirmation] = {
    "vat.basis": Confirmation(
        by="Иванова Анна Андреевна, аттестат аудитора № …",
        on=date(2026, 11, 2),
        basis="Основание проверено: п. 1 ст. 167, п. 1 ст. 172, ст. 176 НК РФ.",
        fingerprint="…",           # отпечаток из пакета, строка «Отпечаток вопроса»
        document="Пакет проверки методики, подписан 02.11.2026, хранится у …"),
}
```

Пока запись есть, а отпечаток с вопросом не сходится, экран «Методика» и документ пишут,
что подтверждение устарело, — а тест падает, требуя пересмотреть запись."""


def _status(choice: Choice) -> str:
    if choice.confirmed and choice.confirmation:
        c = choice.confirmation
        return f"подтверждён: {c.by}, {c.on:%d.%m.%Y}"
    if choice.confirmation_stale:
        return "подтверждение устарело"
    return "не подтверждён"


def _table(columns: tuple[str, ...], rows: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    head = "| Вариант | " + " | ".join(columns) + " |"
    sep = "|---|" + "---|" * len(columns)
    body = ["| " + label + " | " + " | ".join(values) + " |" for label, values in rows]
    return [head, sep, *body]


def _section(choice: Choice, proposal: Proposal, example: Example) -> list[str]:
    lines = [
        f"## Пункт {choice.number}. {choice.title}",
        "",
        f"**Как закрывается:** {RESOLUTIONS[choice.resolution]}. **Методика:** {choice.spec}. "
        f"**Состояние:** {_status(choice)}.",
        "",
        f"**Что делает движок** (на модели примера): {choice.chosen}",
        "",
        "**Чем переключается:** " + (", ".join(f"`{c}`" for c in choice.controls)
                                    if choice.controls else "переключателя нет — трактовка одна."),
        "",
        f"**Открытый вопрос:** {choice.open_question}",
        "",
        "**Предлагаемое основание:** " + (choice.proposed_basis or
                                          "нормы, которая бы решила вопрос, нет — нужно "
                                          "профессиональное суждение."),
        "",
        f"**Пример в числах** — {example.model_name}:",
        "",
        *_table(example.columns, example.rows),
        "",
        f"Как читать: {example.reading}",
        "",
        f"**Предложение платформы:** {proposal.proposal}",
        "",
        f"**Вопрос к вам:** {proposal.question}",
        "",
        "**Решение** (заполняет проверяющий):",
        "",
        "- [ ] Согласен(на) с трактовкой и основанием",
        "- [ ] Возражаю — как должно быть: ______________________________",
        "",
        "Комментарий: ____________________________________________________",
        "",
        "ФИО, квалификация: ______________________ Дата: __________ Подпись: __________",
        "",
        f"Отпечаток вопроса: `{choice.fingerprint}` — переносится в запись о подтверждении.",
        "",
    ]
    return lines


def build_packet() -> str:
    """Собрать пакет целиком. Детерминирован: без дат и случайностей — его свежесть
    сверяет тест с файлом в репозитории."""
    summary: list[tuple[Choice, Example]] = []
    for choice_id, proposal in PROPOSALS.items():
        example = proposal.example()
        # Пункт — с карты **той же модели**, что и числа примера: «что делает движок»
        # и таблица под ним описывают одно и то же.
        report = methodology_map(example.base, run(example.base))
        choice = next(c for c in report.choices if c.id == choice_id)
        summary.append((choice, example))
    # Разделы — в порядке пунктов методики, как в SPEC §22 и на экране «Методика».
    summary.sort(key=lambda pair: pair[0].number)
    judgement = sum(1 for c, _ in summary if c.resolution == "judgement")
    citable = sum(1 for c, _ in summary if c.resolution == "citable")
    presentation = sum(1 for c, _ in summary if c.resolution == "presentation")
    confirmed = sum(1 for c, _ in summary if c.confirmed)
    head = [
        "# Методика расчёта: пакет для проверки",
        "",
        f"> Пакет собран из кода (`backend/calc_core/methodology_packet.py`, движок "
        f"v{ENGINE_VERSION}). Не правьте его руками: `python backend/scripts/"
        "methodology_packet.py` пересобирает файл, а тест сверяет его свежесть с кодом.",
        "",
        INTRO,
        "",
        "## Сводка",
        "",
        f"Пунктов — {len(summary)}: профессионального суждения ждут {judgement}, "
        f"подтверждения нормой — {citable}, вопрос представления — {presentation}. "
        f"Подтверждено действующими записями — {confirmed} из {len(summary)}"
        + (f"; записей в реестре — {len(CONFIRMATIONS)}" if CONFIRMATIONS else "") + ".",
        "",
        "| № | Пункт | Как закрывается | Состояние |",
        "|---|---|---|---|",
        *[f"| {c.number} | {c.title} | {RESOLUTIONS[c.resolution]} | {_status(c)} |"
          for c, _ in summary],
        "",
    ]
    tail = ["## План пилота на реальных проектах", "", PILOT, "",
            "## Как записать подтверждение", "", RECORD, ""]
    sections = [line for c, e in summary for line in _section(c, PROPOSALS[c.id], e)]
    return "\n".join(head + sections + tail).rstrip() + "\n"
