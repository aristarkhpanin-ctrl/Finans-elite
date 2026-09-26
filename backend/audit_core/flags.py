"""Реестр красных флагов (Финанс-Аудит, макет «Экран 9»; методика — SPEC, Приложение И).

Флаг — не находка проверки ввода и не оценка коэффициента. Проверка ввода говорит
«данные противоречивы», норматив — «показатель вне порога». Флаг говорит третье:
**«числа, возможно, приукрашены, и вот на сколько»**. Он существует ради покупателя,
который торгуется, а не ради аналитика, который считает.

Чистые функции над моделью и результатом анализа. **В `AuditResult` не входят и в
golden-снимок не попадают** — как ревью бизнес-плана у первого продукта не входит в
`CalcResult`: находка над результатом не меняет методику расчёта, и новые правила не
должны шевелить эталон чисел.

Денежная мера есть **не у всякого флага**, и это главное в модуле. Отрицательный
капитал или непокрытые проценты не выражаются суммой, которую покупатель вычтет из
цены. Поэтому ``impact`` — ``Decimal | None``, где ``None`` значит «меры нет», а не
ноль, а итог реестра называет и сумму оценённых, и число неоценённых. Подставить
выдуманное число значило бы дать скидку с точностью до рубля там, где основание —
суждение.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .models import AuditSubjectModel
from .obligations import (
    OFF_BALANCE_MATERIAL_SHARE,
    PLEDGE_HEAVY_SHARE,
    ObligationRegister,
    build_obligations,
)
from .result import AuditResult

D = Decimal


@dataclass
class Flag:
    """Красный флаг: что настораживает, в каких периодах и на сколько рублей."""

    code: str
    severity: str                      # risk | warning
    title: str
    detail: str
    periods: list[int] = field(default_factory=list)
    #: Денежная мера флага. ``None`` — её не существует, а не «ноль рублей».
    impact: Optional[Decimal] = None
    evidence: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class FlagRegistry:
    """Реестр флагов с честным итогом.

    ``priced_total`` складывает только те флаги, у которых денежная мера есть.
    ``unpriced`` — сколько флагов в неё не вошло: без этого числа итог выглядел бы
    полной ценой рисков, хотя половина рисков в него не попала.
    """

    flags: list[Flag] = field(default_factory=list)
    priced_total: Decimal = D(0)
    unpriced: int = 0

    @property
    def risks(self) -> int:
        return sum(1 for f in self.flags if f.severity == "risk")


def _line(lines, code: str) -> list[Decimal]:
    for ln in lines:
        if ln.code == code:
            return list(ln.values)
    return []


def _grew(series: list[Decimal], t: int) -> Optional[Decimal]:
    """Темп роста к предыдущему периоду; ``None``, если база непригодна."""
    if t == 0 or t >= len(series):
        return None
    base, cur = series[t - 1], series[t]
    if base <= 0:
        return None
    return (cur - base) / base


def detect_flags(model: AuditSubjectModel, result: AuditResult,
                 obligations: Optional[ObligationRegister] = None) -> FlagRegistry:
    """Красные флаги по введённой отчётности и реестру обязательств.

    Правила опираются на агрегатную отчётность и на то, что введено руками (реестр
    обязательств — SPEC, Приложение Л). 24 процедуры из макета требуют первичных
    документов — выписок, договоров, — которых в модели нет; правило, которому нечего
    читать, не заводится: оно не «пока не реализовано», а не имеет входных данных.

    ``obligations`` — уже посчитанный реестр (чтобы не считать его дважды за запрос);
    не передан — считается здесь.
    """
    n = result.n
    reg = FlagRegistry()
    if n < 1:
        return reg

    rev = _line(result.income, "I_REVENUE")
    cogs = _line(result.income, "I_COGS")
    gross = _line(result.income, "I_GROSS")
    ebit = _line(result.income, "I_EBIT")
    other = _line(result.income, "I_OTHER")
    interest = model.income_row("I_INTEREST")

    recv = model.balance_row("A_RECEIVABLE")
    inv = model.balance_row("A_INVENTORY")
    cash = model.balance_row("A_CASH")
    equity = model.balance_row("P_EQUITY")
    short = model.balance_row("P_SHORT")
    current = _line(result.balance, "A_CURRENT")
    net = _line(result.income, "I_NET")

    last = n - 1
    add = reg.flags.append

    # ── Дебиторка растёт быстрее выручки ─────────────────────────────────────
    # Классический признак продаж «в долг» ради красивой выручки перед продажей.
    # Мера: сколько дебиторки сверх той, что была бы при прежней оборачиваемости.
    for t in range(1, n):
        gr, gv = _grew(recv, t), _grew(rev, t)
        if gr is None or gv is None or gr <= gv or gr - gv < D("0.10"):
            continue
        expected = recv[t - 1] * (rev[t] / rev[t - 1]) if rev[t - 1] > 0 else recv[t - 1]
        add(Flag(
            code="receivables_outpace_revenue", severity="risk",
            title="Дебиторка растёт быстрее выручки",
            detail=(f"В периоде {result.periods[t]} дебиторская задолженность выросла на "
                    f"{gr * 100:.0f}% против {gv * 100:.0f}% у выручки. Часть выручки, "
                    "возможно, продана в долг и ещё не собрана."),
            periods=[t], impact=recv[t] - expected,
            evidence={"receivables_growth": gr, "revenue_growth": gv,
                      "expected_receivables": expected},
        ))

    # ── Запасы растут быстрее себестоимости ──────────────────────────────────
    for t in range(1, n):
        gi, gc = _grew(inv, t), _grew(cogs, t)
        if gi is None or gc is None or gi <= gc or gi - gc < D("0.10"):
            continue
        expected = inv[t - 1] * (cogs[t] / cogs[t - 1]) if cogs[t - 1] > 0 else inv[t - 1]
        add(Flag(
            code="inventory_outpace_cogs", severity="warning",
            title="Запасы растут быстрее себестоимости",
            detail=(f"В периоде {result.periods[t]} запасы выросли на {gi * 100:.0f}% "
                    f"против {gc * 100:.0f}% у себестоимости. Возможен неликвид, "
                    "который придётся уценить."),
            periods=[t], impact=inv[t] - expected,
            evidence={"inventory_growth": gi, "cogs_growth": gc,
                      "expected_inventory": expected},
        ))

    # ── Прибыль есть, а денег нет ────────────────────────────────────────────
    # Денежной меры нет: разрыв между прибылью и деньгами — сигнал, а не сумма скидки.
    #
    # Порог существенности обязателен. Любое предприятие временами вкладывается в
    # оборотку, и деньги проседают при растущей прибыли — само по себе это норма
    # работы, а не приукрашивание. Флагом это становится, когда деньги упали не менее
    # чем на половину заявленной прибыли: тогда прибыль в основном не в деньгах.
    for t in range(1, n):
        drop = cash[t - 1] - cash[t]
        if net[t] > 0 and net[t] >= net[t - 1] and drop >= net[t] / 2:
            add(Flag(
                code="profit_without_cash", severity="risk",
                title="Прибыль растёт, а денег становится меньше",
                detail=(f"В периоде {result.periods[t]} чистая прибыль не снизилась "
                        f"({net[t]}), а денежные средства упали с {cash[t - 1]} до "
                        f"{cash[t]} — на {drop}. Прибыль не превращается в деньги."),
                periods=[t],
                evidence={"net_profit": net[t], "cash_drop": drop},
            ))

    # ── Прибыль держится на прочих доходах ───────────────────────────────────
    # Мера — сами прочие доходы: в следующем году их, скорее всего, не будет.
    if net[last] > 0 and other[last] > 0 and other[last] >= net[last] / 2:
        add(Flag(
            code="other_income_spike", severity="risk",
            title="Прибыль держится на прочих доходах",
            detail=(f"В периоде {result.periods[last]} прочие доходы ({other[last]}) "
                    f"составляют больше половины чистой прибыли ({net[last]}). "
                    "Разовые доходы в следующем периоде могут не повториться."),
            periods=[last], impact=other[last],
            evidence={"other_income": other[last], "net_profit": net[last]},
        ))

    # ── Отрицательный капитал ────────────────────────────────────────────────
    neg = [t for t in range(n) if equity[t] < 0]
    if neg:
        add(Flag(
            code="negative_equity", severity="risk",
            title="Отрицательный собственный капитал",
            detail=("Накопленный убыток превысил вложения собственников: "
                    + ", ".join(f"{result.periods[t]} — {equity[t]}" for t in neg)
                    + ". Формально предприятие принадлежит кредиторам."),
            periods=neg, evidence={"min_equity": min(equity[t] for t in neg)},
        ))

    # ── Проценты не покрыты операционной прибылью ────────────────────────────
    uncovered = [t for t in range(n) if interest[t] > 0 and ebit[t] < interest[t]]
    if uncovered:
        add(Flag(
            code="interest_not_covered", severity="risk",
            title="Операционной прибыли не хватает на проценты",
            detail=("Долг обслуживается не из операций: "
                    + ", ".join(f"{result.periods[t]}: EBIT {ebit[t]} против процентов "
                                f"{interest[t]}" for t in uncovered) + "."),
            periods=uncovered,
            evidence={"worst_gap": min(ebit[t] - interest[t] for t in uncovered)},
        ))

    # ── Краткосрочный долг выше оборотных активов ────────────────────────────
    if current and short[last] > current[last]:
        add(Flag(
            code="short_debt_over_current", severity="warning",
            title="Краткосрочные обязательства выше оборотных активов",
            detail=(f"На {result.periods[last]} краткосрочные обязательства "
                    f"({short[last]}) превышают оборотные активы ({current[last]}): "
                    "рассчитаться по текущим долгам нечем без продажи внеоборотных."),
            periods=[last],
            evidence={"gap": short[last] - current[last]},
        ))

    # ── Выручка растёт, а маржа падает ───────────────────────────────────────
    for t in range(1, n):
        if rev[t - 1] <= 0 or rev[t] <= rev[t - 1]:
            continue
        was, now = gross[t - 1] / rev[t - 1], gross[t] / rev[t]
        if now < was - D("0.02"):
            add(Flag(
                code="margin_down_on_growth", severity="warning",
                title="Выручка растёт, валовая маржа падает",
                detail=(f"В периоде {result.periods[t]} выручка выросла, а валовая "
                        f"рентабельность снизилась с {was * 100:.1f}% до {now * 100:.1f}%. "
                        "Рост куплен ценой."),
                periods=[t],
                evidence={"margin_was": was, "margin_now": now},
            ))

    # ── Реестр обязательств (SPEC, Приложение Л.4) ───────────────────────────
    # Пустой реестр не даёт ни одного флага: обязательства не выводятся из отчётности,
    # и молчание реестра — это «не заполнено», а не «обязательств нет».
    reg_ob = obligations if obligations is not None else build_obligations(model, result)
    if reg_ob.has_rows:
        breached = [r for r in reg_ob.rows if r.covenant and r.covenant_status == "breached"]
        if breached:
            add(Flag(
                code="covenant_breached", severity="risk",
                title="Нарушены ковенанты по кредитам",
                detail=("Кредитор вправе потребовать досрочного погашения: "
                        + "; ".join(f"{r.creditor} — «{r.covenant}»" for r in breached)
                        + ". Такой долг перестаёт быть долгосрочным."),
                periods=[last],
                # Мера — весь остаток по нарушенным договорам: истребован может быть он весь.
                impact=sum((r.amount for r in breached), D(0)),
                evidence={"breached_debt": sum((r.amount for r in breached), D(0)),
                          "covenants_breached": D(len(breached))},
            ))

        if reg_ob.off_balance > 0:
            eq = equity[last]
            material = eq <= 0 or reg_ob.off_balance >= eq * OFF_BALANCE_MATERIAL_SHARE
            if material:
                why = ("у предприятия отрицательный капитал, поэтому существенно любое"
                       if eq <= 0 else
                       f"это больше половины собственного капитала ({eq})")
                add(Flag(
                    code="off_balance_material", severity="risk",
                    title="Существенные забалансовые обязательства",
                    detail=(f"Условные обязательства (поручительства, залоги за третьих "
                            f"лиц) — {reg_ob.off_balance}: {why}. В балансе их нет, но "
                            "они станут долгом покупателя, если основной должник "
                            "перестанет платить."),
                    periods=[last], impact=reg_ob.off_balance,
                    evidence={"off_balance": reg_ob.off_balance, "equity": eq},
                ))

        if reg_ob.pledged_share is not None and reg_ob.pledged_share >= PLEDGE_HEAVY_SHARE:
            # Денежной меры нет: залог не уменьшает стоимость активов, он лишает
            # свободы ими распорядиться. Сумма скидки отсюда не выводится.
            add(Flag(
                code="pledged_most_assets", severity="warning",
                title="Активы заложены почти целиком",
                detail=(f"Под залогом {reg_ob.pledged_share * 100:.0f}% активов "
                        f"({reg_ob.pledged_total}). Свободных от обременения активов "
                        f"осталось на {reg_ob.free_assets} — в этих пределах покупатель "
                        "сможет привлечь новое финансирование без согласия кредиторов."),
                periods=[last],
                evidence={"pledged": reg_ob.pledged_total,
                          "free_assets": reg_ob.free_assets or D(0)},
            ))

        if reg_ob.balance_debt > 0 and not reg_ob.reconciled:
            more = reg_ob.discrepancy > 0
            add(Flag(
                code="debt_not_reconciled", severity="warning",
                title="Реестр обязательств расходится с балансом",
                detail=(f"В балансе долга {reg_ob.reported_debt}, в реестре — "
                        f"{reg_ob.balance_debt}. "
                        + ("Часть долга не названа: неизвестно, кому она и на каких "
                           "условиях." if more else
                           "Реестр шире баланса: либо в него попало условное "
                           "обязательство, либо отчётность неполна.")),
                periods=[last], impact=abs(reg_ob.discrepancy),
                evidence={"reported_debt": reg_ob.reported_debt,
                          "register_debt": reg_ob.balance_debt,
                          "discrepancy": reg_ob.discrepancy},
            ))

    # ── Итог: складываем только то, что имеет денежную меру ──────────────────
    for f in reg.flags:
        if f.impact is None:
            reg.unpriced += 1
        else:
            reg.priced_total += f.impact
    order = {"risk": 0, "warning": 1}
    reg.flags.sort(key=lambda f: (order.get(f.severity, 2), f.code))
    return reg
