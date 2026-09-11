"""Тесты экспертного заключения (пакет №5, D0): build_opinion над ревью и результатом."""
from decimal import Decimal

from calc_core import run
from calc_core.reports.lines import (
    BALANCE_LINES,
    CASHFLOW_LINES,
    INCOME_LINES,
    PROFIT_USE_LINES,
)
from calc_core.reports.result import CalcResult, InvestmentMetrics
from calc_core.reports.statements import Statement
from calc_core.review import ReviewContext, run_review
from calc_core.review.opinion import build_opinion, opinion_is_positive
from calc_core.review.types import Finding, ReviewResult
from calc_core.samples import build_sample_project


def _result(n=12, npv="1000000", irr="0.30", pb=6, peak=None) -> CalcResult:
    return CalcResult(
        engine_version="t", n=n,
        income=Statement(INCOME_LINES, n),
        cashflow=Statement(CASHFLOW_LINES, n),
        balance=Statement(BALANCE_LINES, n),
        profit_use=Statement(PROFIT_USE_LINES, n),
        metrics=InvestmentMetrics(
            npv=Decimal(npv),
            irr_annual=Decimal(irr) if irr is not None else None,
            pb_months=pb,
            peak_financing_need=Decimal(peak) if peak is not None else None,
        ),
    )


def _review(light="ok", findings=()) -> ReviewResult:
    counts = {"risk": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] += 1
    return ReviewResult(light=light, counts=counts, findings=list(findings))


def _finding(severity, title="Находка", rec="Рекомендация.") -> Finding:
    return Finding(id=f"t.{severity}", category="viability", severity=severity,
                   title=title, detail="d", recommendation=rec)


def test_opinion_marginal_sample_is_negative():
    """Демо «Мини-производство» маргинально: заключение отрицательное, риски перечислены."""
    model = build_sample_project()
    result = run(model)
    review = run_review(ReviewContext(model=model, result=result))
    opinion = build_opinion(review, result)
    assert "существенные риски" in opinion
    assert "Существенные риски:" in opinion            # блок с находками
    assert "не рекомендуется" in opinion               # вердикт
    assert "NPV" in opinion and "мес." in opinion      # показатели упомянуты
    assert not opinion_is_positive(review, result.metrics.npv)


def test_opinion_positive_profile():
    review = _review("ok")
    result = _result(npv="2500000", peak="300000")
    opinion = build_opinion(review, result)
    assert "готов к представлению" in opinion
    assert "не выявило рисков" in opinion
    assert "2 500 000" in opinion                      # NPV с группировкой разрядов
    assert "300 000" in opinion                        # пиковая потребность
    assert opinion_is_positive(review, result.metrics.npv)


def test_opinion_warning_profile():
    review = _review("warning", [_finding("warning", "Тонкая маржа", "Поднять цену.")])
    opinion = build_opinion(review, _result())
    assert "слабые места" in opinion
    assert "Слабые места (предупреждения):" in opinion
    assert "— Тонкая маржа. Поднять цену." in opinion
    assert "жизнеспособен" in opinion                  # вердикт warning-профиля


def test_opinion_negative_npv_overrides_light():
    """Даже при «зелёном» ревью отрицательный NPV делает вердикт отрицательным."""
    opinion = build_opinion(_review("ok"), _result(npv="-100"))
    assert "не рекомендуется" in opinion
    assert not opinion_is_positive(_review("ok"), Decimal("-100"))


def test_opinion_undefined_metrics_wording():
    opinion = build_opinion(_review("ok"), _result(irr=None, pb=None))
    assert "IRR) не определена" in opinion
    assert "окупаемость в пределах горизонта не достигается" in opinion


def test_opinion_findings_limited_to_five():
    findings = [_finding("risk", f"Риск {i}") for i in range(8)]
    opinion = build_opinion(_review("risk", findings), _result())
    assert "— Риск 4." in opinion and "— Риск 5." not in opinion
    # Усечение названо: пять строк под «Существенные риски» без оговорки читаются
    # как весь список (заключение уходит отдельным файлом, без интерфейса рядом).
    assert "Показаны 5 находок из 8" in opinion


def test_opinion_short_list_gets_no_truncation_note():
    """Оговорка появляется от усечения, а не всегда."""
    opinion = build_opinion(_review("risk", [_finding("risk", "Риск 0")]), _result())
    assert "Показаны" not in opinion


def test_opinion_truncation_says_where_the_rest_is():
    """Читателю документа некуда посмотреть остальные находки, если не сказать куда."""
    findings = [_finding("risk", f"Риск {i}") for i in range(8)]
    assert "Ревью плана" in build_opinion(_review("risk", findings), _result())


def test_opinion_counts_are_named_for_every_severity():
    """Пришло на смену одинокому «Заметок для перепроверки: N».

    Прежняя строка выводилась только в ветке «ok/info» и называла лишь заметки —
    число рисков и предупреждений читатель документа не видел вовсе, хотя список
    выше мог быть усечён.
    """
    for review in (_review("risk", [_finding("risk"), _finding("warning")]),
                   _review("warning", [_finding("warning")]),
                   _review("info", [_finding("info")]),
                   _review("ok")):
        opinion = build_opinion(review, _result())
        c = review.counts
        assert (f"Всего находок ревью: рисков — {c['risk']}, "
                f"предупреждений — {c['warning']}, заметок — {c['info']}.") in opinion
