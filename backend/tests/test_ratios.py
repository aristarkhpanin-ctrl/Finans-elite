"""Тесты финансовых коэффициентов (5.2)."""
from decimal import Decimal

from calc_core import run
from calc_core.reports.lines import (
    BALANCE_LINES,
    CASHFLOW_LINES,
    INCOME_LINES,
    PROFIT_USE_LINES,
)
from calc_core.reports.ratios import compute_ratios
from calc_core.reports.statements import Statement
from calc_core.samples import build_sample_project


def _stmt(catalog, values):
    s = Statement(catalog, 1)
    for k, v in values.items():
        s[k] = [Decimal(v)]
    return s


def _stmt_n(catalog, values, n):
    s = Statement(catalog, n)
    for k, v in values.items():
        s[k] = [Decimal(x) for x in v]
    return s


def test_activity_uses_period_average_opening_and_prev():
    """Средняя за период: t0 = (opening+конец)/2, t1 = (конец t0 + конец t1)/2."""
    n = 2
    income = _stmt_n(INCOME_LINES, {"I1": [1200, 1200]}, n)
    balance = _stmt_n(BALANCE_LINES, {"B2": [200, 400]}, n)
    r = compute_ratios(income, _stmt_n(CASHFLOW_LINES, {}, n), balance,
                       _stmt_n(PROFIT_USE_LINES, {}, n), Decimal(0), n, {"B2": Decimal(100)})
    days = r.activity["Период оборачиваемости дебиторки, дн."]
    denom = Decimal(1200) * Decimal(12)
    assert days[0] == Decimal(365) * Decimal(150) / denom  # (100+200)/2
    assert days[1] == Decimal(365) * Decimal(300) / denom  # (200+400)/2


def _ratios(common_shares=10):
    income = _stmt(INCOME_LINES, {"I1": 100, "I4": 100, "I5": 20, "I7": 30, "I8": 60,
                                  "I9": 5, "I16": 10, "I18": 8, "I23": 12, "I28": 40})
    balance = _stmt(BALANCE_LINES, {"B1": 50, "B2": 30, "B3": 10, "B5": 20, "B6": 20,
                                    "B8": 200, "B11": 250, "B20": 500, "B23": 40,
                                    "B25": 100, "B26": 100, "B33": 300})
    profit_use = _stmt(PROFIT_USE_LINES, {"P4": 0, "P5": 5})
    cashflow = _stmt(CASHFLOW_LINES, {})
    return compute_ratios(income, cashflow, balance, profit_use, Decimal(common_shares), 1)


def test_liquidity():
    r = _ratios()
    assert r.liquidity["Коэффициент текущей ликвидности"][0] == Decimal(2)       # 200/100
    assert r.liquidity["Коэффициент срочной ликвидности"][0] == Decimal(1)       # (50+30+20)/100
    assert r.liquidity["Чистый оборотный капитал"][0] == Decimal(100)            # 200-100


def test_profitability():
    r = _ratios()
    assert r.profitability["Рентабельность валовой прибыли"][0] == Decimal("0.6")
    assert r.profitability["Рентабельность операционной прибыли"][0] == Decimal("0.45")
    assert r.profitability["Рентабельность чистой прибыли"][0] == Decimal("0.4")
    # ROA/ROE — на средние активы/капитал; opening не задан → среднее = конец/2.
    assert r.profitability["Рентабельность активов (ROA)"][0] == Decimal("1.92")   # 40*12/(500/2)
    assert r.profitability["Рентабельность собств. капитала (ROE)"][0] == Decimal("3.2")  # 480/(300/2)


def test_gearing_and_activity():
    r = _ratios()
    assert r.gearing["Суммарные обязательства к активам"][0] == Decimal("0.4")     # 200/500 (конец)
    assert r.gearing["Коэффициент покрытия процентов"][0] == Decimal("2.5")        # (12+8)/8
    # оборачиваемость — на средние; дебиторка средняя = 30/2 = 15 → 365*15/1200
    assert r.activity["Период оборачиваемости дебиторки, дн."][0] == Decimal("4.5625")


def test_investment_per_share():
    r = _ratios(common_shares=10)
    assert r.investment["Прибыль на акцию (EPS)"][0] == Decimal(48)                # (40-0)*12/10
    assert r.investment["Дивиденды на акцию"][0] == Decimal(6)                      # 5*12/10
    assert r.investment["Коэффициент покрытия дивидендов"][0] == Decimal(8)         # 40/5
    assert r.investment["Сумма активов на акцию"][0] == Decimal(50)                 # 500/10


def test_zero_denominator_is_none():
    income = _stmt(INCOME_LINES, {})
    balance = _stmt(BALANCE_LINES, {})
    profit_use = _stmt(PROFIT_USE_LINES, {})
    cashflow = _stmt(CASHFLOW_LINES, {})
    r = compute_ratios(income, cashflow, balance, profit_use, Decimal(0), 1)
    assert r.liquidity["Коэффициент текущей ликвидности"][0] is None  # B25 = 0
    assert r.investment["Прибыль на акцию (EPS)"][0] is None          # No = 0
    # чистый оборотный капитал — абсолютная величина, всегда определена
    assert r.liquidity["Чистый оборотный капитал"][0] == Decimal(0)


def test_ratios_attached_to_result():
    r = run(build_sample_project())
    assert len(r.ratios.liquidity["Коэффициент текущей ликвидности"]) == r.n
    # демо задаёт common_shares=1000 → показатели «на акцию» определены
    assert r.ratios.investment["Сумма активов на акцию"][0] is not None
