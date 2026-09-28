"""НДС с полученных авансов в режиме «по отгрузке» (пакет G, G11; SPEC §11, §22.2).

П. 1 ст. 167 НК РФ: момент определения базы — **наиболее ранняя** из дат отгрузки и
оплаты. С полученного аванса НДС начисляется при получении денег, а при отгрузке
принимается к вычету (п. 8 ст. 171, п. 6 ст. 172). До 0.9.45 в режиме «по отгрузке» НДС
с аванса не начислялся вовсе: уплата сдвигалась на месяц отгрузки, касса в промежутке
была завышена.

Правила, которые здесь проверяются:

* признание месяца = НДС по отгрузке + прирост остатка НДС с авансов на конец месяца;
  остаток — по каждой строке сбыта (тот же ``sales_timing``, что ведёт авансы B24);
* уплаченный НДС с аванса — актив B7 до отгрузки (баланс сходится);
* **не** «максимум накопленного по отгрузке и по оплате», как было записано в плане: при
  смешанных условиях (часть предоплатой, часть с отсрочкой) дебиторка строки гасила бы её
  же аванс, и НДС с аванса снова не начислялся бы;
* модели без остатка авансов — **те же числа**; режим «по оплате» не меняется.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from calc_core import run
from calc_core.engine.vat import output_on_earliest_date
from calc_core.models import (
    Company,
    Financing,
    OperatingPlan,
    Product,
    ProjectHeader,
    ProjectModel,
    ProjectSettings,
    SalesLine,
    StartingBalance,
)
from calc_core.models.common import VatBasis
from calc_core.models.operating import PaymentPart, PaymentTerms
from calc_core.money import quantize

D = Decimal


def _model(payment: PaymentTerms, volume: list[Decimal], *,
           basis: VatBasis = VatBasis.SHIPMENT) -> ProjectModel:
    # Лишний месяц без продаж: НДС платится в месяце, **следующем** за признанием (0.9.51),
    # и признание последнего месяца без него ушло бы за горизонт (см. ``_vat_paid``).
    volume = [*volume, D(0)]
    n = len(volume)
    return ProjectModel(
        header=ProjectHeader(name="vat", start_date=date(2026, 1, 1), duration_months=n),
        settings=ProjectSettings(discount_rate_annual=D(0), profit_tax_rate=D(0),
                                 property_tax_rate=D(0), vat_rate=D("0.20"),
                                 vat_basis=basis),
        company=Company(starting_balance=StartingBalance()),
        operating_plan=OperatingPlan(
            products=[Product(id="p1", name="Товар")],
            sales=[SalesLine(product_id="p1", volume=volume, price=[D(100)] * n,
                             payment=payment)],
        ),
        financing=Financing(common_shares=D(1000)),
    )


def _vat_paid(result) -> list[Decimal]:
    """НДС, **признанный** в каждом месяце: уплата (слагаемое C12, сохранённое конвейером),
    сдвинутая на месяц назад. С 0.9.51 помесячный НДС платится в следующем месяце, а
    правила этого файла — о моменте признания, и ожидания оставлены в его терминах."""
    c12 = next(d for d in result.details if d.code == "C12")
    return list(next(item.values for item in c12.items if item.name == "НДС к уплате")[1:])


def _balanced(result) -> bool:
    return [quantize(v) for v in result.balance["B20"]] == \
        [quantize(v) for v in result.balance["B34"]]


# --- Чистая предоплата ---

PREPAID = PaymentTerms(prepayment_share=D(1), advance_lead_months=1)


def test_vat_on_an_advance_is_due_when_the_money_arrives():
    """Отгрузка во втором месяце (НДС 200), деньги — за месяц до неё."""
    r = run(_model(PREPAID, [D(0), D(10), D(0), D(0)]))
    assert _vat_paid(r) == [D(200), D(0), D(0), D(0)]      # до 0.9.45: [0, 200, 0, 0]
    assert r.balance["B24"][0] == D(1200)                  # аванс с НДС — обязательство
    assert r.balance["B7"][:2] == [D(200), D(0)]           # НДС с аванса — актив до отгрузки
    assert _balanced(r)


def test_for_a_pure_prepayment_both_bases_pay_the_same_month():
    """Весь платёж — предоплатой: «наиболее ранняя дата» — это дата денег, как и в
    режиме «по оплате»."""
    volume = [D(0), D(10), D(5), D(0)]
    shipment = run(_model(PREPAID, volume))
    payment = run(_model(PREPAID, volume, basis=VatBasis.PAYMENT))
    assert _vat_paid(shipment) == _vat_paid(payment)


# --- Смешанные условия: почему не «максимум накопленного» ---

MIXED = PaymentTerms(schedule=[PaymentPart(offset_months=-1, share=D("0.3")),
                               PaymentPart(offset_months=1, share=D("0.7"))])


def test_mixed_terms_tax_the_advance_even_while_the_line_owes_more():
    """Две отгрузки по 1000 (НДС 200): 30% предоплатой за месяц, 70% — через месяц.

    К концу второго месяца отгружена первая партия (НДС 200) и получен аванс за вторую
    (НДС 60): признано 260. Максимум накопленного по отгрузке (200) и по оплате (120) дал
    бы 200 — дебиторка первой партии погасила бы аванс за вторую.
    """
    volume = [D(0), D(10), D(10), D(0)]
    paid = _vat_paid(run(_model(MIXED, volume)))
    assert paid == [D(60), D(200), D(140), D(0)]
    cumulative = [sum(paid[:t + 1]) for t in range(len(paid))]
    assert cumulative[1] == D(260)
    shipped, received = [D(0), D(200), D(400), D(400)], [D(60), D(120), D(260), D(400)]
    assert max(shipped[1], received[1]) == D(200) != cumulative[1]    # ловушка плана


def test_mixed_terms_keep_the_balance():
    for volume in ([D(0), D(10), D(10), D(0)], [D(5), D(0), D(7), D(3), D(0), D(9)]):
        assert _balanced(run(_model(MIXED, volume)))


# --- Эквивалентность: без авансов — те же числа ---

def test_without_advances_recognition_is_the_accrual_itself():
    accrued = [D("12.5"), D(0), D("7.25"), D("3")]
    assert output_on_earliest_date(accrued, [D(0)] * 4) == accrued


def test_same_month_prepayment_leaves_no_advance_and_changes_nothing():
    """Предоплата «в месяце отгрузки» (опережение 0) остатка аванса на конец месяца не
    оставляет: у подписки и аренды в шаблонах именно так, и их числа не меняются."""
    volume = [D(3), D(10), D(0), D(4)]
    same_month = PaymentTerms(prepayment_share=D(1), advance_lead_months=0)
    assert _vat_paid(run(_model(same_month, volume))) == \
        _vat_paid(run(_model(PaymentTerms(), volume)))


def test_the_payment_basis_is_untouched():
    """«По оплате» НДС и так шёл за деньгами — правка его не касается."""
    volume = [D(0), D(10), D(10), D(0)]
    r = run(_model(MIXED, volume, basis=VatBasis.PAYMENT))
    assert _vat_paid(r) == [D(60), D(60), D(140), D(140)]
    assert _balanced(r)
