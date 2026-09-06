"""Полный разбор дела — один конвейер на экран и на документ (SPEC, Приложение У).

Слои due diligence считаются в строгом порядке: каждый следующий читает предыдущие
(флагам нужен реестр обязательств, процедурам — флаги и качество прибыли, сводке —
всё сразу). Порядок этот был записан дважды — в эндпоинте анализа и в выгрузке
документа, — и во второй копии половина слоёв отсутствовала: документ рассказывал о
состоянии, но молчал о находках, оценке и рисках, хотя читатель документа и есть тот,
кому они адресованы. Две копии конвейера расходятся молча, поэтому копия здесь одна.

Модуль остаётся чистым: ни FastAPI, ни базы — на вход модель, на выход разбор.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import analyze
from .earnings import EarningsQuality, normalize_earnings
from .flags import FlagRegistry, detect_flags
from .input_check import InputIssue, check_input
from .models import AuditSubjectModel
from .obligations import ObligationRegister, build_obligations
from .opinion import build_opinion
from .planfact import PlanFact, build_plan_fact
from .procedures import ProcedureReport, run_procedures
from .result import AuditResult
from .risk import RiskResult, analyze_risk
from .summary import CaseSummary, build_summary
from .valuation import Valuation, build_valuation

__all__ = ["CaseReview", "review_case"]


@dataclass
class CaseReview:
    """Разбор дела целиком: результат анализа и все слои поверх него.

    Слои **не входят** в ``AuditResult`` — он остаётся тем, что стережёт
    `tests/golden_audit`, и ни один пакет due diligence его не трогал.
    """

    model: AuditSubjectModel
    result: AuditResult
    issues: list[InputIssue] = field(default_factory=list)
    flags: FlagRegistry = field(default_factory=FlagRegistry)
    earnings: EarningsQuality = field(default_factory=EarningsQuality)
    obligations: ObligationRegister = field(default_factory=ObligationRegister)
    procedures: ProcedureReport = field(default_factory=ProcedureReport)
    valuation: Valuation = field(default_factory=Valuation)
    risk: RiskResult = field(default_factory=RiskResult)
    plan_fact: PlanFact = field(default_factory=PlanFact)
    summary: CaseSummary = field(default_factory=CaseSummary)
    opinion: str = ""


def review_case(model: AuditSubjectModel) -> CaseReview:
    """Посчитать анализ и все слои поверх него в единственном верном порядке."""
    result = analyze(model)
    # Находки о качестве ввода считаются по исходной модели, а не по результату:
    # анализ уже применил переоценки, а претензии предъявляются к тому, что ввели.
    obligations = build_obligations(model, result)
    issues = check_input(model)
    flags = detect_flags(model, result, obligations)
    earnings = normalize_earnings(model, result)
    procedures = run_procedures(model, result, flags, issues, obligations, earnings)
    valuation = build_valuation(model, result, earnings, obligations)
    risk = analyze_risk(model, result, earnings, obligations)
    plan_fact = build_plan_fact(model, flags)
    summary = build_summary(model, result, flags, issues, obligations, earnings,
                            procedures, valuation)
    return CaseReview(
        model=model, result=result, issues=issues, flags=flags, earnings=earnings,
        obligations=obligations, procedures=procedures, valuation=valuation, risk=risk,
        plan_fact=plan_fact, summary=summary,
        # Границы проверки идут в заключение: умолчание о непроверенном читается как
        # проверенное, и скрыть его нельзя (SPEC, Приложение М.4).
        opinion=build_opinion(result, procedures),
    )
