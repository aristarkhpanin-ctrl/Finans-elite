"""Эталонные субъекты анализа для golden-master Финанс-Аудит.

Числа подобраны так, чтобы баланс сходился и работали все группы коэффициентов
(включая квартальную периодичность — приведение к году).
"""
from __future__ import annotations

from decimal import Decimal

from .models import AuditPeriod, AuditSubjectModel

D = Decimal


def build_trading_subject() -> AuditSubjectModel:
    """Торговое предприятие, 3 года: рост выручки, умеренная долговая нагрузка."""
    return AuditSubjectModel(
        name="ООО «Торговый дом»",
        currency="RUB",
        industry="Оптовая торговля",
        periods=[AuditPeriod(label="2022", kind="year"),
                 AuditPeriod(label="2023", kind="year"),
                 AuditPeriod(label="2024", kind="year")],
        balance={
            "A_FIXED": [D(4000), D(4400), D(5200)],
            "A_INVENTORY": [D(3000), D(3600), D(4100)],
            "A_RECEIVABLE": [D(2200), D(2500), D(3000)],
            "A_CASH": [D(800), D(1000), D(1400)],
            # актив: 10000, 11500, 13700
            "P_EQUITY": [D(5000), D(6000), D(7400)],
            "P_LONG": [D(2000), D(2200), D(2600)],
            "P_SHORT": [D(3000), D(3300), D(3700)],
        },
        income={
            "I_REVENUE": [D(18000), D(21000), D(25000)],
            "I_COGS": [D(12600), D(14700), D(17250)],
            "I_OPEX": [D(3400), D(3900), D(4500)],
            "I_INTEREST": [D(400), D(430), D(500)],
            "I_OTHER": [D(0), D(100), D(-50)],
            "I_TAX": [D(320), D(414), D(540)],
        },
    )


def build_quarterly_subject() -> AuditSubjectModel:
    """Производство, 4 квартала: проверка приведения квартальных потоков к году."""
    return AuditSubjectModel(
        name="АО «Квартальный завод»",
        currency="RUB",
        industry="Производство",
        periods=[AuditPeriod(label=f"2024 Q{i}", kind="quarter") for i in (1, 2, 3, 4)],
        balance={
            "A_FIXED": [D(9000), D(9200), D(9100), D(9500)],
            "A_INVENTORY": [D(2500), D(2700), D(2900), D(2600)],
            "A_RECEIVABLE": [D(1800), D(2000), D(2200), D(2100)],
            "A_CASH": [D(700), D(600), D(900), D(1300)],
            # актив: 14000, 14500, 15100, 15500
            "P_EQUITY": [D(8000), D(8300), D(8700), D(9200)],
            "P_LONG": [D(3500), D(3600), D(3600), D(3500)],
            "P_SHORT": [D(2500), D(2600), D(2800), D(2800)],
        },
        income={
            "I_REVENUE": [D(5000), D(5400), D(5800), D(6200)],
            "I_COGS": [D(3300), D(3550), D(3800), D(4000)],
            "I_OPEX": [D(1000), D(1050), D(1120), D(1200)],
            "I_INTEREST": [D(150), D(150), D(145), D(140)],
            "I_OTHER": [D(0), D(0), D(20), D(0)],
            "I_TAX": [D(110), D(130), D(151), D(172)],
        },
    )


#: Реестр эталонов golden-master: (имя снимка, конструктор).
GOLDEN_SUBJECTS: list[tuple[str, object]] = [
    ("trading_subject", build_trading_subject),
    ("quarterly_subject", build_quarterly_subject),
]
