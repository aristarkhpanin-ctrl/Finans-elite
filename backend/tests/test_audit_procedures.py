"""Чек-лист процедур (Финанс-Аудит, «Экран 21»; методика — SPEC, Приложение М).

Проверяются решения методики, которые легко потерять при следующей правке:

* исполнитель назван у каждой процедуры, и системных ровно столько, сколько у
  платформы работающих правил (М.1);
* статус системной процедуры выводится из прогона, а не ставится руками, и
  ``no_data`` **не «пройдено»** (М.2);
* снятие без причины не применяется (М.3);
* всё невыполненное попадает в «Границы проверки» — скрыть нельзя (М.4).
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze, build_obligations, check_input, detect_flags
from audit_core.earnings import normalize_earnings
from audit_core.models import AuditSubjectModel
from audit_core.procedures import (
    ANALYST,
    CATALOG,
    DONE,
    FINDING,
    NO_DATA,
    PASS,
    PENDING,
    SKIPPED,
    SYSTEM,
    run_procedures,
)
from audit_core.samples import build_trading_subject

D = Decimal


def model(**over) -> AuditSubjectModel:
    """Здоровое предприятие на 2 года — то же, что в тестах флагов."""
    data = {
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["400", "440"], "A_INVENTORY": ["300", "330"],
            "A_RECEIVABLE": ["200", "220"], "A_CASH": ["100", "130"],
            "P_EQUITY": ["500", "600"], "P_LONG": ["200", "200"], "P_SHORT": ["300", "320"],
            "M_RETAINED": ["180", "250"],
        },
        "income": {
            "I_REVENUE": ["1800", "1980"], "I_COGS": ["1260", "1386"],
            "I_OPEX": ["340", "374"], "I_INTEREST": ["40", "40"],
            "I_OTHER": ["0", "0"], "I_TAX": ["32", "36"],
        },
    }
    for key, value in over.items():
        if key in ("balance", "income"):
            data[key] = {**data[key], **value}      # type: ignore[dict-item]
        else:
            data[key] = value
    return AuditSubjectModel.model_validate(data)


def report(m: AuditSubjectModel):
    result = analyze(m)
    obligations = build_obligations(m, result)
    return run_procedures(m, result, detect_flags(m, result, obligations),
                          check_input(m), obligations, normalize_earnings(m, result))


def item(m: AuditSubjectModel, code: str):
    found = [i for i in report(m).items if i.code == code]
    assert len(found) == 1, f"ожидалась одна процедура {code}, получено {len(found)}"
    return found[0]


# ── М.1. Каталог и исполнитель ───────────────────────────────────────────────

def test_catalog_size_is_pinned():
    """Счёт закреплён: спецификация называет число, и оно обязано совпадать с кодом."""
    assert len(CATALOG) == 28


def test_every_procedure_declares_an_executor_and_a_method():
    for p in CATALOG:
        assert p.source in (SYSTEM, ANALYST), p.code
        assert p.method, f"{p.code}: не сказано, чем процедура выполняется"
        assert p.group and p.title


def test_procedure_codes_are_unique():
    assert len({p.code for p in CATALOG}) == len(CATALOG)


def test_no_procedure_is_promised_for_later():
    """«Нужна выписка» — это другой исполнитель, а не «пока не реализовано».

    Формулировка «в разработке» у процедуры, которой просто не дают документов,
    обещала бы, что однажды платформа прочитает картотеку арбитражных дел. Она её
    не прочитает: такой процедуре нужен человек, и так и написано.
    """
    postponed = ("не реализован", "в разработке", "пока ", "скоро", "планируется")
    for p in CATALOG:
        low = p.method.lower()
        assert not any(w in low for w in postponed), p.code
        # И обратное: процедуру аналитика нельзя подписать «автоматически» — ровно
        # эту подпись макет ставит под сверкой с банковской выпиской.
        if p.source == ANALYST:
            assert "автоматическ" not in low, p.code


# ── М.2. Статус системной процедуры выводится ────────────────────────────────

def test_system_status_comes_from_the_run_not_from_a_mark():
    """Отметка аналитика по системной процедуре игнорируется.

    Иначе «выполнено» можно было бы объявить там, где правило не отработало, —
    и чек-лист перестал бы что-либо значить.
    """
    marked = model(procedure_marks=[{"code": "balance_identity", "status": "done",
                                     "note": "я посмотрел"}])
    assert item(marked, "balance_identity").status == PASS
    broken = model(balance={"A_CASH": ["100", "999"]},
                   procedure_marks=[{"code": "balance_identity", "status": "done",
                                     "note": "всё хорошо"}])
    assert item(broken, "balance_identity").status == FINDING


def test_finding_names_the_rule_that_fired():
    m = model(balance={"P_EQUITY": ["500", "-100"]})
    result = item(m, "equity_sufficiency")
    assert result.status == FINDING
    assert "negative_equity" in result.findings


def test_no_data_is_not_a_pass():
    """Главное решение методики: незаполненная строка — не благополучие.

    Покрытие процентов без введённых процентов не проверено, а не «в порядке».
    """
    m = model(income={"I_INTEREST": []})
    result = item(m, "interest_coverage")
    assert result.status == NO_DATA
    assert result.status != PASS
    assert "не введены" in result.detail


def test_one_period_gives_no_data_for_dynamics():
    """По одному периоду динамику сравнивать не с чем — и это сказано, а не «pass»."""
    m = model(periods=[{"label": "2024", "kind": "year"}])
    assert item(m, "receivables_dynamics").status == NO_DATA


def test_bankruptcy_models_not_computed_are_not_green():
    """Без нераспределённой прибыли модель не посчитана, а не «в зелёной зоне»."""
    m = model(balance={"M_RETAINED": []})
    result = item(m, "bankruptcy_models")
    assert result.status in (NO_DATA, PASS)
    if result.status == PASS:
        # Модели Z″ хватает и без M_RETAINED — но тогда об этом говорит счёт моделей.
        assert "Посчитано моделей" in result.detail


def test_empty_model_leaves_system_procedures_unrun():
    m = AuditSubjectModel()
    rep = report(m)
    system = [i for i in rep.items if i.source == SYSTEM]
    assert all(i.status == NO_DATA for i in system)
    assert rep.passed == 0


def test_unchecked_covenant_keeps_the_procedure_open():
    """`unknown` ковенант — не «проверено»: процедура остаётся незакрытой (Л.3 + М.2)."""
    m = model(obligations=[{"creditor": "Банк", "kind": "credit", "amount": "520",
                            "covenant": "Долг/EBITDA ≤ 2.5×"}])
    assert item(m, "covenants").status == NO_DATA


def test_checked_covenants_close_the_procedure():
    m = model(obligations=[{"creditor": "Банк", "kind": "credit", "amount": "520",
                            "covenant": "Долг/EBITDA ≤ 2.5×", "covenant_status": "ok"}])
    assert item(m, "covenants").status == PASS


def test_empty_obligations_leave_debt_procedures_unrun():
    """Реестр не заполнен — сверять нечего, и это не «сошлось»."""
    for code in ("debt_register", "off_balance", "covenants"):
        assert item(model(), code).status == NO_DATA


# ── М.3. Отметки аналитика ───────────────────────────────────────────────────

def test_analyst_procedure_is_pending_until_marked():
    assert item(model(), "litigation").status == PENDING


def test_analyst_mark_closes_the_procedure():
    m = model(procedure_marks=[{"code": "litigation", "status": "done",
                                "note": "картотека проверена, дел нет"}])
    result = item(m, "litigation")
    assert result.status == DONE and "картотека" in result.detail


def test_skip_without_a_reason_is_not_applied():
    """Процедура, снятая молча, неотличима от забытой — поэтому снятие не применяется."""
    m = model(procedure_marks=[{"code": "litigation", "status": "skipped"}])
    result = item(m, "litigation")
    assert result.status == PENDING
    assert "неотличима от забытой" in result.detail


def test_skip_with_a_reason_is_applied_and_keeps_the_reason():
    m = model(procedure_marks=[{"code": "litigation", "status": "skipped",
                                "note": "цель зарегистрирована месяц назад"}])
    result = item(m, "litigation")
    assert result.status == SKIPPED and "месяц назад" in result.detail


# ── М.5. Свои процедуры ──────────────────────────────────────────────────────

def test_custom_procedure_joins_the_checklist():
    m = model(custom_procedures=[{"title": "Сверить полисы ОСГОП с числом машин"}])
    codes = [i.title for i in report(m).items]
    assert "Сверить полисы ОСГОП с числом машин" in codes


def test_custom_procedure_is_never_performed_by_the_platform():
    m = model(custom_procedures=[{"title": "Своя", "status": "done", "note": "сделано"}])
    own = [i for i in report(m).items if i.title == "Своя"][0]
    assert own.source == ANALYST and own.status == DONE
    assert "платформа её не выполняет" in own.method


def test_nameless_custom_procedure_does_not_exist():
    m = model(custom_procedures=[{"title": "   ", "status": "done"}])
    assert report(m).total == len(CATALOG)


# ── М.4. Границы проверки ────────────────────────────────────────────────────

def test_limits_collect_everything_unfinished():
    m = model(procedure_marks=[{"code": "litigation", "status": "skipped",
                                "note": "цель моложе года"}])
    rep = report(m)
    joined = " | ".join(rep.limits)
    assert "Судебные дела и претензии — цель моложе года" in joined
    # Незакрытых процедур ровно столько, сколько строк в границах — ничего не потерялось.
    assert len(rep.limits) == rep.no_data + rep.skipped + rep.pending


def test_closed_procedures_stay_out_of_limits():
    m = model()
    rep = report(m)
    closed = {i.title for i in rep.items if not i.is_open}
    assert closed and not any(lim.split(" — ")[0] in closed for lim in rep.limits)


def test_coverage_is_the_share_of_closed_procedures():
    rep = report(model())
    assert rep.coverage == D(rep.closed) / D(rep.total)
    assert rep.closed == rep.passed + rep.findings + rep.done


def test_coverage_is_none_without_a_catalog():
    """Делить не на что — «0%» здесь означало бы «ничего не проверено»."""
    from audit_core.procedures import ProcedureReport
    assert ProcedureReport().coverage is None


# ── Демо-дело ────────────────────────────────────────────────────────────────

def test_demo_case_runs_every_system_procedure_it_can():
    """У демо-дела системная часть чек-листа закрыта, кроме честных пробелов.

    Демо, у которого половина правил «нет данных», ничему не учит; демо, у которого
    закрыто всё, — врёт: ковенанты в нём намеренно не проверены (см. Прил. Л).
    """
    m = build_trading_subject()
    rep = report(m)
    system = [i for i in rep.items if i.source == SYSTEM]
    unrun = [i.code for i in system if i.status == NO_DATA]
    assert unrun == ["covenants"]
    assert rep.findings == 0
    # Процедуры аналитика остаются открытыми: за него их никто не выполнил.
    assert rep.pending == sum(1 for p in CATALOG if p.source == ANALYST)

# ── М.4. Границы доходят до заключения и документа ───────────────────────────

def test_limits_reach_the_opinion():
    """Заключение без границ читается как «проверено всё» — поэтому раздел обязателен."""
    from audit_core.opinion import build_opinion
    m = model(procedure_marks=[{"code": "litigation", "status": "skipped",
                                "note": "цель моложе года"}])
    result = analyze(m)
    text = build_opinion(result, report(m))
    assert "Границы проверки" in text
    assert "Судебные дела и претензии — цель моложе года" in text


def test_opinion_without_a_checklist_invents_no_limits():
    """Чек-лист не считался — придумывать границы не из чего (свод группы)."""
    from audit_core.opinion import build_opinion
    assert "Границы проверки" not in build_opinion(analyze(model()))


def test_checklist_reaches_the_document():
    from app.audit_docgen import build_audit_docx
    m = model(procedure_marks=[{"code": "litigation", "status": "skipped",
                                "note": "цель моложе года"}])
    result = analyze(m)
    rep = report(m)
    content = build_audit_docx(result, "Заключение.", subject_name="Цель",
                               procedures=rep)
    assert content[:2] == b"PK" and len(content) > 5000


def test_document_lists_every_procedure_not_only_the_closed_ones():
    """Отчёт с одними закрытыми процедурами выдаёт часть проверки за целое."""
    import re
    from io import BytesIO
    from zipfile import ZipFile

    from app.audit_docgen import build_audit_docx
    m = model()
    rep = report(m)
    content = build_audit_docx(analyze(m), "Заключение.", subject_name="Цель",
                               procedures=rep)
    xml = ZipFile(BytesIO(content)).read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml)
    for item in rep.items:
        assert item.title in text, item.title
    assert "Судебные дела и претензии" in text        # процедура аналитика, не выполнена
