"""Консолидация группы предприятий (Финанс-Аудит, фаза H)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from audit_core import analyze, consolidate_subjects
from audit_core.models import AuditPeriod, AuditSubjectModel
from audit_core.samples import build_quarterly_subject, build_trading_subject

D = Decimal


def _subject(labels: list[str], cash: list[int], equity: list[int]) -> AuditSubjectModel:
    """Простой сходящийся субъект: актив = деньги, пассив = капитал."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label=x, kind="year") for x in labels],
        balance={"A_CASH": [D(v) for v in cash], "P_EQUITY": [D(v) for v in equity]},
        income={"I_REVENUE": [D(100) for _ in labels]},
    )


def _line(result, code):
    for group in (result.balance, result.income):
        for ln in group:
            if ln.code == code:
                return ln.values
    raise AssertionError(code)


def test_sums_matching_periods():
    """Строки складываются по совпадающим периодам; баланс группы сходится."""
    a = _subject(["2023", "2024"], [100, 150], [100, 150])
    b = _subject(["2023", "2024"], [40, 60], [40, 60])
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.periods_used == ["2023", "2024"]
    r = analyze(c.model)
    assert _line(r, "A_CASH") == [D(140), D(210)]
    assert _line(r, "A_TOTAL") == [D(140), D(210)]
    assert _line(r, "I_REVENUE") == [D(200), D(200)]
    assert r.balanced is True


def test_period_matched_by_label_not_position():
    """Сопоставление по подписи периода, а не по порядковому номеру."""
    a = _subject(["2023", "2024"], [100, 200], [100, 200])
    b = _subject(["2024", "2023"], [10, 1], [10, 1])   # обратный порядок
    c = consolidate_subjects([("A", a), ("B", b)])
    r = analyze(c.model)
    # 2023: 100 + 1; 2024: 200 + 10
    assert _line(r, "A_CASH") == [D(101), D(210)]


def test_only_common_periods_used():
    """Период, которого нет у всех, в свод не входит (иначе сумма занижала бы группу)."""
    a = _subject(["2022", "2023", "2024"], [10, 20, 30], [10, 20, 30])
    b = _subject(["2023", "2024"], [1, 2], [1, 2])
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.periods_used == ["2023", "2024"]
    assert c.skipped == {"A": ["2022"]}
    assert any("не вошли периоды" in w for w in c.warnings)
    assert _line(analyze(c.model), "A_CASH") == [D(21), D(32)]


def test_no_common_periods():
    """Совсем разные периоды: пустой свод + явное предупреждение."""
    c = consolidate_subjects([("Год", build_trading_subject()),
                              ("Квартал", build_quarterly_subject())])
    assert c.periods_used == []
    assert any("нет ни одного общего отчётного периода" in w for w in c.warnings)
    assert analyze(c.model).n == 0


def test_intragroup_warning_always_present():
    """Оговорка о невычтенных внутригрупповых оборотах присутствует всегда."""
    c = consolidate_subjects([("A", _subject(["2024"], [10], [10]))])
    assert any("внутригрупповые обороты" in w for w in c.warnings)


def test_memo_line_consolidated():
    """Справочная строка (нераспределённая прибыль) тоже складывается — нужна диагностике."""
    a = _subject(["2024"], [100], [100])
    a.balance["M_RETAINED"] = [D(30)]
    b = _subject(["2024"], [50], [50])
    b.balance["M_RETAINED"] = [D(20)]
    c = consolidate_subjects([("A", a), ("B", b)])
    assert c.model.balance["M_RETAINED"] == [D(50)]


def test_empty_members_rejected():
    with pytest.raises(ValueError):
        consolidate_subjects([])


