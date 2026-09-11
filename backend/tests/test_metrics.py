from decimal import Decimal

from calc_core.metrics import (
    annual_to_monthly,
    has_investment,
    investment_graph,
    irr_annual,
    npv,
    payback_months,
    profitability_index,
)
from calc_core.money import ONE
from calc_core.reports.result import build_investment_metrics


def test_annual_to_monthly_compounds_back():
    m = annual_to_monthly(Decimal("0.1925"))  # ~1.5%/мес
    assert abs((ONE + m) ** 12 - ONE - Decimal("0.1925")) < Decimal("1e-6")


def test_npv_zero_rate_is_sum():
    flow = [Decimal(-100), Decimal(60), Decimal(60)]
    assert npv(flow, Decimal(0)) == Decimal(20)


def test_irr_simple():
    # -100 сейчас, +110 через месяц => месячная ставка 10% => годовая ~213.8%
    flow = [Decimal(-100), Decimal(110)]
    irr = irr_annual(flow)
    assert irr is not None
    expected = (ONE + Decimal("0.10")) ** 12 - ONE
    assert abs(irr - expected) < Decimal("0.01")


def test_irr_none_when_no_sign_change():
    assert irr_annual([Decimal(10), Decimal(20)]) is None


def test_irr_is_none_when_there_was_no_investment():
    """IRR — норма доходности **на вложенное**. Поток, который начинается с прихода
    (действующий бизнес на своём обороте), вложения не содержит, и числа у такой
    доходности нет.

    Найдено на отраслевом шаблоне «магазин у дома» (D4): бисекция возвращала границу
    интервала — «−100% годовых» под прибыльным магазином. Неверное число хуже честного
    «не определена»: его читают.
    """
    profitable_shop = [Decimal(4_265_733), Decimal(-4_742_662)] + [Decimal(1_100_000)] * 22
    assert irr_annual(profitable_shop) is None

    # А поток с вложением на старте по-прежнему считается.
    with_investment = [Decimal(-1000)] + [Decimal(200)] * 12
    assert irr_annual(with_investment) is not None


def test_payback():
    # накопленный поток: -100, -60, -20, +20 → неотрицателен в 4-м периоде (1-индексация)
    assert payback_months([Decimal(-100), Decimal(40), Decimal(40), Decimal(40)]) == 4
    assert payback_months([Decimal(-100), Decimal(10)]) is None


def test_investment_graph_single_outflow():
    # Весь капитал нужен в t0; дальше дефицит не растёт.
    assert investment_graph([Decimal(-100), Decimal(60), Decimal(60)]) == [
        Decimal(100), Decimal(0), Decimal(0),
    ]


def test_investment_graph_deepening_deficit():
    # Дефицит углубляется два периода: 100, затем +50.
    assert investment_graph([Decimal(-100), Decimal(-50), Decimal(200)]) == [
        Decimal(100), Decimal(50), Decimal(0),
    ]


def test_investment_graph_ignores_dip_after_recovery():
    # Ключевое отличие от старого правила: провал −30 после окупаемости НЕ инвестиция.
    assert investment_graph([Decimal(-100), Decimal(200), Decimal(-30), Decimal(50)]) == [
        Decimal(100), Decimal(0), Decimal(0), Decimal(0),
    ]


def test_investment_graph_no_deficit():
    assert investment_graph([Decimal(100), Decimal(50)]) == [Decimal(0), Decimal(0)]


def test_profitability_index_basic():
    # PI = 1 + NPV / PV(инвестиции).
    assert profitability_index(Decimal(20), Decimal(100)) == Decimal("1.2")
    assert profitability_index(Decimal(-50), Decimal(100)) == Decimal("0.5")  # PI<1 ⟺ NPV<0


def test_profitability_index_none_without_investment():
    assert profitability_index(Decimal(20), Decimal(0)) is None


def test_the_whole_return_family_refuses_together():
    """IRR, MIRR, ARR и PI отказываются **одним условием**, а не каждая по-своему.

    До 0.9.43 отказывалась только IRR, и у прибыльного действующего магазина рядом с
    «IRR не определена» стояли «PI 43,9», «ARR 2995%» и «MIRR 182%». Пользователь,
    получивший два противоположных ответа на один вопрос, верит тому, который больше
    нравится, — и это худший из возможных исходов для показателя.
    """
    shop = [Decimal(4_265_733), Decimal(-4_742_662)] + [Decimal(1_100_000)] * 22
    m = build_investment_metrics(shop, annual_to_monthly(Decimal("0.18")))

    assert (m.irr_annual, m.mirr_annual, m.arr_annual, m.pi) == (None, None, None, None)
    # Отказ назван, а не оставлен прочерком: «—» читается как ноль.
    assert m.no_return_metrics_note and "действующий бизнес" in m.no_return_metrics_note
    # NPV и потребность в капитале считаются как обычно — они вложения не требуют.
    assert m.npv > 0 and m.pv_investments > 0


def test_a_project_with_an_investment_keeps_all_four():
    """Тишина правила — половина его смысла: обычный проект показателей не теряет."""
    project = [Decimal(-1000)] + [Decimal(200)] * 24
    m = build_investment_metrics(project, annual_to_monthly(Decimal("0.18")))
    assert None not in (m.irr_annual, m.mirr_annual, m.arr_annual, m.pi)
    assert m.no_return_metrics_note is None


def test_has_investment_looks_at_the_first_non_zero_month():
    """Нули в начале горизонта — не приток: проект, стартующий в третьем месяце, вложение
    содержит, и показателей терять не должен."""
    assert has_investment([Decimal(0), Decimal(0), Decimal(-100), Decimal(300)])
    assert not has_investment([Decimal(0), Decimal(50), Decimal(-100)])
    assert not has_investment([Decimal(0), Decimal(0)])          # потока нет вовсе


def test_pi_without_the_flow_keeps_its_old_contract():
    """Поток — необязательный аргумент: вызов без него проверяет только знаменатель
    (так PI зовут в местах, где чистого потока под рукой нет)."""
    assert profitability_index(Decimal(20), Decimal(100)) == Decimal("1.2")
    assert profitability_index(Decimal(20), Decimal(100), [Decimal(50)]) is None


def test_the_reason_reaches_the_document():
    """Правило дома: пробел называется, а не оставляется прочерком. В бизнес-плане это
    особенно важно — спросить автора документа нельзя."""
    from datetime import date
    from io import BytesIO

    from docx import Document

    from app.docgen import build_business_plan_docx
    from calc_core import run
    from calc_core.review import ReviewContext, run_review
    from calc_core.review.opinion import build_opinion
    from calc_core.templates import INDUSTRY_TEMPLATES

    model = INDUSTRY_TEMPLATES["retail"].build()     # действующий магазин: приток с t=0
    result = run(model)
    assert result.metrics.no_return_metrics_note                      # предпосылка теста
    opinion = build_opinion(run_review(ReviewContext(model=model, result=result)), result)
    doc = Document(BytesIO(build_business_plan_docx(
        model, result, opinion, project_name="Магазин", today=date(2026, 7, 1))))
    assert "действующий бизнес" in "\n".join(p.text for p in doc.paragraphs)
