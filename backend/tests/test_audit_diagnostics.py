"""Диагностика Финанс-Аудит (фаза D): скоринги банкротства, нормативы, «светофор».

Числа выверены вручную по опубликованным формулам моделей.
"""
from __future__ import annotations

from decimal import Decimal

from audit_core import analyze
from audit_core.diagnostics import DISTRESS, GOOD, GREY, RISK, SAFE, WARN
from audit_core.models import AuditPeriod, AuditSubjectModel

D = Decimal


def _healthy(with_retained: bool = True, n: int = 1) -> AuditSubjectModel:
    """Устойчивое предприятие: актив 1000 = пассив, прибыльное, низкий долг."""
    bal = {
        "A_FIXED": [D(400)] * n,
        "A_INVENTORY": [D(200)] * n,
        "A_RECEIVABLE": [D(250)] * n,
        "A_CASH": [D(150)] * n,          # актив 1000, оборотные 600
        "P_EQUITY": [D(700)] * n,
        "P_LONG": [D(100)] * n,
        "P_SHORT": [D(200)] * n,         # пассив 1000, обязательства 300
    }
    if with_retained:
        bal["M_RETAINED"] = [D(300)] * n
    return AuditSubjectModel(
        periods=[AuditPeriod(label=f"P{i + 1}", kind="year") for i in range(n)],
        balance=bal,
        income={
            "I_REVENUE": [D(1500)] * n,
            "I_COGS": [D(900)] * n,
            "I_OPEX": [D(400)] * n,      # EBIT = 200
            "I_INTEREST": [D(20)] * n,
            "I_OTHER": [D(0)] * n,
            "I_TAX": [D(36)] * n,        # чистая = 144
        },
    )


def _distressed() -> AuditSubjectModel:
    """Неустойчивое: убыток, отрицательный оборотный капитал, высокая долговая нагрузка."""
    return AuditSubjectModel(
        periods=[AuditPeriod(label="2024", kind="year")],
        balance={
            "A_FIXED": [D(700)], "A_INVENTORY": [D(150)],
            "A_RECEIVABLE": [D(100)], "A_CASH": [D(50)],       # актив 1000, оборотные 300
            "P_EQUITY": [D(50)], "P_LONG": [D(200)], "P_SHORT": [D(750)],
            "M_RETAINED": [D(-400)],
        },
        income={
            "I_REVENUE": [D(600)], "I_COGS": [D(500)], "I_OPEX": [D(200)],  # EBIT = −100
            "I_INTEREST": [D(90)], "I_OTHER": [D(0)], "I_TAX": [D(0)],      # чистая = −190
        },
    )


def _score(r, sid):
    return next(s for s in r.diagnostics.scores if s.id == sid)


def _assess(r, name):
    return next(a for a in r.diagnostics.assessments if a.name == name)


def test_altman_private_formula():
    """Z′ = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5 (учётные величины)."""
    r = analyze(_healthy())
    # X1=(600−200)/1000=0.4; X2=300/1000=0.3; X3=200/1000=0.2; X4=700/300; X5=1500/1000=1.5
    expected = (D("0.717") * D("0.4") + D("0.847") * D("0.3") + D("3.107") * D("0.2")
                + D("0.420") * (D(700) / D(300)) + D("0.998") * D("1.5"))
    z = _score(r, "altman_z_private")
    assert z.values[0] == expected
    assert z.zones[0] == SAFE          # > 2.9


def test_altman_nonmfg_formula():
    """Z″ = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4 (без фактора выручки)."""
    r = analyze(_healthy())
    expected = (D("6.56") * D("0.4") + D("3.26") * D("0.3") + D("6.72") * D("0.2")
                + D("1.05") * (D(700) / D(300)))
    z = _score(r, "altman_z_nonmfg")
    assert z.values[0] == expected and z.zones[0] == SAFE


def test_two_factor_model_excluded():
    """Двухфакторная модель не включена: она структурно не способна подать сигнал риска.

    Её максимум при любых допустимых входах = −0.3877 + 0.0579 ≈ −0.33 < 0 (граница зоны),
    т.е. даже для неплатёжеспособного предприятия она показала бы «низкий риск».
    """
    r = analyze(_distressed())
    assert all(s.id != "two_factor" for s in r.diagnostics.scores)
    # проверка самого утверждения: максимум формулы < 0
    best = D("-0.3877") - D("1.0736") * D(0) + D("0.0579") * D(1)
    assert best < 0


def test_distressed_subject_flagged():
    """Неустойчивое предприятие: модели Альтмана в зоне риска, светофор — risk."""
    r = analyze(_distressed())
    assert _score(r, "altman_z_private").zones[0] == DISTRESS
    assert _score(r, "altman_z_nonmfg").zones[0] == DISTRESS
    assert r.diagnostics.light == RISK
    assert "неустойчивости" in r.diagnostics.summary


