"""Отчётность из ГИР БО → аналитическая форма дела (пакет L, L3).

ГИР БО — государственный ресурс бухгалтерской (финансовой) отчётности ФНС: баланс и
отчёт о финансовых результатах почти всех организаций с 2019 года, построчно по кодам
форм. До этого аналитик перепечатывал формы руками или через шаблон Excel.

Модуль **чистый**: сеть живёт в ``app/girbo.py``, здесь — только разбор ответа ресурса и
сопоставление строк. Правила, и каждое называется в оговорках, которые едут с числами:

* **годы** — свои данные года берутся из его собственной отчётности; самый ранний год —
  из сравнительного столбца следующей (у ресурса нет отчётности до 2019 года). Если
  следующая отчётность пересчитала прошлый год, это названо, а взята отчётность за сам год;
* **суммы** — ресурс публикует их в тысячах рублей, дело ведётся в рублях: ×1000;
* **отнесение** — аналитическая форма агрегатная, и строки РСБУ сворачиваются в неё:
  запасы — **остаток оборотных активов** за вычетом дебиторки и денег, то есть 1210,
  НДС по приобретённым ценностям (1220), прочие оборотные (1260) и всякая строка без
  своей статьи (на настоящей отчётности встретилась 1215) — в быстрые активы их не
  считают; краткосрочные финансовые вложения (1240) — к денежным средствам (так считают
  абсолютную ликвидность); доходы будущих периодов остаются в краткосрочных
  обязательствах, как в форме;
* **подытоги отчётности сохраняются**: прибыль от продаж, до налогообложения и чистая
  выходят **ровно** такими, как в форме (налог — разность прибыли до налогообложения и
  чистой: в неё попадают и отложенный налог, и «прочее» 2460);
* **упрощённая форма** (0710096) не делит расходы: всё — в 2120, коммерческих и
  управленческих отдельно нет, нераспределённой прибыли нет — это названо;
* **амортизации** в формах нет — EBITDA не считается, пока её не введут;
* сумма статей сверяется с итогом баланса — расхождение называется, а не прячется.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

THOUSAND = Decimal(1000)
FULL_FORM = "0710099"
SIMPLIFIED_FORM = "0710096"
FORM_NAMES = {FULL_FORM: "полная", SIMPLIFIED_FORM: "упрощённая"}
#: Тип годовой отчётности в ответе ресурса (12 месяцев).
ANNUAL = 12
#: Сколько последних лет загружать по умолчанию: дело читают за пять лет, больше — шум.
DEFAULT_YEARS = 5

STATUS_NAMES = {"ACTIVE": "действующая", "INACTIVE": "недействующая"}

_TAG = re.compile(r"<[^>]+>")


def clean(text: object) -> str:
    """Строка ответа без подсветки поиска (``<strong>…</strong>``) и лишних пробелов."""
    return " ".join(_TAG.sub("", str(text or "")).split())


@dataclass
class GirboYear:
    """Год отчётности: строки РСБУ (тыс. руб.) и откуда они взяты."""

    period: str
    form: str
    #: «отчётность за 2024 год» | «сравнительные данные отчётности за 2025 год».
    source: str
    balance: dict[str, Decimal] = field(default_factory=dict)
    income: dict[str, Decimal] = field(default_factory=dict)


def _annual(report: dict) -> dict | None:
    for tc in report.get("typeCorrections") or []:
        if tc.get("type") == ANNUAL:
            return tc.get("correction") or None
    corrections = report.get("typeCorrections") or []
    return (corrections[0].get("correction") or None) if corrections else None


def _column(form: dict | None, prefix: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for key, value in (form or {}).items():
        if value is None or not key.startswith(prefix):
            continue
        code = key[len(prefix):]
        if code.isdigit():
            out[code] = Decimal(str(value))
    return out


def collect_years(reports: list[dict], *,
                  limit: int = DEFAULT_YEARS) -> tuple[list[GirboYear], list[str]]:
    """Годы из ответа ресурса — по возрастанию, не больше ``limit`` последних.

    Год без отчёта о финансовых результатах не берётся: баланс без прибыли сделал бы
    коэффициенты года нулями, которые читались бы как результат.
    """
    notes: list[str] = []
    own: dict[str, GirboYear] = {}
    comparative: dict[str, GirboYear] = {}
    for report in reports:
        period = str(report.get("period") or "")
        corr = _annual(report)
        if not period.isdigit() or corr is None:
            continue
        form = str(corr.get("knd") or report.get("knd") or "")
        balance, income = corr.get("balance"), corr.get("financialResult")
        own[period] = GirboYear(period, form, f"отчётность за {period} год",
                                _column(balance, "current"), _column(income, "current"))
        prev = str(int(period) - 1)
        comparative[prev] = GirboYear(
            prev, form, f"сравнительные данные отчётности за {period} год",
            _column(balance, "previous"), _column(income, "previous"))

    years: dict[str, GirboYear] = {}
    for period, year in own.items():
        years[period] = year
        later = comparative.get(period)
        if later is not None and _restated(year, later):
            notes.append(f"Данные {period} года в отчётности за {int(period) + 1} год "
                         f"пересчитаны — взята отчётность за сам {period} год.")
    for period, year in comparative.items():
        if period not in years and year.balance and year.income:
            years[period] = year
    complete = sorted((y for y in years.values() if y.balance and y.income),
                      key=lambda y: y.period)
    dropped = len(complete) - limit
    if dropped > 0:
        notes.append(f"Загружены последние {limit} лет; ещё {dropped} — в ресурсе.")
        complete = complete[-limit:]
    # Год из сравнительных данных называется, только если он действительно загружен.
    for year in complete:
        if year.period not in own:
            notes.append(f"{year.period} год — из сравнительных данных отчётности за "
                         f"{int(year.period) + 1} год: своей отчётности за него в ресурсе нет.")
    return complete, notes


def _restated(own: GirboYear, later: GirboYear) -> bool:
    """Пересчитала ли следующая отчётность итоги года (баланс, выручка, чистая прибыль)."""
    pairs = (("1600", own.balance, later.balance), ("2110", own.income, later.income),
             ("2400", own.income, later.income))
    return any(code in mine and code in other and mine[code] != other[code]
               for code, mine, other in pairs)


def _sum(table: dict[str, Decimal], *codes: str) -> Decimal | None:
    present = [table[c] for c in codes if c in table]
    return sum(present, Decimal(0)) if present else None


def _first(table: dict[str, Decimal], *candidates: tuple[str, ...]) -> Decimal | None:
    """Первая из альтернатив, у которой есть хоть одна строка: итог, затем слагаемые."""
    for codes in candidates:
        value = _sum(table, *codes)
        if value is not None:
            return value
    return None


def to_analytic(year: GirboYear) -> tuple[dict[str, Decimal], dict[str, Decimal], list[str]]:
    """Один год: строки РСБУ (тыс. руб.) → строки аналитической формы (руб.) и оговорки."""
    b, i = year.balance, year.income
    notes: list[str] = []
    zero = Decimal(0)

    fixed = _first(b, ("1100",), ("1110", "1120", "1130", "1140", "1150", "1160", "1170",
                                  "1180", "1190")) or zero
    receivable = _sum(b, "1230") or zero
    cash = _sum(b, "1240", "1250") or zero
    current = _first(b, ("1200",), ("1210", "1220", "1230", "1240", "1250", "1260")) or zero
    # Запасы — остаток оборотных: 1210 + 1220 + 1260 и всё, чему нет своей строки в форме.
    inventory = current - receivable - cash
    equity = _first(b, ("1300",), ("1310", "1320", "1340", "1350", "1360", "1370")) or zero
    long_ = _first(b, ("1400",), ("1410", "1420", "1430", "1450")) or zero
    short = _first(b, ("1500",), ("1510", "1520", "1530", "1540", "1550")) or zero

    total_assets = b.get("1600")
    total_liab = b.get("1700")
    if total_assets is not None and fixed + current != total_assets:
        notes.append(f"{year.period}: сумма статей актива ({_fmt(fixed + current)}) не сходится "
                     f"с итогом баланса ({_fmt(total_assets)}) — проверьте отчётность.")
    if total_liab is not None and equity + long_ + short != total_liab:
        notes.append(f"{year.period}: сумма статей пассива ({_fmt(equity + long_ + short)}) "
                     f"не сходится с итогом баланса ({_fmt(total_liab)}).")

    revenue = _sum(i, "2110") or zero
    if "2100" in i:
        cogs = revenue - i["2100"]
    else:
        cogs = _sum(i, "2120") or zero
    gross = revenue - cogs
    if "2200" in i:
        opex = gross - i["2200"]
    else:
        opex = _sum(i, "2210", "2220") or zero
    sales_profit = gross - opex
    interest = _sum(i, "2330") or zero
    if "2300" in i:
        other = i["2300"] - sales_profit + interest
    else:
        other = (_sum(i, "2310", "2320", "2340") or zero) - (_sum(i, "2350") or zero)
    pre_tax = sales_profit - interest + other
    tax = pre_tax - i["2400"] if "2400" in i else zero

    balance = {
        "A_FIXED": fixed, "A_INVENTORY": inventory, "A_RECEIVABLE": receivable,
        "A_CASH": cash, "P_EQUITY": equity, "P_LONG": long_, "P_SHORT": short,
    }
    if "1370" in b:
        balance["M_RETAINED"] = b["1370"]
    income = {
        "I_REVENUE": revenue, "I_COGS": cogs, "I_OPEX": opex, "I_INTEREST": interest,
        "I_OTHER": other, "I_TAX": tax,
    }
    return ({k: v * THOUSAND for k, v in balance.items()},
            {k: v * THOUSAND for k, v in income.items()}, notes)


def _fmt(value: Decimal) -> str:
    return f"{value:,.0f}".replace(",", " ") + " тыс. ₽"


def _date(text: object) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


def _address(org: dict) -> str:
    parts = [org.get("index"), org.get("region"), org.get("city") or org.get("settlement"),
             org.get("street"), org.get("house") and f"д. {org['house']}",
             org.get("building") and f"корп. {org['building']}",
             org.get("office") and f"пом. {org['office']}"]
    return ", ".join(clean(p) for p in parts if p)


def _okved(org: dict) -> str:
    okved = org.get("okved2")
    if isinstance(okved, dict):
        return " — ".join(clean(x) for x in (okved.get("id"), okved.get("name")) if x)
    return clean(okved)


@dataclass
class GirboImport:
    """Отчётность дела из ГИР БО: строки аналитической формы по годам и снимок реестра."""

    periods: list[str]
    forms: list[str]
    sources: list[str]
    balance: dict[str, list[Decimal]]
    income: dict[str, list[Decimal]]
    registry: dict
    notes: list[str]


#: Что сказано всегда: откуда числа и чего они не значат.
ALWAYS = [
    "Источник — ГИР БО (ресурс бухгалтерской отчётности ФНС, bo.nalog.gov.ru): это "
    "отчётность, которую организация сдала сама; аудиторскую проверку она не означает.",
    "Суммы в ресурсе — в тысячах рублей; в деле — в рублях (×1000).",
    "Отнесение строк: НДС по приобретённым ценностям (1220), прочие оборотные активы "
    "(1260) и строки оборотных активов без своей статьи в аналитической форме (например, "
    "1215) — к запасам: в быстрые активы их не считают; краткосрочные финансовые "
    "вложения (1240) — к денежным средствам. Прибыль от продаж, до налогообложения и "
    "чистая совпадают с формой.",
    "Амортизации в формах нет — EBITDA не считается, пока её не введут.",
]


def build_import(org: dict, reports: list[dict], *, today: date,
                 limit: int = DEFAULT_YEARS) -> GirboImport:
    """Собрать загрузку из ответов ресурса: карточки организации и списка отчётностей."""
    years, notes = collect_years(reports, limit=limit)
    periods = [y.period for y in years]
    balance: dict[str, list[Decimal]] = {}
    income: dict[str, list[Decimal]] = {}
    simplified = [y.period for y in years if y.form == SIMPLIFIED_FORM]
    if simplified:
        notes.append(f"Упрощённая форма ({', '.join(simplified)}): расходы по обычной "
                     "деятельности одной строкой (2120) — коммерческие и управленческие "
                     "отдельно не показаны и стоят в себестоимости.")
    for t, year in enumerate(years):
        bal, inc, year_notes = to_analytic(year)
        notes.extend(year_notes)
        for table, values in ((balance, bal), (income, inc)):
            for code, value in values.items():
                table.setdefault(code, [Decimal(0)] * len(years))[t] = value
    if years and "M_RETAINED" not in balance:
        notes.append("Нераспределённой прибыли (1370) в загруженной отчётности нет — модели "
                     "Альтмана не считаются, пока её не введут.")
    status = clean(org.get("statusCode"))
    since = _date(org.get("statusDate"))
    registry = {
        "source": "girbo", "fetched_on": today.isoformat(),
        "inn": clean(org.get("inn")), "ogrn": clean(org.get("ogrn")),
        "kpp": clean(org.get("kpp")),
        "full_name": clean(org.get("fullName")) or clean(org.get("shortName")),
        "short_name": clean(org.get("shortName")), "address": _address(org),
        "okved": _okved(org), "status_code": status,
        "status_date": since.isoformat() if since else None,
        "periods": periods, "notes": ALWAYS + notes,
    }
    return GirboImport(periods=periods, forms=[FORM_NAMES.get(y.form, y.form) for y in years],
                       sources=[y.source for y in years], balance=balance, income=income,
                       registry=registry, notes=ALWAYS + notes)


def status_label(code: str) -> str:
    """Статус словами; неизвестный код — как есть, а не «действующая» по умолчанию."""
    return STATUS_NAMES.get(code, f"статус «{code}»" if code else "статус не указан")
