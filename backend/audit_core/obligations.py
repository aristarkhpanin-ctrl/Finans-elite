"""Реестр обязательств и залогов (Финанс-Аудит, «Экран 10»; методика — SPEC, Прил. Л).

Долг в аналитической форме — две строки-агрегата. Из них не видно ни кому должны, ни
под какой залог, ни что случится при нарушении ковенанта. А сделки чаще разваливаются
именно здесь: поручительство за связанную сторону не стоит в балансе вовсе, но
становится долгом покупателя в тот день, когда связанная сторона перестаёт платить.

Три решения задают модуль.

**Забалансовое не складывается с балансовым (Л.1).** Итогов два — ``balance_debt`` и
``off_balance``, — и они никогда не сводятся в один. Сложить значило бы утверждать, что
условное обязательство уже наступило; спрятать — что его нет. Тот же приём, что с
рыночной капитализацией при своде группы: величина существует, а складывать нельзя.

**Сверка с балансом обязательна (Л.2).** Сумма введённых балансовых обязательств
сравнивается с ``P_LONG + P_SHORT`` последнего периода, и расхождение показывается
всегда: оно означает либо неполный реестр, либо долг, который никто не назвал.

**График погашений — это долг по годам погашения, а не платежи года.** График
амортизации долга в модели не вводится, и раскладывать остаток по годам «равными
долями» значило бы выдумать условия договоров. Поэтому остаток целиком относится к
году погашения: ответ на вопрос «сколько долга упирается в такой-то год», и он так и
подписан.

Чистые функции над моделью и результатом анализа. **В ``AuditResult`` не входят** — как
флаги и нормализация прибыли: реестр ничего не меняет в методике расчёта отчётов.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import AuditSubjectModel, Obligation
from .result import AuditResult

D = Decimal

#: Доля активов под залогом, с которой предприятие считается заложенным целиком.
PLEDGE_HEAVY_SHARE = D("0.70")
#: Доля капитала, с которой условные обязательства существенны.
OFF_BALANCE_MATERIAL_SHARE = D("0.50")
#: Относительная величина расхождения реестра с балансом, ниже которой это округление.
RECONCILE_TOLERANCE = D("0.01")


@dataclass
class ObligationRow:
    """Строка реестра: введённое + то, что из вида обязательства следует."""

    creditor: str
    contract: str
    kind: str
    kind_label: str
    off_balance: bool
    amount: Decimal
    rate: Optional[Decimal]
    maturity: str                      # «2029» | «по требованию» | «срок не указан»
    on_demand: bool
    collateral: str
    pledged_amount: Decimal
    covenant: str
    covenant_status: str               # ok | breached | unknown
    covenant_note: str


@dataclass
class MaturityBucket:
    """Сколько долга упирается в год погашения (не платёж года — см. модуль)."""

    label: str
    amount: Decimal
    #: year — обычный год; on_demand — «по требованию»; unknown — срок не заполнен.
    kind: str = "year"


@dataclass
class ObligationRegister:
    """Реестр с двумя несводимыми итогами и сверкой с балансом.

    ``balance_debt`` и ``off_balance`` намеренно не имеют общей суммы: см. Л.1.
    ``free_assets`` — ``None``, когда активов нет вовсе (сравнивать залог не с чем),
    а не ноль: ноль означал бы «всё заложено».
    """

    rows: list[ObligationRow] = field(default_factory=list)
    balance_debt: Decimal = D(0)
    off_balance: Decimal = D(0)
    #: P_LONG + P_SHORT последнего периода — то, что стоит в отчётности.
    reported_debt: Decimal = D(0)
    #: Отчётность − реестр. Положительное — часть долга не названа в реестре.
    discrepancy: Decimal = D(0)
    buckets: list[MaturityBucket] = field(default_factory=list)
    pledged_total: Decimal = D(0)
    free_assets: Optional[Decimal] = None
    pledged_share: Optional[Decimal] = None
    covenants_breached: int = 0
    covenants_unknown: int = 0

    @property
    def has_rows(self) -> bool:
        return bool(self.rows)

    @property
    def reconciled(self) -> bool:
        """Реестр сходится с балансом (в пределах округления).

        Пустой реестр «сходящимся» не считается: сверять нечего, и утверждать, что
        всё в порядке, нельзя — поэтому смотреть надо на ``has_rows`` вместе с этим.
        """
        if self.reported_debt == 0:
            return self.balance_debt == 0
        return abs(self.discrepancy) <= abs(self.reported_debt) * RECONCILE_TOLERANCE


def _line(lines, code: str) -> list[Decimal]:
    for ln in lines:
        if ln.code == code:
            return list(ln.values)
    return []


def _maturity_label(o: Obligation) -> tuple[str, str]:
    """Подпись срока и вид корзины. «По требованию» ≠ «срок не заполнен»."""
    if o.on_demand:
        return "по требованию", "on_demand"
    if o.maturity_year is None:
        return "срок не указан", "unknown"
    return str(o.maturity_year), "year"


def build_obligations(model: AuditSubjectModel,
                      result: AuditResult) -> ObligationRegister:
    """Реестр обязательств по введённым данным и последнему периоду отчётности.

    Пустой список обязательств даёт пустой реестр: сверка с балансом в нём не
    выполняется — реестра, который мог бы разойтись с отчётностью, ещё нет.
    """
    reg = ObligationRegister()
    n = result.n
    if n:
        last = n - 1
        long_, short = _line(result.balance, "P_LONG"), _line(result.balance, "P_SHORT")
        if long_ and short:
            reg.reported_debt = long_[last] + short[last]
        assets = _line(result.balance, "A_TOTAL")
        total_assets = assets[last] if assets else D(0)
    else:
        total_assets = D(0)

    by_year: dict[str, Decimal] = {}
    order: dict[str, tuple[int, str]] = {}
    for o in model.obligations:
        label, kind = _maturity_label(o)
        row = ObligationRow(
            creditor=o.creditor, contract=o.contract, kind=o.kind,
            kind_label=o.kind_label, off_balance=o.is_off_balance, amount=o.amount,
            rate=o.rate, maturity=label, on_demand=o.on_demand,
            collateral=o.collateral, pledged_amount=o.pledged_amount,
            covenant=o.covenant, covenant_status=o.covenant_status,
            covenant_note=o.covenant_note,
        )
        reg.rows.append(row)
        reg.pledged_total += o.pledged_amount

        # Ковенант считается только там, где он вписан: обязательство без ковенантов —
        # не «непроверенный ковенант», а договор, в котором их нет.
        if o.covenant:
            if o.covenant_status == "breached":
                reg.covenants_breached += 1
            elif o.covenant_status == "unknown":
                # Непроверенный ковенант — не благополучие (Л.3): он считается отдельно.
                reg.covenants_unknown += 1

        if o.is_off_balance:
            # Условное обязательство не попадает ни в балансовый итог, ни в график
            # погашений: платить по нему нечего, пока основной должник платит сам.
            reg.off_balance += o.amount
            continue

        reg.balance_debt += o.amount
        by_year[label] = by_year.get(label, D(0)) + o.amount
        # Годы по возрастанию, затем «по требованию», затем «срок не указан».
        rank = {"year": 0, "on_demand": 1, "unknown": 2}[kind]
        order[label] = (rank, label)

    reg.buckets = [MaturityBucket(label=lbl, amount=by_year[lbl],
                                  kind={0: "year", 1: "on_demand", 2: "unknown"}[
                                      order[lbl][0]])
                   for lbl in sorted(by_year, key=lambda k: order[k])]

    reg.discrepancy = reg.reported_debt - reg.balance_debt
    if total_assets > 0:
        reg.free_assets = total_assets - reg.pledged_total
        reg.pledged_share = reg.pledged_total / total_assets
    return reg