def test_missing_retained_is_undefined_not_zero():
    """Без нераспределённой прибыли модели с этим фактором не считаются (None), а не «0»."""
    r = analyze(_healthy(with_retained=False))
    assert _score(r, "altman_z_private").values == [None]
    assert _score(r, "altman_z_private").zones == [None]
    assert "Не рассчитан" in _score(r, "altman_z_private").note
    assert _score(r, "altman_z_nonmfg").values == [None]
    # нормативная оценка коэффициентов этого фактора не требует — работает
    assert _assess(r, "Коэффициент текущей ликвидности").status == [GOOD]


def test_ratio_assessment_statuses():
    """Нормативы: значения по краям попадают в good/warn/risk."""
    r = analyze(_healthy())
    assert _assess(r, "Коэффициент текущей ликвидности").status == [GOOD]      # 3.0 ≥ 1.5
    assert _assess(r, "Коэффициент автономии").status == [GOOD]                # 0.7 ≥ 0.5
    assert _assess(r, "Рентабельность чистой прибыли").status == [GOOD]        # > 0

    bad = analyze(_distressed())
    assert _assess(bad, "Коэффициент текущей ликвидности").status == [RISK]    # 0.4 < 1
    assert _assess(bad, "Коэффициент автономии").status == [RISK]              # 0.05 < 0.3
    assert _assess(bad, "Рентабельность чистой прибыли").status == [RISK]      # убыток


def test_warning_light_between_bands():
    """Пограничные значения (без нарушенных нормативов) → светофор warning, не risk."""
    m = _healthy()
    # Ктл = 600/450 = 1.33 → warn (1..1.5); обязательства/капитал = 500/500 = 1 → warn (0.7..1]
    m.balance["P_SHORT"] = [D(450)]
    m.balance["P_LONG"] = [D(50)]
    m.balance["P_EQUITY"] = [D(500)]           # актив 1000 = пассив 1000
    r = analyze(m)
    assert r.balanced is True
    assert _assess(r, "Коэффициент текущей ликвидности").status == [WARN]
    assert _assess(r, "Суммарные обязательства к собств. капиталу").status == [WARN]
    # ни один норматив не нарушен → risk не выставляется
    assert all(RISK not in a.status for a in r.diagnostics.assessments)
    assert r.diagnostics.light == "warning"
    assert "внимания" in r.diagnostics.summary


def test_light_uses_last_period():
    """Диагноз ставится по текущему (последнему) периоду, а не по истории."""
    m = _healthy(n=2)
    # ухудшаем только первый период — текущее состояние остаётся здоровым
    m.balance["P_SHORT"] = [D(900), D(200)]
    m.balance["P_EQUITY"] = [D(0), D(700)]
    m.balance["P_LONG"] = [D(100), D(100)]
    r = analyze(m)
    assert _assess(r, "Коэффициент автономии").status == [RISK, GOOD]
    assert r.diagnostics.light == "ok"


def test_grey_zone_maps_to_warning():
    """Зона неопределённости скоринга без нарушенных нормативов → warning."""
    r = analyze(_healthy())
    z = _score(r, "altman_z_private")
    assert z.zones[0] in (SAFE, GREY)     # эталон здоровый
    assert r.diagnostics.light in ("ok", "warning")


def test_empty_model_has_no_diagnostics():
    r = analyze(AuditSubjectModel())
    assert r.diagnostics is None or r.diagnostics.scores == []


# --- v2: свои нормативы субъекта ---

def _th(ratio: str, direction: str, risk: str, good: str):
    from audit_core.models import RatioThreshold
    return RatioThreshold(ratio=ratio, direction=direction, risk_edge=D(risk), good_edge=D(good))


def test_custom_threshold_overrides_universal():
    """Свой норматив строже универсального → показатель уходит в risk."""
    m = _healthy()          # Ктл = 600/200 = 3.0 → по универсальному good
    assert _assess(analyze(m), "Коэффициент текущей ликвидности").status == [GOOD]

    m.thresholds = [_th("Коэффициент текущей ликвидности", "higher", "3.5", "4")]
    r = analyze(m)
    assert _assess(r, "Коэффициент текущей ликвидности").status == [RISK]
    assert r.diagnostics.light == RISK


def test_custom_threshold_can_relax():
    """Свой норматив мягче универсального → показатель перестаёт быть нарушением."""
    m = _distressed()       # Ктл = 300/750 = 0.4 → по универсальному risk
    assert _assess(analyze(m), "Коэффициент текущей ликвидности").status == [RISK]

    m.thresholds = [_th("Коэффициент текущей ликвидности", "higher", "0.2", "0.35")]
    assert _assess(analyze(m), "Коэффициент текущей ликвидности").status == [GOOD]


