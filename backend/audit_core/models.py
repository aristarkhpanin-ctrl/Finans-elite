"""Модель субъекта анализа (Финанс-Аудит): реквизиты, периоды, фактическая отчётность.

Хранится как JSON в таблице ``audit_subjects`` (по образцу ``Project.model``). Значения —
``Decimal`` (строками в JSON), как в расчётном ядре первого продукта. Инвариант «актив =
пассив» проверяется по агрегатам ввода.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .lines import ASSET_CODES, EQLIAB_CODES, INCOME_CODES, INCOME_MEMO_CODES


class AuditPeriod(BaseModel):
    """Отчётный период: подпись (например «2024», «2024 Q1», «01.2024») и тип.

    Тип задаёт длину периода: показатели «в днях» считаются по ней, а потоковые
    показатели приводятся к году (квартал ×4, месяц ×12) — иначе периоды разной
    длины были бы несопоставимы.
    """

    label: str = Field(default="", max_length=40)
    kind: Literal["year", "quarter", "month"] = "year"


class UserMetric(BaseModel):
    """Пользовательский показатель: имя + формула над строками аналитической формы.

    Формула — язык формул платформы (тот же, что в таблицах первого продукта). Доступны
    коды строк аналитической формы (``A_*``/``P_*``/``I_*``/``M_*``) и ``N`` — число
    периодов. Ошибка формулы не роняет анализ: показатель получает сообщение и нули.
    """

    name: str = Field(default="", max_length=200)
    formula: str = Field(default="", max_length=2000)


class RatioThreshold(BaseModel):
    """Свой норматив для показателя (v2): переопределяет универсальный порог.

    ``direction`` — «чем больше, тем лучше» (``higher``) или наоборот (``lower``).
    ``risk_edge`` — граница зоны риска, ``good_edge`` — граница нормы; между ними «внимание».
    Для ``higher`` ожидается ``risk_edge <= good_edge``, для ``lower`` — наоборот;
    несогласованный порог игнорируется с предупреждением (молча подменять оценку нельзя).
    """

    ratio: str = Field(default="", max_length=200)
    direction: Literal["higher", "lower"] = "higher"
    risk_edge: Decimal = Decimal(0)
    good_edge: Decimal = Decimal(0)

    def is_consistent(self) -> bool:
        return (self.risk_edge <= self.good_edge if self.direction == "higher"
                else self.risk_edge >= self.good_edge)


class Revaluation(BaseModel):
    """Поправка к статье баланса (v2): экспертная переоценка по периодам.

    ``code`` — статья баланса (кроме капитала: он служит корреспонденцией любой поправки),
    ``label`` — причина («безнадёжная дебиторка», «дооценка ОС»), ``amounts`` — поправки по
    периодам (со знаком). Актив ``+Δ`` увеличивает капитал, обязательство ``+Δ`` уменьшает —
    поэтому равенство «актив = пассив» сохраняется.
    """

    code: str = Field(default="", max_length=32)
    label: str = Field(default="", max_length=200)
    amounts: list[Decimal] = Field(default_factory=list)


class EarningsAdjustment(BaseModel):
    """Поправка к показателю прибыли при нормализации (SPEC, Приложение К.2).

    Нормализация — суждение, а не расчёт: что считать разовым доходом и какое
    вознаграждение собственника избыточно, знает проверяющий, а не формула. Поэтому
    поправку задаёт пользователь, и у неё **обязательна причина** (``label``): без неё
    нормализованный показатель нельзя объяснить, а значит нельзя и защитить в переговорах.

    ``amounts`` — со знаком: «+» возвращает прибыль (убрали лишний расход), «−» убирает
    (разовый доход не повторится).
    """

    label: str = Field(default="", max_length=200)
    kind: Literal["one_off", "owner", "related_party", "non_operating",
                  "accounting"] = "one_off"
    amounts: list[Decimal] = Field(default_factory=list)


#: Виды обязательства → (подпись, забалансовое ли). Забалансовость — свойство **вида**,
#: а не отдельная галочка: кредит нельзя объявить условным, а поручительство — балансовым.
OBLIGATION_KINDS: dict[str, tuple[str, bool]] = {
    "credit": ("Кредит банка", False),
    "lease": ("Лизинг", False),
    "loan": ("Займ (в т.ч. участника)", False),
    "other": ("Иное балансовое обязательство", False),
    "guarantee": ("Поручительство за третье лицо", True),
    "pledge_third_party": ("Залог за третье лицо", True),
}


class Obligation(BaseModel):
    """Обязательство реестра (SPEC, Приложение Л): кредит, лизинг или условное.

    Долг в балансе — две строки-агрегата. Из них не видно ни кому должны, ни под какой
    залог, ни что будет при нарушении ковенанта, — поэтому реестр **вводится**, а не
    выводится из отчётности.

    ``rate`` и ``maturity_year`` — ``None``, когда не указаны: беспроцентный займ (0%) и
    заём без указанной ставки — разные факты, как и «погашение в 2029» против «срок в
    реестре не заполнен». ``on_demand`` — заём «по требованию»: срока нет не потому, что
    его забыли ввести, а потому, что его нет в договоре.
    """

    creditor: str = Field(default="", max_length=200)
    contract: str = Field(default="", max_length=200)
    kind: Literal["credit", "lease", "loan", "other",
                  "guarantee", "pledge_third_party"] = "credit"
    #: Остаток долга (балансовое) либо сумма условного обязательства.
    amount: Decimal = Decimal(0)
    rate: Decimal | None = None
    maturity_year: int | None = None
    on_demand: bool = False
    collateral: str = Field(default="", max_length=200)
    #: Оценка заложенного имущества. 0 — залога нет либо он не оценён.
    pledged_amount: Decimal = Decimal(0)
    #: Условие договора текстом («Долг/EBITDA ≤ 2.5×») — к нашим показателям не сводится.
    covenant: str = Field(default="", max_length=200)
    covenant_status: Literal["ok", "breached", "unknown"] = "unknown"
    covenant_note: str = Field(default="", max_length=300)

    @property
    def is_off_balance(self) -> bool:
        return OBLIGATION_KINDS[self.kind][1]

    @property
    def kind_label(self) -> str:
        return OBLIGATION_KINDS[self.kind][0]


class ProcedureMark(BaseModel):
    """Отметка аналитика по процедуре каталога (SPEC, Приложение М.3).

    Ставится **только** у процедур с исполнителем «аналитик»: итог системной процедуры
    выводится из фактического прогона, и объявить его вручную нельзя.

    ``note`` при снятии обязателен: процедура, снятая без причины, неотличима от
    забытой, а в «Границах проверки» она обязана быть названа с объяснением.
    """

    code: str = Field(default="", max_length=64)
    status: Literal["pending", "done", "skipped"] = "pending"
    note: str = Field(default="", max_length=500)


class CustomProcedure(BaseModel):
    """Своя процедура аналитика (SPEC, Приложение М.5).

    Отраслевого каталога у платформы нет — он утверждал бы, что именно проверяют в
    конкретной отрасли, а такой методики у неё нет. Процедуру, которой платформа не
    знает, пишет тот, кто знает отрасль; ведёт её аналитик.
    """

    title: str = Field(default="", max_length=300)
    status: Literal["pending", "done", "skipped"] = "pending"
    note: str = Field(default="", max_length=500)


class ValuationAssumptions(BaseModel):
    """Допущения оценки (SPEC, Приложение П): всё вводится, ничего не выводится.

    Дисконтированный поток строится по будущему, а в деле есть только прошлое.
    Экстраполировать выручку «как росла, так и будет» значило бы выдать регрессию за
    прогноз, поэтому рост, капвложения и изменение оборотного капитала задаёт человек.

    Связь с проверкой одна и главная: база прогноза — **нормализованный** EBIT
    последнего периода (Прил. К), ради чего нормализация и делалась.

    ``asking_price`` — цена продавца. ``None`` значит «не введена», и тогда дисконта
    **не существует**: величина без второго операнда — не ноль процентов.
    """

    enabled: bool = False
    horizon_years: int = Field(default=5, ge=1, le=15)
    wacc: Decimal = Decimal("0.20")
    terminal_growth: Decimal = Decimal("0.03")
    tax_rate: Decimal = Decimal("0.20")
    #: Рост показателя по годам прогноза; ряд короче горизонта — последнее значение
    #: продлевается (обнулить хвост значило бы подставить своё допущение).
    growth: list[Decimal] = Field(default_factory=list, max_length=15)
    capex: list[Decimal] = Field(default_factory=list, max_length=15)
    nwc_change: list[Decimal] = Field(default_factory=list, max_length=15)
    #: Доля миноритариев: в аналитической форме её нет, поэтому вводится.
    minority_interest: Decimal = Decimal(0)
    asking_price: Optional[Decimal] = None


class AuditSubjectModel(BaseModel):
    """Субъект анализа с фактической отчётностью по периодам.

    ``balance``/``income`` — ``{код строки: [значения по периодам]}`` (длина ряда = числу
    периодов; недостающие/лишние приводятся к ``n`` при чтении). Пустая модель инертна.
    """

    name: str = Field(default="", max_length=255)
    currency: str = Field(default="RUB", max_length=8)
    industry: str = Field(default="", max_length=120)
    # Основа отчётности (v2). Форма ввода — агрегаты, одинаковые для любого стандарта,
    # поэтому это **атрибут, а не трансформация**: платформа не пересчитывает РСБУ в МСФО,
    # но фиксирует основу, чтобы она попадала в заключение и чтобы свод группы не смешивал
    # молча отчётность, составленную по разным правилам.
    reporting_standard: Literal["rsbu", "ifrs", "management"] = "rsbu"
    periods: list[AuditPeriod] = Field(default_factory=list, max_length=48)
    balance: dict[str, list[Decimal]] = Field(default_factory=dict)
    income: dict[str, list[Decimal]] = Field(default_factory=dict)
    # Пользовательские методики (фаза G): свои показатели поверх аналитической формы.
    user_metrics: list[UserMetric] = Field(default_factory=list, max_length=100)
    # Свои нормативы (v2): переопределяют универсальные пороги; пусто — универсальные.
    thresholds: list[RatioThreshold] = Field(default_factory=list, max_length=100)
    # Переоценка статей (v2): поправки к балансу с корреспонденцией в капитале. Пустой
    # список инертен — анализ идёт по учётным данным без единого пересчёта.
    revaluations: list[Revaluation] = Field(default_factory=list, max_length=50)
    # Нормализация прибыли (фаза 4): поправки пользователя к EBIT/EBITDA. Пустой
    # список инертен — нормализованный показатель равен отчётному.
    earnings_adjustments: list[EarningsAdjustment] = Field(default_factory=list,
                                                           max_length=50)
    # Реестр обязательств и залогов (фаза 4). Пустой список инертен: реестра нет —
    # сверять и нечего, новых флагов не появляется.
    obligations: list[Obligation] = Field(default_factory=list, max_length=200)
    # Чек-лист процедур (фаза 4): отметки по каталогу + свои процедуры аналитика.
    # Пустые списки инертны — процедуры каталога остаются в статусе «не отмечено».
    procedure_marks: list[ProcedureMark] = Field(default_factory=list, max_length=200)
    custom_procedures: list[CustomProcedure] = Field(default_factory=list, max_length=100)
    # Оценка стоимости (фаза 5). `enabled=False` по умолчанию — оценка не считается,
    # пока её не включили: DCF по невведённым допущениям был бы числом из ничего.
    valuation: ValuationAssumptions = Field(default_factory=ValuationAssumptions)

    @property
    def n(self) -> int:
        return len(self.periods)

    def _row(self, table: dict[str, list[Decimal]], code: str) -> list[Decimal]:
        """Ряд строки, приведённый к числу периодов (обрезка/дополнение нулями)."""
        vals = list(table.get(code, []))[: self.n]
        while len(vals) < self.n:
            vals.append(Decimal(0))
        return vals

    def _sum_rows(self, table: dict[str, list[Decimal]], codes: list[str]) -> list[Decimal]:
        out = [Decimal(0)] * self.n
        for code in codes:
            for t, v in enumerate(self._row(table, code)):
                out[t] += v
        return out

    def total_assets(self) -> list[Decimal]:
        return self._sum_rows(self.balance, ASSET_CODES)

    def total_eqliab(self) -> list[Decimal]:
        return self._sum_rows(self.balance, EQLIAB_CODES)

    def balance_gap(self) -> list[Decimal]:
        """Актив − пассив по периодам (0 — баланс сходится)."""
        a, p = self.total_assets(), self.total_eqliab()
        return [a[t] - p[t] for t in range(self.n)]

    def is_balanced(self) -> bool:
        """Баланс сходится во всех периодах (актив = пассив)."""
        return all(g == 0 for g in self.balance_gap())

    def balance_row(self, code: str) -> list[Decimal]:
        return self._row(self.balance, code)

    def has_balance_row(self, code: str) -> bool:
        """Строка введена (а не отсутствует). «Не введено» и «введён ноль» — разные факты:
        диагностика по непредоставленным данным не считается, а не подставляет нули."""
        return bool(self.balance.get(code))

    def income_row(self, code: str) -> list[Decimal]:
        known = code in INCOME_CODES or code in INCOME_MEMO_CODES
        return self._row(self.income, code) if known else [Decimal(0)] * self.n

    def has_income_row(self, code: str) -> bool:
        """Строка ОФР введена. Как и у баланса: «не введено» ≠ «введён ноль».

        От этого зависит, существует ли EBITDA: без введённой амортизации показатель
        не считается вовсе, а не считается нулевым.
        """
        return bool(self.income.get(code))
