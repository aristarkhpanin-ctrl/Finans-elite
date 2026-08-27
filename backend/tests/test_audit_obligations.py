"""Реестр обязательств и залогов (Финанс-Аудит, «Экран 10»; методика — SPEC, Прил. Л).

Проверяются решения методики, которые легко потерять при следующей правке:

* забалансовое **никогда** не складывается с балансовым (Л.1) — два итога, общей суммы нет;
* расхождение реестра с балансом считается всегда (Л.2), но флагом становится только
  существенное и только у заполненного реестра;
* ковенант — состояние, а не вычисление (Л.3), и ``unknown`` не выдаётся за благополучие;
* график погашений — это долг по годам погашения, а не платежи года: раскладывать
  остаток «равными долями» значило бы выдумать условия договоров.

У каждого нового флага, как и в Приложении И, два теста: срабатывание и тишина.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, build_obligations, detect_flags
from audit_core.models import AuditSubjectModel
from audit_core.samples import build_trading_subject

D = Decimal


def model(obligations=(), **over) -> AuditSubjectModel:
    """Предприятие на 2 года: активы 1120, долг в балансе 520 (200 длинных + 320 коротких)."""
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
        },
        "income": {
            "I_REVENUE": ["1800", "1980"], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"],
        },
        "obligations": list(obligations),
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def credit(amount: str, **over) -> dict:
    row = {"creditor": "Сбербанк", "contract": "КД-4417/24", "kind": "credit",
           "amount": amount, "maturity_year": 2029}
    row.update(over)
    return row


def register(m: AuditSubjectModel):
    return build_obligations(m, analyze(m))


def codes(m: AuditSubjectModel) -> list[str]:
    result = analyze(m)
    return [f.code for f in detect_flags(m, result, build_obligations(m, result)).flags]


def one(m: AuditSubjectModel, code: str):
    result = analyze(m)
    found = [f for f in detect_flags(m, result, build_obligations(m, result)).flags
             if f.code == code]
    assert len(found) == 1, f"ожидался ровно один флаг {code}, получено {len(found)}"
    return found[0]


# ── Л.1. Забалансовое отдельно ───────────────────────────────────────────────

def test_off_balance_not_summed_with_balance_debt():
    """Главное правило модуля: два итога, и общей суммы у них нет.

    Сложить поручительство с кредитами значило бы утверждать, что оно уже наступило.
    """
    reg = register(model([credit("400"),
                          {"creditor": "ООО «Транссиб-Ойл»", "kind": "guarantee",
                           "amount": "180"}]))
    assert reg.balance_debt == D(400)
    assert reg.off_balance == D(180)
    assert not hasattr(reg, "total_debt")     # общего итога не существует — намеренно


def test_off_balance_absent_from_maturity_buckets():
    """Условное обязательство не попадает в график: платить по нему пока нечего."""
    reg = register(model([credit("400", maturity_year=2027),
                          {"kind": "guarantee", "amount": "180", "maturity_year": 2027}]))
    assert [(b.label, b.amount) for b in reg.buckets] == [("2027", D(400))]


# ── Л.2. Сверка с балансом ───────────────────────────────────────────────────

def test_discrepancy_measured_against_reported_debt():
    reg = register(model([credit("400")]))
    assert reg.reported_debt == D(520)        # P_LONG 200 + P_SHORT 320
    assert reg.discrepancy == D(120)
    assert not reg.reconciled


def test_full_register_reconciles():
    reg = register(model([credit("520")]))
    assert reg.discrepancy == D(0)
    assert reg.reconciled


def test_rounding_difference_is_not_a_discrepancy():
    """1% допуска: реестр в тысячах против баланса в рублях — не «долг, который скрыли»."""
    reg = register(model([credit("517")]))
    assert reg.discrepancy == D(3)
    assert reg.reconciled                     # 3 из 520 — округление, а не находка


def test_debt_not_reconciled_fires():
    flag = one(model([credit("400")]), "debt_not_reconciled")
    assert flag.severity == "warning"
    assert flag.impact == D(120)              # мера — величина расхождения
    assert "не названа" in flag.detail


def test_debt_not_reconciled_silent_when_register_matches():
    assert "debt_not_reconciled" not in codes(model([credit("520")]))


def test_empty_register_gives_no_flags():
    """Пустой реестр — «не заполнено», а не «обязательств нет».

    Иначе флаг «реестр расходится с балансом» горел бы у каждого дела, которого
    этот экран ещё не касался, и реестр флагов перестали бы читать.
    """
    reg = register(model())
    assert not reg.has_rows and reg.balance_debt == D(0)
    assert "debt_not_reconciled" not in codes(model())


def test_register_wider_than_balance_says_so():
    """Реестр шире баланса — другая причина, чем «часть долга не названа»."""
    flag = one(model([credit("700")]), "debt_not_reconciled")
    assert flag.impact == D(180)
    assert "Реестр шире баланса" in flag.detail


# ── Л.3. Ковенанты ───────────────────────────────────────────────────────────

def test_covenant_breached_fires_with_outstanding_as_impact():
    flag = one(model([credit("300", covenant="Долг/EBITDA ≤ 2.5×",
                             covenant_status="breached"),
                      credit("220", creditor="Альфа-Банк", covenant="ICR ≥ 3.0",
                             covenant_status="ok")]), "covenant_breached")
    assert flag.severity == "risk"
    assert flag.impact == D(300)              # только нарушенный договор
    assert "Сбербанк" in flag.detail and "Альфа-Банк" not in flag.detail


def test_covenant_ok_is_silent():
    assert "covenant_breached" not in codes(
        model([credit("520", covenant="Долг/EBITDA ≤ 2.5×", covenant_status="ok")]))


def test_unknown_covenant_counted_apart_and_not_flagged():
    """`unknown` — не благополучие и не нарушение: он виден числом, но не флагом.

    Флаг означал бы, что ковенант нарушен, а мы этого не знаем — знаем только, что
    его не проверяли.
    """
    reg = register(model([credit("520", covenant="Долг/EBITDA ≤ 2.5×")]))
    assert reg.covenants_unknown == 1 and reg.covenants_breached == 0
    assert "covenant_breached" not in codes(model([credit("520",
                                                          covenant="Долг/EBITDA ≤ 2.5×")]))


def test_obligation_without_covenant_is_not_unchecked_covenant():
    """Договор без ковенантов не считается «непроверенным ковенантом»."""
    reg = register(model([credit("520")]))
    assert reg.covenants_unknown == 0


# ── Л.4. Забалансовое существенно ────────────────────────────────────────────

def test_off_balance_material_fires_against_equity():
    flag = one(model([credit("520"), {"kind": "guarantee", "amount": "400"}]),
               "off_balance_material")
    assert flag.severity == "risk"
    assert flag.impact == D(400)              # мера — сумма условных обязательств
    assert "600" in flag.detail               # капитал назван


def test_small_off_balance_is_silent():
    assert "off_balance_material" not in codes(
        model([credit("520"), {"kind": "guarantee", "amount": "100"}]))


def test_any_off_balance_is_material_without_equity():
    """При отрицательном капитале «половина капитала» не порог, а бессмыслица."""
    flag = one(model([credit("520"), {"kind": "guarantee", "amount": "1"}],
                     balance={"P_EQUITY": ["500", "-100"]}), "off_balance_material")
    assert "отрицательный капитал" in flag.detail


# ── Л.4. Залоги ──────────────────────────────────────────────────────────────

def test_pledged_share_and_free_assets():
    reg = register(model([credit("520", pledged_amount="840")]))
    assert reg.pledged_total == D(840)
    assert reg.free_assets == D(280)          # активы 1120 − заложено 840
    assert reg.pledged_share == D("0.75")


def test_pledged_most_assets_fires_without_money_measure():
    """Залог не уменьшает стоимость активов — он лишает свободы ими распорядиться.

    Поэтому денежной меры у флага нет: сумма скидки отсюда не выводится.
    """
    flag = one(model([credit("520", pledged_amount="840")]), "pledged_most_assets")
    assert flag.severity == "warning"
    assert flag.impact is None
    assert "280" in flag.detail               # свободные активы названы


def test_light_pledge_is_silent():
    assert "pledged_most_assets" not in codes(model([credit("520", pledged_amount="500")]))


def test_free_assets_unknown_without_assets():
    """Активов нет — «свободных активов ноль» было бы враньём: сравнивать не с чем.

    Доли тоже нет, поэтому флаг «активы заложены целиком» не срабатывает: 50 из нуля
    не «100% активов», а деление, которого не существует.
    """
    empty = model([credit("0", pledged_amount="50")],
                  balance={"A_FIXED": ["0", "0"], "A_INVENTORY": ["0", "0"],
                           "A_RECEIVABLE": ["0", "0"], "A_CASH": ["0", "0"],
                           "P_EQUITY": ["0", "0"], "P_LONG": ["0", "0"],
                           "P_SHORT": ["0", "0"]})
    reg = register(empty)
    assert reg.free_assets is None and reg.pledged_share is None
    assert "pledged_most_assets" not in codes(empty)


# ── График погашений ─────────────────────────────────────────────────────────

def test_buckets_are_debt_by_maturity_year_not_annual_payments():
    """Остаток целиком относится к году погашения.

    График амортизации долга в модель не вводится, и «равные доли по годам» были бы
    выдуманными условиями договора.
    """
    reg = register(model([credit("300", maturity_year=2027),
                          credit("120", creditor="Альфа-Банк", maturity_year=2027),
                          credit("100", creditor="Совкомбанк", maturity_year=2026)]))
    assert [(b.label, b.amount) for b in reg.buckets] == [("2026", D(100)),
                                                          ("2027", D(420))]


def test_on_demand_and_unknown_maturity_are_different_buckets():
    """«По требованию» — факт договора; «срок не указан» — незаполненное поле."""
    reg = register(model([credit("300", maturity_year=2026),
                          credit("120", creditor="Участник", on_demand=True,
                                 maturity_year=None),
                          credit("100", creditor="Иной", maturity_year=None)]))
    assert [(b.label, b.kind) for b in reg.buckets] == [
        ("2026", "year"), ("по требованию", "on_demand"), ("срок не указан", "unknown")]


def test_rate_not_entered_is_not_zero_percent():
    """Беспроцентный займ (0%) и займ без указанной ставки — разные факты."""
    reg = register(model([credit("300"), credit("220", creditor="Участник", rate="0")]))
    assert reg.rows[0].rate is None
    assert reg.rows[1].rate == D(0)


def test_kind_decides_off_balance_not_a_checkbox():
    """Забалансовость — свойство вида: кредит нельзя объявить условным."""
    reg = register(model([credit("100"), {"kind": "pledge_third_party", "amount": "50"}]))
    assert [r.off_balance for r in reg.rows] == [False, True]
    assert reg.rows[1].kind_label == "Залог за третье лицо"


def test_empty_model_gives_empty_register():
    reg = build_obligations(AuditSubjectModel(), analyze(AuditSubjectModel()))
    assert reg.rows == [] and reg.reported_debt == D(0) and reg.free_assets is None


# ── Демо-дело ────────────────────────────────────────────────────────────────

def test_demo_register_reconciles_with_its_own_balance():
    """Демо показывает сошедшийся реестр — иначе экран учил бы мириться с расхождением.

    Тест держит связь двух мест: правка `P_LONG`/`P_SHORT` семпла без правки реестра
    сделает демо-дело примером незаполненного реестра, и это выяснится здесь, а не у
    пользователя, который открыл демо первым делом.
    """
    m = build_trading_subject()
    reg = build_obligations(m, analyze(m))
    assert reg.discrepancy == D(0) and reg.reconciled
    # Забалансовое стоит отдельно и в балансовый итог не попало.
    assert reg.off_balance == D(1500) and reg.balance_debt == D(6300)


def test_demo_register_exercises_every_rule_without_raising_a_flag():
    """Демо обязано показать каждое состояние экрана и при этом остаться «здоровым».

    Реестр, который молчит, потому что пуст, ничего не демонстрирует; реестр, который
    горит флагами, противоречит остальному демо-делу.
    """
    m = build_trading_subject()
    result = analyze(m)
    reg = build_obligations(m, result)
    assert reg.covenants_unknown == 1                    # «не проверен» показан
    assert any(b.kind == "on_demand" for b in reg.buckets)
    assert [r.rate for r in reg.rows if r.creditor == "Займ участника"] == [D(0)]
    assert reg.pledged_share is not None and reg.free_assets is not None
    assert detect_flags(m, result, reg).flags == []