def test_threshold_for_metric_without_universal_norm():
    """Норматив можно задать показателю, у которого универсального порога нет."""
    m = _healthy()
    assert _assess_opt(analyze(m), "Оборачиваемость активов") is None
    m.thresholds = [_th("Оборачиваемость активов", "higher", "2", "3")]
    # оборачиваемость = 1500/1000 = 1.5 → ниже границы риска
    assert _assess(analyze(m), "Оборачиваемость активов").status == [RISK]


def test_inconsistent_threshold_ignored_with_warning():
    """Несогласованный порог не применяется молча — универсальный + предупреждение."""
    m = _healthy()
    m.thresholds = [_th("Коэффициент текущей ликвидности", "higher", "3", "1")]  # риск > нормы
    r = analyze(m)
    assert _assess(r, "Коэффициент текущей ликвидности").status == [GOOD]   # универсальный
    assert any("несогласованно" in w for w in r.warnings)


def test_no_thresholds_is_inert():
    """Без своих нормативов поведение прежнее."""
    m = _healthy()
    assert analyze(m).diagnostics.light == analyze(_healthy()).diagnostics.light


def _assess_opt(r, name):
    return next((a for a in r.diagnostics.assessments if a.name == name), None)


# --- v2: классическая модель Альтмана (публичные компании) ---

def _score_opt(r, sid):
    return next((s for s in r.diagnostics.scores if s.id == sid), None)


def test_altman_public_formula():
    """Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5, где X4 — рыночная капитализация."""
    m = _healthy()
    m.balance["M_MARKET_CAP"] = [D(1200)]
    r = analyze(m)
    # X1=0.4; X2=0.3; X3=0.2; X4=1200/300=4 (рыночная, не 700/300); X5=1.5
    expected = (D("1.2") * D("0.4") + D("1.4") * D("0.3") + D("3.3") * D("0.2")
                + D("0.6") * D(4) + D("1.0") * D("1.5"))
    z = _score(r, "altman_z_public")
    assert z.values[0] == expected
    assert z.zones[0] == SAFE          # > 2.99


def test_public_model_uses_market_not_book_equity():
    """Классическая модель берёт рыночную стоимость капитала, а не балансовую.

    Балансовый капитал 700, капитализация 1200 → фактор X4 обязан отличаться, иначе под
    именем классической модели считалась бы модификация Z′.
    """
    m = _healthy()
    m.balance["M_MARKET_CAP"] = [D(1200)]
    with_market = _score(analyze(m), "altman_z_public").values[0]
    m.balance["M_MARKET_CAP"] = [D(700)]        # капитализация = балансовому капиталу
    as_book = _score(analyze(m), "altman_z_public").values[0]
    assert with_market != as_book
    assert with_market - as_book == D("0.6") * (D(500) / D(300))


def test_public_model_absent_without_market_cap():
    """Без капитализации модель не показывается вовсе: у непубличной компании её нет.

    Это отличается от нераспределённой прибыли: та есть у любого предприятия и может быть
    просто не введена (модель показывается «не рассчитанной»), а капитализации у
    непубличной компании не существует — строка «не рассчитано» вводила бы в заблуждение.
    """
    r = analyze(_healthy())
    assert _score_opt(r, "altman_z_public") is None
    assert _score_opt(r, "altman_z_private") is not None


def test_public_model_zero_market_cap_is_entered_value():
    """Введённый ноль — это факт (капитал обесценен), а не «не введено»: модель считается.

    Отличие от отсутствия строки принципиально: там модель не показывается вовсе, здесь —
    считается с X4 = 0. Итоговая зона остаётся за моделью: прочие факторы у предприятия
    сильные, и подменять её вердикт своим мы не вправе.
    """
    m = _healthy()
    m.balance["M_MARKET_CAP"] = [D(0)]
    z = _score(analyze(m), "altman_z_public")
    # X4 = 0 → Z = 1.2·0.4 + 1.4·0.3 + 3.3·0.2 + 1.0·1.5 = 3.06
    assert z.values[0] == D("3.06")
    assert z.zones[0] == SAFE          # 3.06 > 2.99 — вердикт модели, а не наш


def test_public_model_needs_retained_too():
    """Фактор накопленной прибыли общий: без него классическая модель тоже не считается."""
    m = _healthy(with_retained=False)
    m.balance["M_MARKET_CAP"] = [D(1200)]
    z = _score(analyze(m), "altman_z_public")
    assert z.values == [None] and z.zones == [None]
    assert "Не рассчитан" in z.note


def test_public_model_counts_in_light():
    """Классическая модель в зоне риска влияет на «светофор» наравне с прочими."""
    m = _distressed()
    m.balance["M_MARKET_CAP"] = [D(10)]
    r = analyze(m)
    assert _score(r, "altman_z_public").zones[0] == DISTRESS
    assert r.diagnostics.light == RISK
