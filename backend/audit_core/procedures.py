"""Чек-лист процедур (Финанс-Аудит, «Экран 21»; методика — SPEC, Приложение М).

Покупатель платит не за отчёт, а за уверенность, что проверено всё, что можно было
проверить. Чек-лист отвечает на два вопроса: что проверено и — важнее — **что не
проверено и почему**.

Три решения задают модуль.

**Исполнитель назван у каждой процедуры.** ``system`` — процедуру выполняет правило
платформы над введёнными данными; ``analyst`` — ей нужны первичные документы (выписки,
картотека судов, реестр ФНП, договоры), которых в модели нет вовсе. Макет подписывает
«базовая · автоматически» под сверкой с банковской выпиской; так подписать нельзя:
платформа не выполняет того, чего не читает.

**Статус системной процедуры выводится, а не ставится.** Он берётся из фактического
прогона: ``pass`` (правило отработало и молчит), ``finding`` (нашло), ``no_data``
(входных данных нет — правило **не считалось**). ``no_data`` не «пройдено»: покрытие
процентов при незаполненной строке процентов не проверено, а не благополучно.

**Невыполненное собирается в «Границы проверки».** Снятое аналитиком и `no_data`
системного попадают в заключение: покупатель обязан видеть, что не проверялось, —
иначе умолчание читается как проверенное. Поэтому охват без списка границ не выводится.

Чистые функции над моделью и результатами. **В ``AuditResult`` не входят** — как флаги,
нормализация и реестр обязательств: чек-лист читает готовое и ничего не пересчитывает.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

from .earnings import EarningsQuality
from .flags import FlagRegistry
from .input_check import InputIssue
from .models import AuditSubjectModel
from .obligations import ObligationRegister
from .result import AuditResult

D = Decimal

#: Исполнитель процедуры.
SYSTEM = "system"
ANALYST = "analyst"

#: Статусы. Первые три выводятся из прогона, последние три ставит аналитик.
PASS, FINDING, NO_DATA = "pass", "finding", "no_data"
DONE, SKIPPED, PENDING = "done", "skipped", "pending"

#: Незакрытые статусы — то, что попадёт в «Границы проверки».
OPEN_STATUSES = (NO_DATA, SKIPPED, PENDING)


@dataclass(frozen=True)
class Procedure:
    """Процедура каталога: что проверяется, кем и чем именно."""

    code: str
    group: str
    title: str
    source: str                     # system | analyst
    #: Чем процедура выполняется (или почему её не может выполнить платформа).
    method: str


@dataclass
class ProcedureResult:
    """Итог процедуры: статус, пояснение и сработавшие находки."""

    code: str
    group: str
    title: str
    source: str
    method: str
    status: str
    detail: str = ""
    #: Коды находок (флагов / проверки ввода), из-за которых статус — ``finding``.
    findings: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


@dataclass
class ProcedureReport:
    """Чек-лист целиком: итоги по процедурам, охват и границы проверки.

    ``coverage`` — доля закрытых процедур. Она честна только вместе с ``limits``,
    поэтому одно без другого не выводится: «охват 70%» без списка тех 30% читается
    как «почти всё проверено», а не как «треть не проверялась».
    """

    items: list[ProcedureResult] = field(default_factory=list)
    passed: int = 0
    findings: int = 0
    no_data: int = 0
    done: int = 0
    skipped: int = 0
    pending: int = 0
    #: Границы проверки: что не выполнено и почему (в порядке каталога).
    limits: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def closed(self) -> int:
        return self.passed + self.findings + self.done

    @property
    def coverage(self) -> Optional[Decimal]:
        """Доля закрытых процедур; ``None`` — каталога нет (делить не на что)."""
        return D(self.closed) / D(self.total) if self.total else None


# ── Каталог ──────────────────────────────────────────────────────────────────
# Системных процедур ровно столько, сколько у платформы работающих правил. Остальные
# помечены исполнителем «аналитик» — не «пока не реализовано», а другой исполнитель.

G_REPORTING = "Отчётность и её целостность"
G_REVENUE = "Выручка и прибыль"
G_WORKING = "Оборотный капитал"
G_DEBT = "Долг и обязательства"
G_STABILITY = "Устойчивость"
G_PARTIES = "Связанные стороны, налоги и споры"

CATALOG: list[Procedure] = [
    Procedure("balance_identity", G_REPORTING, "Актив равен пассиву во всех периодах",
              SYSTEM, "инвариант ввода"),
    Procedure("reporting_filled", G_REPORTING, "Формы заполнены, пустых периодов нет",
              SYSTEM, "проверка ввода"),
    Procedure("periods_consistent", G_REPORTING, "Периоды различимы и сопоставимы",
              SYSTEM, "проверка подписей и типа периода"),
    Procedure("primary_documents", G_REPORTING,
              "Сверка отчётности с регистрами и первичными документами",
              ANALYST, "нужны учётные регистры — в модель вводятся только агрегаты"),
    Procedure("revenue_bank", G_REVENUE, "Сверка выручки с банковской выпиской",
              ANALYST, "нужна выписка по расчётным счетам"),
    Procedure("margin_dynamics", G_REVENUE, "Валовая маржа при росте выручки",
              SYSTEM, "флаг «выручка растёт, маржа падает»"),
    Procedure("other_income", G_REVENUE, "Разовость прочих доходов",
              SYSTEM, "флаг «прибыль держится на прочих доходах»"),
    Procedure("earnings_normalized", G_REVENUE, "Нормализация прибыли",
              SYSTEM, "корректировки аналитика поверх EBIT/EBITDA"),
    Procedure("customer_concentration", G_REVENUE,
              "Концентрация выручки на ключевых покупателях",
              ANALYST, "нужен разрез выручки по контрагентам — форма агрегатная"),
    Procedure("receivables_dynamics", G_WORKING, "Дебиторка против динамики выручки",
              SYSTEM, "флаг «дебиторка растёт быстрее выручки»"),
    Procedure("inventory_dynamics", G_WORKING, "Запасы против динамики себестоимости",
              SYSTEM, "флаг «запасы растут быстрее себестоимости»"),
    Procedure("profit_to_cash", G_WORKING, "Прибыль превращается в деньги",
              SYSTEM, "флаг «прибыль растёт, а денег меньше»"),
    Procedure("receivables_ageing", G_WORKING, "Дебиторка по срокам возникновения",
              ANALYST, "нужен реестр задолженности — форма агрегатная"),
    Procedure("inventory_count", G_WORKING, "Инвентаризация запасов",
              ANALYST, "нужна инвентаризационная опись"),
    Procedure("debt_register", G_DEBT, "Реестр обязательств сходится с балансом",
              SYSTEM, "сверка реестра с P_LONG + P_SHORT"),
    Procedure("covenants", G_DEBT, "Ковенанты кредитных договоров проверены",
              SYSTEM, "статусы ковенантов реестра"),
    Procedure("pledges", G_DEBT, "Залоговая нагрузка на активы",
              SYSTEM, "доля заложенного в активах"),
    Procedure("off_balance", G_DEBT, "Забалансовые обязательства выявлены",
              SYSTEM, "поручительства и залоги за третьих лиц в реестре"),
    Procedure("interest_coverage", G_DEBT, "Проценты покрыты операционной прибылью",
              SYSTEM, "флаг «операционной прибыли не хватает на проценты»"),
    Procedure("pledge_registry", G_DEBT, "Сверка залогов с реестром уведомлений ФНП",
              ANALYST, "нужен реестр залогов движимого имущества"),
    Procedure("equity_sufficiency", G_STABILITY, "Достаточность собственного капитала",
              SYSTEM, "флаг «отрицательный собственный капитал»"),
    Procedure("short_debt_cover", G_STABILITY,
              "Краткосрочный долг покрыт оборотными активами",
              SYSTEM, "флаг «краткосрочные обязательства выше оборотных активов»"),
    Procedure("ratio_norms", G_STABILITY, "Показатели против нормативов",
              SYSTEM, "оценка коэффициентов по порогам"),
    Procedure("bankruptcy_models", G_STABILITY, "Модели банкротства",
              SYSTEM, "скоринги Альтмана"),
    Procedure("related_parties", G_PARTIES, "Сделки со связанными сторонами",
              ANALYST, "нужны договоры и состав участников"),
    Procedure("intragroup", G_PARTIES, "Внутригрупповые обороты выявлены",
              ANALYST, "платформа исключает их при своде, но не выявляет по одной форме"),
    Procedure("tax_debt", G_PARTIES, "Задолженность перед бюджетом",
              ANALYST, "нужна справка ФНС о состоянии расчётов"),
    Procedure("litigation", G_PARTIES, "Судебные дела и претензии",
              ANALYST, "нужна картотека арбитражных дел"),
]

BY_CODE: dict[str, Procedure] = {p.code: p for p in CATALOG}


@dataclass
class _Ctx:
    """Всё, что чек-лист читает. Ничего не пересчитывается — только смотрится."""

    model: AuditSubjectModel
    result: AuditResult
    flags: FlagRegistry
    issues: tuple[InputIssue, ...]
    obligations: ObligationRegister
    earnings: EarningsQuality

    def flag(self, *codes: str) -> list[str]:
        return [f.code for f in self.flags.flags if f.code in codes]

    def issue(self, *codes: str) -> list[str]:
        return [i.code for i in self.issues if i.code in codes]

    def rows(self, *codes: str) -> bool:
        """Все названные строки баланса/ОФР введены (а не подставлены нулями)."""
        return all(self.model.has_balance_row(c) or self.model.has_income_row(c)
                   for c in codes)


#: Итог системной процедуры: (статус, пояснение, коды находок).
Outcome = tuple[str, str, list[str]]

#: Правило системной процедуры. Возвращает ``None``, если процедуры нет в каталоге.
Rule = Callable[[_Ctx], Outcome]


def _verdict(found: list[str], ok: str, bad: str) -> Outcome:
    return (FINDING, bad, found) if found else (PASS, ok, [])


def _flag_rule(needs: tuple[str, ...], missing: str, ok: str, bad: str,
               *codes: str) -> Rule:
    """Процедура «правило отработало / нашло / читать было нечего».

    ``needs`` — строки, без которых правило не считалось вовсе. Без этой проверки
    молчание правила выглядело бы как благополучие, хотя данных ему не давали.
    """
    def rule(c: _Ctx) -> Outcome:
        if c.result.n == 0 or not c.rows(*needs):
            return NO_DATA, missing, []
        return _verdict(c.flag(*codes), ok, bad)
    return rule


def _two_period(needs: tuple[str, ...], missing: str, ok: str, bad: str,
                *codes: str) -> Rule:
    """То же, но правилу нужна динамика: по одному периоду сравнивать не с чем."""
    inner = _flag_rule(needs, missing, ok, bad, *codes)

    def rule(c: _Ctx) -> Outcome:
        if c.result.n < 2:
            return NO_DATA, "Введён один период — динамику сравнивать не с чем.", []
        return inner(c)
    return rule


def _balance_identity(c: _Ctx) -> Outcome:
    if c.result.n == 0:
        return NO_DATA, "Отчётность не введена.", []
    found = c.issue("balance_gap")
    return _verdict(found, "Актив равен пассиву во всех введённых периодах.",
                    "Баланс не сходится — расхождение показано в проверке ввода.")


def _reporting_filled(c: _Ctx) -> Outcome:
    if c.result.n == 0:
        return NO_DATA, "Отчётность не введена.", []
    found = c.issue("no_income", "no_balance", "empty_period", "negative_line",
                    "cogs_without_revenue", "retained_over_equity")
    return _verdict(found, "Формы заполнены, пустых и противоречивых периодов нет.",
                    "Проверка ввода нашла незаполненное или противоречивое.")


def _periods_consistent(c: _Ctx) -> Outcome:
    if c.result.n == 0:
        return NO_DATA, "Периоды не заданы.", []
    found = c.issue("blank_period_label", "duplicate_period_label")
    return _verdict(found, "Периоды подписаны различимо.",
                    "Подписи периодов пусты или повторяются.")


def _earnings_normalized(c: _Ctx) -> Outcome:
    if c.result.n == 0:
        return NO_DATA, "Отчётность не введена.", []
    if not c.earnings.has_adjustments:
        # Отсутствие поправок — содержательный ответ (Прил. К), а не пропуск работы.
        return PASS, (f"Корректировок нет: {c.earnings.base_code} принят по отчётности."), []
    return PASS, (f"{c.earnings.base_code} нормализован: "
                  f"{len(c.earnings.adjustments)} корректировк(и) с причинами."), []


def _debt_register(c: _Ctx) -> Outcome:
    if not c.obligations.has_rows:
        return NO_DATA, "Реестр обязательств не заполнен — сверять с балансом нечего.", []
    found = c.flag("debt_not_reconciled")
    return _verdict(found, "Реестр обязательств сходится с балансом.",
                    "Реестр расходится с балансом.")


def _covenants(c: _Ctx) -> Outcome:
    reg = c.obligations
    if not reg.has_rows:
        return NO_DATA, "Реестр обязательств не заполнен.", []
    if reg.covenants_breached == 0 and reg.covenants_unknown == 0:
        return PASS, "Ковенанты проверены, нарушений нет.", []
    if reg.covenants_breached:
        return FINDING, (f"Нарушено ковенантов: {reg.covenants_breached}."), \
            c.flag("covenant_breached")
    # Непроверенный ковенант — не благополучие (Прил. Л.3): процедура остаётся открытой.
    return NO_DATA, (f"Не проверено ковенантов: {reg.covenants_unknown}. "
                     "Статус ставит аналитик — условие договора к нашим показателям "
                     "не сводится."), []


def _pledges(c: _Ctx) -> Outcome:
    if c.obligations.pledged_share is None:
        return NO_DATA, "Залоги не введены либо активов нет — доля не считается.", []
    found = c.flag("pledged_most_assets")
    return _verdict(found, "Залоговая нагрузка оценена, активы заложены не целиком.",
                    "Активы заложены почти целиком.")


def _off_balance(c: _Ctx) -> Outcome:
    if not c.obligations.has_rows:
        return NO_DATA, ("Реестр обязательств не заполнен: забалансовые обязательства "
                         "из отчётности не выводятся."), []
    found = c.flag("off_balance_material")
    if found:
        return FINDING, "Забалансовые обязательства существенны.", found
    if c.obligations.off_balance == 0:
        return PASS, "В реестре условных обязательств не заявлено.", []
    return PASS, "Забалансовые обязательства заявлены и несущественны.", []


def _ratio_norms(c: _Ctx) -> Outcome:
    diag = c.result.diagnostics
    if diag is None or not diag.assessments:
        return NO_DATA, "Показатели не посчитаны — нормативы применять не к чему.", []
    bad = [a.name for a in diag.assessments
           if any(s == "risk" for s in a.status)]
    if bad:
        return FINDING, "Вне норматива: " + ", ".join(bad) + ".", []
    return PASS, "Показатели в пределах нормативов.", []


def _bankruptcy_models(c: _Ctx) -> Outcome:
    diag = c.result.diagnostics
    scored = [s for s in (diag.scores if diag else [])
              if any(v is not None for v in s.values)]
    if not scored:
        # Например, не введена нераспределённая прибыль: модель не посчитана,
        # а не «в зелёной зоне».
        return NO_DATA, ("Ни одна модель не посчиталась: не хватает учётных величин "
                         "(нераспределённая прибыль, рыночная капитализация)."), []
    bad = [s.name for s in scored if s.zones and s.zones[-1] == "distress"]
    if bad:
        return FINDING, "Зона риска: " + ", ".join(bad) + ".", []
    return PASS, "Посчитано моделей: " + str(len(scored)) + "; зоны риска нет.", []


RULES: dict[str, Rule] = {
    "balance_identity": _balance_identity,
    "reporting_filled": _reporting_filled,
    "periods_consistent": _periods_consistent,
    "margin_dynamics": _two_period(
        ("I_REVENUE", "I_COGS"), "Выручка или себестоимость не введены.",
        "Маржа при росте выручки не снижается.", "Рост куплен ценой.",
        "margin_down_on_growth"),
    "other_income": _flag_rule(
        ("I_OTHER",), "Прочие доходы не введены — разовость оценивать не на чем.",
        "Прибыль не держится на прочих доходах.",
        "Существенная доля прибыли — прочие доходы.", "other_income_spike"),
    "earnings_normalized": _earnings_normalized,
    "receivables_dynamics": _two_period(
        ("A_RECEIVABLE", "I_REVENUE"), "Дебиторка или выручка не введены.",
        "Дебиторка растёт не быстрее выручки.",
        "Дебиторка обгоняет выручку.", "receivables_outpace_revenue"),
    "inventory_dynamics": _two_period(
        ("A_INVENTORY", "I_COGS"), "Запасы или себестоимость не введены.",
        "Запасы растут не быстрее себестоимости.",
        "Запасы обгоняют себестоимость.", "inventory_outpace_cogs"),
    "profit_to_cash": _two_period(
        ("A_CASH",), "Денежные средства не введены.",
        "Прибыль подкреплена деньгами.",
        "Прибыль не превращается в деньги.", "profit_without_cash"),
    "debt_register": _debt_register,
    "covenants": _covenants,
    "pledges": _pledges,
    "off_balance": _off_balance,
    "interest_coverage": _flag_rule(
        ("I_INTEREST",),
        "Проценты к уплате не введены — покрытие считать не от чего.",
        "Операционной прибыли хватает на проценты.",
        "Проценты не покрыты операционной прибылью.", "interest_not_covered"),
    "equity_sufficiency": _flag_rule(
        ("P_EQUITY",), "Капитал не введён.",
        "Собственный капитал положителен во всех периодах.",
        "Собственный капитал отрицателен.", "negative_equity"),
    "short_debt_cover": _flag_rule(
        ("P_SHORT",), "Краткосрочные обязательства не введены.",
        "Краткосрочный долг покрыт оборотными активами.",
        "Краткосрочный долг выше оборотных активов.", "short_debt_over_current"),
    "ratio_norms": _ratio_norms,
    "bankruptcy_models": _bankruptcy_models,
}


def _mark_outcome(status: str, note: str) -> Outcome:
    """Статус по отметке аналитика.

    Снятие без причины **не применяется**: процедура, снятая молча, неотличима от
    забытой, а в «Границах проверки» она обязана быть названа с объяснением.
    """
    if status == DONE:
        return DONE, note or "Выполнено аналитиком.", []
    if status == SKIPPED:
        if not note.strip():
            return PENDING, ("Снятие без причины не применяется: процедура, снятая "
                             "молча, неотличима от забытой."), []
        return SKIPPED, note, []
    return PENDING, "", []


def _analyst_outcome(model: AuditSubjectModel, code: str) -> Outcome:
    """Статус процедуры каталога, которую ведёт аналитик, — по его отметке."""
    for mark in model.procedure_marks:
        if mark.code == code:
            return _mark_outcome(mark.status, mark.note)
    return PENDING, "", []


def run_procedures(model: AuditSubjectModel, result: AuditResult,
                   flags: FlagRegistry, issues=(), obligations=None,
                   earnings=None) -> ProcedureReport:
    """Чек-лист по каталогу плюс свои процедуры аналитика.

    Ничего не пересчитывает: системные статусы выводятся из уже готовых находок,
    статусы процедур аналитика — из его отметок.
    """
    ctx = _Ctx(model=model, result=result, flags=flags, issues=tuple(issues),
               obligations=obligations if obligations is not None else ObligationRegister(),
               earnings=earnings if earnings is not None else EarningsQuality())
    report = ProcedureReport()

    for proc in CATALOG:
        if proc.source == SYSTEM:
            rule = RULES.get(proc.code)
            status, detail, found = (rule(ctx) if rule else
                                     (NO_DATA, "Правило не задано.", []))
        else:
            status, detail, found = _analyst_outcome(model, proc.code)
        report.items.append(ProcedureResult(
            code=proc.code, group=proc.group, title=proc.title, source=proc.source,
            method=proc.method, status=status, detail=detail, findings=found,
        ))

    # Свои процедуры аналитика: платформа их не выполняет и не притворяется, что может.
    for i, own in enumerate(model.custom_procedures):
        if not own.title.strip():
            continue                  # безымянная процедура не существует
        status, detail, _ = _mark_outcome(own.status, own.note)
        report.items.append(ProcedureResult(
            code=f"custom:{i}", group="Свои процедуры", title=own.title,
            source=ANALYST, method="процедура аналитика — платформа её не выполняет",
            status=status, detail=detail,
        ))

    counters = {PASS: "passed", FINDING: "findings", NO_DATA: "no_data",
                DONE: "done", SKIPPED: "skipped", PENDING: "pending"}
    for item in report.items:
        attr = counters[item.status]
        setattr(report, attr, getattr(report, attr) + 1)
        if item.is_open:
            reason = item.detail or ("Процедуру выполняет аналитик; отметки нет."
                                     if item.source == ANALYST else "Не выполнено.")
            report.limits.append(f"{item.title} — {reason}")
    return report