def test_consolidate_endpoint(client, auth_headers):
    """Эндпоинт: свод двух субъектов, состав, оговорки и анализ группы."""
    def make(name: str, cash: str, equity: str) -> str:
        model = {
            "periods": [{"label": "2024", "kind": "year"}],
            "balance": {"A_CASH": [cash], "P_EQUITY": [equity]},
            "income": {"I_REVENUE": ["500"], "I_COGS": ["300"], "I_OPEX": ["100"],
                       "I_INTEREST": ["0"], "I_OTHER": ["0"], "I_TAX": ["20"]},
        }
        return client.post("/api/v1/audit/subjects", json={"name": name, "model": model},
                           headers=auth_headers).json()["id"]

    ids = [make("Мама", "100", "100"), make("Дочка", "40", "40")]
    r = client.post("/api/v1/audit/consolidate",
                    json={"subject_ids": ids, "name": "Наша группа"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["members"] == ["Мама", "Дочка"]
    assert body["periods_used"] == ["2024"]
    assert any("внутригрупповые обороты" in w for w in body["warnings"])
    total = next(ln for ln in body["analysis"]["balance"] if ln["code"] == "A_TOTAL")
    assert str(total["values"][0]) == "140"
    assert body["analysis"]["opinion"]


def test_consolidate_isolated_by_org(client, register):
    """Чужой субъект в свод не попадает (404)."""
    a = register(email="ca@e.ru", org="Орг CA")
    b = register(email="cb@e.ru", org="Орг CB")
    model = {"periods": [{"label": "2024", "kind": "year"}],
             "balance": {"A_CASH": ["10"], "P_EQUITY": ["10"]}, "income": {}}
    sid = client.post("/api/v1/audit/subjects", json={"name": "Чужой", "model": model},
                      headers=a).json()["id"]
    r = client.post("/api/v1/audit/consolidate", json={"subject_ids": [sid]}, headers=b)
    assert r.status_code == 404


# --- v2: исключение внутригрупповых оборотов ---

def _traded(rec: int, rev: int) -> AuditSubjectModel:
    """Субъект с взаимной задолженностью и выручкой (баланс сходится)."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label="2024", kind="year")],
        balance={"A_RECEIVABLE": [D(rec)], "A_CASH": [D(100)],
                 "P_EQUITY": [D(100)], "P_SHORT": [D(rec)]},
        income={"I_REVENUE": [D(rev)], "I_COGS": [D(rev)]},
    )


def test_elimination_removes_intragroup_turnover():
    """Взаимные обороты вычитаются из свода."""
    from audit_core.consolidate import Elimination

    members = [("A", _traded(50, 300)), ("B", _traded(30, 200))]
    plain = analyze(consolidate_subjects(members).model)
    cut = analyze(consolidate_subjects(
        members, elimination=Elimination(receivables=[D(20)], revenue=[D(100)])).model)

    assert _line(plain, "A_RECEIVABLE") == [D(80)] and _line(cut, "A_RECEIVABLE") == [D(60)]
    assert _line(plain, "I_REVENUE") == [D(500)] and _line(cut, "I_REVENUE") == [D(400)]
    assert _line(cut, "I_COGS") == [D(400)]          # себестоимость вычтена парно
    assert _line(cut, "P_SHORT") == [D(60)]          # кредиторка вычтена парно


def test_elimination_keeps_balance_invariant():
    """Парное вычитание сохраняет «актив = пассив» — иначе свод стал бы некорректным."""
    from audit_core.consolidate import Elimination

    members = [("A", _traded(50, 300)), ("B", _traded(30, 200))]
    r = analyze(consolidate_subjects(
        members, elimination=Elimination(receivables=[D(35)], revenue=[D(250)])).model)
    assert r.balanced is True
    assert _line(r, "A_TOTAL") == _line(r, "P_TOTAL")


def test_elimination_capped_to_available():
    """Вычесть больше, чем есть в своде, нельзя: обрезается с предупреждением."""
    from audit_core.consolidate import Elimination

    c = consolidate_subjects([("A", _traded(50, 300))],
                             elimination=Elimination(receivables=[D(9999)]))
    assert any("превышает свод" in w for w in c.warnings)
    assert c.model.balance["A_RECEIVABLE"] == [D(0)]
    assert analyze(c.model).balanced is True


def test_elimination_changes_warning_text():
    """Без исключений — оговорка о завышении; с исключениями — что именно вычтено."""
    from audit_core.consolidate import Elimination

    plain = consolidate_subjects([("A", _traded(50, 300))])
    assert any("не исключает внутригрупповые обороты" in w for w in plain.warnings)

    cut = consolidate_subjects([("A", _traded(50, 300))],
                               elimination=Elimination(receivables=[D(10)]))
    assert any("исключены заданные внутригрупповые величины" in w for w in cut.warnings)
    # названо ровно то, что вычтено: выручку не исключали — о ней и не сообщаем
    text = " ".join(cut.warnings)
    assert "взаимная задолженность" in text and "взаимная выручка" not in text
    # оговорка про гудвилл появляется только при исключении вложений
    assert not any("Гудвилл" in w for w in cut.warnings)


def test_empty_elimination_is_inert():
    """Пустые исключения не меняют свод."""
    from audit_core.consolidate import Elimination

    members = [("A", _traded(50, 300))]
    a = consolidate_subjects(members).model
    b = consolidate_subjects(members, elimination=Elimination()).model
    assert a.balance == b.balance and a.income == b.income


# --- v2: рыночная капитализация не аддитивна ---

def test_market_cap_not_summed_into_group():
    """Капитализации участников не складываются: это был бы двойной счёт.

    Капитализация материнской компании уже включает стоимость дочерних, поэтому сумма по
    группе завышала бы капитал. В свод строка не переносится вовсе, и классическая модель
    Альтмана для группы не считается — вместо правдоподобного, но ложного числа.
    """
    a = _subject(["2024"], [100], [100])
    a.balance["M_MARKET_CAP"] = [D(500)]
    b = _subject(["2024"], [50], [50])
    b.balance["M_MARKET_CAP"] = [D(200)]
    c = consolidate_subjects([("A", a), ("B", b)])

    assert c.model.balance.get("M_MARKET_CAP") is None
    assert any("двойным счётом" in w for w in c.warnings)
    assert all(s.id != "altman_z_public" for s in analyze(c.model).diagnostics.scores)


def test_no_market_cap_no_extra_warning():
    """Без капитализации участников оговорка о ней не появляется."""
    c = consolidate_subjects([("A", _subject(["2024"], [100], [100]))])
    assert not any("двойным счётом" in w for w in c.warnings)


# --- v2: доли участия и нереализованная прибыль в запасах ---

def _holder(fixed: int, inventory: int, equity: int) -> AuditSubjectModel:
    """Участник с вложением во внеоборотных активах и запасами (баланс сходится)."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label="2024", kind="year")],
        balance={"A_FIXED": [D(fixed)], "A_INVENTORY": [D(inventory)],
                 "A_CASH": [D(50)], "P_EQUITY": [D(equity)],
                 "P_SHORT": [D(fixed + inventory + 50 - equity)],
                 "M_RETAINED": [D(40)]},
        income={"I_REVENUE": [D(600)], "I_COGS": [D(400)]},
    )


def test_investment_eliminated_against_equity():
    """Вложение в капитал вычитается парно: из внеоборотных активов и из капитала."""
    from audit_core.consolidate import Elimination

    members = [("Мама", _holder(300, 100, 200)), ("Дочка", _holder(0, 80, 120))]
    plain = analyze(consolidate_subjects(members).model)
    cut = analyze(consolidate_subjects(
        members, elimination=Elimination(investments=[D(120)])).model)

    assert _line(plain, "A_FIXED") == [D(300)] and _line(cut, "A_FIXED") == [D(180)]
    assert _line(plain, "P_EQUITY") == [D(320)] and _line(cut, "P_EQUITY") == [D(200)]
    assert cut.balanced is True                       # инвариант держится
    # актив группы уменьшился ровно на вложение — двойной счёт капитала снят
    assert _line(plain, "A_TOTAL")[0] - _line(cut, "A_TOTAL")[0] == D(120)


def test_investment_elimination_warns_about_goodwill():
    """Гудвилл и неконтролирующая доля не выделяются — об этом сказано прямо."""
    from audit_core.consolidate import Elimination

    c = consolidate_subjects([("A", _holder(300, 100, 200))],
                             elimination=Elimination(investments=[D(50)]))
    assert any("Гудвилл" in w and "неконтролирующая доля" in w for w in c.warnings)
    assert any("вложения в капитал участников" in w for w in c.warnings)


def test_unrealized_profit_removed_from_inventory_and_profit():
    """Нереализованная прибыль снимается из запасов, капитала и прибыли периода."""
    from audit_core.consolidate import Elimination

    members = [("A", _holder(300, 100, 200)), ("B", _holder(0, 80, 120))]
    plain = analyze(consolidate_subjects(members).model)
    cut = analyze(consolidate_subjects(
        members, elimination=Elimination(unrealized_profit=[D(30)])).model)

    assert _line(plain, "A_INVENTORY") == [D(180)] and _line(cut, "A_INVENTORY") == [D(150)]
    assert _line(cut, "P_EQUITY") == [D(290)]                 # 320 − 30
    # себестоимость восстановлена → прибыль группы ниже ровно на ту же величину
    assert _line(cut, "I_COGS")[0] - _line(plain, "I_COGS")[0] == D(30)
    assert _line(plain, "I_NET")[0] - _line(cut, "I_NET")[0] == D(30)
    assert cut.balanced is True


def test_unrealized_profit_adjusts_retained_memo():
    """Нераспределённая прибыль (справочная строка) уменьшается на ту же сумму.

    Иначе фактор моделей Альтмана «накопленная прибыль / активы» противоречил бы капиталу,
    из которого эта прибыль уже вычтена.
    """
    from audit_core.consolidate import Elimination

    c = consolidate_subjects([("A", _holder(300, 100, 200)), ("B", _holder(0, 80, 120))],
                             elimination=Elimination(unrealized_profit=[D(30)]))
    assert c.model.balance["M_RETAINED"] == [D(50)]           # 40 + 40 − 30


def test_both_new_eliminations_keep_invariant():
    """Вложения и нереализованная прибыль вместе — баланс группы по-прежнему сходится."""
    from audit_core.consolidate import Elimination

    members = [("A", _holder(300, 100, 200)), ("B", _holder(0, 80, 120))]
    r = analyze(consolidate_subjects(members, elimination=Elimination(
        receivables=[D(0)], revenue=[D(50)],
        investments=[D(120)], unrealized_profit=[D(30)])).model)
    assert r.balanced is True
    assert _line(r, "A_TOTAL") == _line(r, "P_TOTAL")


def test_new_eliminations_capped_to_available():
    """Вычесть больше, чем есть, нельзя — обрезка с предупреждением, инвариант держится."""
    from audit_core.consolidate import Elimination

    # A_FIXED 300, A_INVENTORY 100, P_EQUITY 200
    c = consolidate_subjects([("A", _holder(300, 100, 200))],
                             elimination=Elimination(investments=[D(9999)],
                                                     unrealized_profit=[D(9999)]))
    assert sum("превышает свод" in w for w in c.warnings) == 2
    # вложения обрезаны капиталом (200), а не активом: 300 − 200 = 100, капитал → 0
    assert c.model.balance["A_FIXED"] == [D(100)] and c.model.balance["P_EQUITY"] == [D(0)]
    # капитала не осталось → нереализованная прибыль не вычитается вовсе (запасы целы)
    assert c.model.balance["A_INVENTORY"] == [D(100)]
    assert analyze(c.model).balanced is True


def test_unrealized_capped_after_investments():
    """Обрезка нереализованной прибыли учитывает капитал, уже уменьшенный вложениями."""
    from audit_core.consolidate import Elimination

    # капитал 200: вложения снимают 150, на прибыль остаётся 50
    c = consolidate_subjects([("A", _holder(300, 100, 200))],
                             elimination=Elimination(investments=[D(150)],
                                                     unrealized_profit=[D(80)]))
    assert c.model.balance["P_EQUITY"] == [D(0)]
    assert c.model.balance["A_INVENTORY"] == [D(50)]          # вычтено 50, а не 80
    assert any("нереализованной прибыли" in w and "превышает свод" in w for w in c.warnings)


def test_memo_row_absent_when_nobody_entered_it():
    """Никто не вводил нераспределённую прибыль → в своде строки нет, а не ноль.

    Иначе диагностика группы посчитала бы модели Альтмана с накопленной прибылью 0, тогда
    как по тем же субъектам поодиночке они честно остаются нерассчитанными.
    """
    a = _subject(["2024"], [100], [100])
    b = _subject(["2024"], [50], [50])
    c = consolidate_subjects([("A", a), ("B", b)])
    assert "M_RETAINED" not in c.model.balance
    assert c.model.has_balance_row("M_RETAINED") is False

    a.balance["M_RETAINED"] = [D(30)]                 # ввёл только один участник
    c2 = consolidate_subjects([("A", a), ("B", b)])
    assert c2.model.balance["M_RETAINED"] == [D(30)]
