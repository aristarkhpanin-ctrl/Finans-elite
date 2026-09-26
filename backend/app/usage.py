"""События пользования продуктом (NEXT-STEPS.md, E2).

Платформа не записывала **ни одного** события пользования: журнал по правилу пакета A→D
не пишет чтение, а отметка присутствия хранит только последнее значение. Из-за этого
«сколько раз открывали результаты» не знал никто, а удержание (вернулся ли человек через
неделю) не считалось вовсе — истории присутствия нет. Дашборд поверх такой пустоты
показал бы три числа и соврал про остальные, а соврать графиком дороже, чем цифрой.

**Это не журнал, и путать их нельзя.** Журнал отвечает **клиенту** на вопрос «кто это
сделал», не пишет чтение и хранится долго. События отвечают **платформе** на вопрос «как
пользуются», пишут именно чтение и живут ровно столько, сколько нужно для ответа. Одна
таблица на два вопроса означала бы, что в журнале тонет сигнал, а в событиях появляются
персональные данные.

Четыре правила, без которых слой заводить нельзя:

1. **Перечень событий закрыт** (:data:`EVENTS`) — и **каждое событие в нём кто-то
   пишет**. Свободные «произвольные события» превращают таблицу в свалку, из которой
   ничего нельзя доказать; событие, которого никто не пишет, — обещание данных, которые
   не придут никогда. И то и другое стережёт перечень-тест. Так из перечня уже выпало
   «открыл результаты»: отдельного маршрута у экрана результатов нет, он зовёт расчёт —
   и событие было бы вторым именем того же самого.
2. **Ни одного числа из модели клиента.** Правило 6 пакета A→D («оператор платформы не
   читает модели») действует и здесь: «посчитал проект» — да, «посчитал проект с NPV =
   X» — нет. Проверяется перечнем разрешённых ключей контекста.
3. **Участник обезличен.** В событии лежит не почта, а её отпечаток с солью установки:
   для когорт («тот же человек вернулся») этого достаточно, а для «кто именно» — нет.
   Обратно отпечаток не разворачивается: соль не хранится рядом с данными.
4. **Рубильник и срок.** Сбор выключается одной переменной; события старше срока чистит
   эксплуатация — как и журнал. Код, умеющий стирать свои следы, их не охраняет.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import Organization, UsageEvent

#: Закрытый перечень событий: код → что он означает. Ключи стабильны — на них ссылаются
#: сводка платформы и выгрузка.
EVENTS: dict[str, str] = {
    "signup": "зарегистрировался (создана организация)",
    "project.create": "завёл проект",
    "project.open": "открыл проект в редакторе",
    "project.calculate": "посчитал проект",
    "project.export": "выгрузил документ или таблицу",
    "case.create": "завёл дело",
    "case.analyze": "разобрал дело",
    "case.report": "выгрузил заключение",
    "member.invite": "пригласил участника",
    "billing.paid": "оплатил тариф",
}

#: Что можно класть в контекст события. Всё остальное отбрасывается: контекст свободной
#: формы — самая короткая дорога к числам клиента в аналитике платформы.
CONTEXT_KEYS = frozenset({"product", "template", "source", "plan"})

#: Длина отпечатка участника. 16 знаков — достаточно, чтобы когорты не слипались, и
#: коротко, чтобы никто не принял его за идентификатор человека.
FINGERPRINT_LEN = 16


def collecting() -> bool:
    """Собираем ли события. Читается на каждом вызове: рубильник выключают на ходу.

    По умолчанию **выключено**. Сбор данных о пользовании — решение владельца установки,
    а не значение по умолчанию: включённый молча, он превращает продукт в то, чего его
    покупатель не заказывал.
    """
    return os.getenv("USAGE_EVENTS", "").strip().lower() in {"1", "true", "yes", "on"}


def _salt() -> str:
    """Соль отпечатка участника. Без неё отпечаток — это словарь почт, а не анонимность."""
    return os.getenv("USAGE_SALT", "") or os.getenv("JWT_SECRET", "dev-secret-change-me")


def fingerprint(email: str) -> str:
    """Отпечаток участника: «тот же человек» — да, «кто именно» — нет.

    Обратно не разворачивается: соль установки не лежит рядом с событиями, а без неё
    перебор почт ничего не даёт. Пустой адрес → пустой отпечаток: событие без человека
    (системное) не притворяется чьим-то.
    """
    if not email:
        return ""
    digest = hashlib.sha256(f"{_salt()}:{email.strip().lower()}".encode("utf-8"))
    return digest.hexdigest()[:FINGERPRINT_LEN]


def clean_context(context: dict | None) -> dict:
    """Оставить только разрешённые ключи и привести значения к коротким строкам.

    Числа из модели клиента сюда не попадут: ключа под них нет, а значение обрезается до
    64 знаков — в такую строку не уместить ни ряда, ни отчёта.
    """
    if not context:
        return {}
    return {k: str(v)[:64] for k, v in context.items() if k in CONTEXT_KEYS}


def record(db: Session, *, event: str, org_id: str, email: str = "",
           context: dict | None = None, now: datetime | None = None) -> UsageEvent | None:
    """Записать событие пользования. Возвращает ``None``, если сбор выключен.

    **Не бросает исключений и ничего не ломает**: аналитика стоит в стороне от работы
    пользователя, и падение записи события не должно ронять то, ради чего он пришёл.
    Неизвестное событие не пишется вовсе — перечень закрыт, и «почти правильный» код
    события хуже отсутствующего.
    """
    if not collecting() or event not in EVENTS:
        return None
    row = UsageEvent(
        organization_id=org_id, event=event, actor=fingerprint(email),
        context=clean_context(context),
        created_at=now or datetime.now(timezone.utc),
    )
    try:
        db.add(row)
        db.commit()
    except Exception:                                   # noqa: BLE001 — см. docstring
        db.rollback()
        return None
    return row


# --- Сводка событий на выгрузку (OPEN-DECISIONS §7) ---
#
# Выгружается **агрегат, в котором участника нет вовсе**: месяц, код события,
# организация, число. Отпечаток нужен платформе **внутри**, чтобы ответить «тот же
# человек вернулся»; в файле он не нужен ни для одного вопроса, а вне платформы отпечаток
# с солью рано или поздно соединят с чем-то ещё — и обезличенность кончится. Поэтому из
# отпечатков в файл уходит только **их количество** — «сколько разных людей», а не «какие».


@dataclass(frozen=True)
class UsageRow:
    """Строка сводки: что происходило в одной организации в одном месяце."""

    month: str
    event: str
    #: Имя организации **на момент выгрузки** и её идентификатор: имя читают, а по
    #: идентификатору сходятся строки разных выгрузок, если организацию переименовали.
    organization_id: str
    organization: str
    count: int
    #: Сколько **разных** участников — производная от отпечатков, а не отпечаток.
    #: «Десять событий от одного человека» и «десять от десяти» — разные факты, и без
    #: этого числа их не различить.
    participants: int


@dataclass
class UsageSummary:
    """Сводка событий: строки, помесячные итоги и **границы их применимости**."""

    generated_at: datetime
    months: int
    rows: list[UsageRow] = field(default_factory=list)
    #: Итог по месяцам — рядом, и **с нулями**: пропущенный месяц в ряду читается как
    #: потерянные данные, а ноль в нём — это ответ.
    monthly: list[tuple[str, int]] = field(default_factory=list)
    #: Когда записано самое первое событие — **по всем** событиям, а не по окну: окно
    #: сужает выдачу, а «собираем с такого-то числа» обязано остаться правдой.
    #: ``None`` — событий нет вовсе.
    first_event_at: datetime | None = None
    collecting: bool = False
    notes: list[str] = field(default_factory=list)


def _month_key(value: datetime) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _months_back(now: datetime, months: int) -> list[str]:
    """Последние ``months`` месяцев, включая текущий, старые сверху."""
    out: list[str] = []
    year, month = now.year, now.month
    for _ in range(months):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


def summarize(db: Session, *, now: datetime | None = None,
              months: int = 12) -> UsageSummary:
    """Собрать сводку событий за последние ``months`` месяцев.

    Группировка — **в Python**, а не выражением SQL: помесячная свёртка на диалекте
    прошла бы тесты на SQLite и разошлась бы с PostgreSQL молча (тот же довод, что в
    сводке платформы).

    Организации называются по имени: файл читает владелец установки, который и так видит
    их в служебном разделе. Содержимого моделей здесь нет и быть не может — его нет в
    самих событиях.
    """
    now = now or datetime.now(timezone.utc)
    window = set(_months_back(now, months))
    names = {o.id: o.name for o in db.execute(select(Organization)).scalars()}

    counts: dict[tuple[str, str, str], int] = {}
    actors: dict[tuple[str, str, str], set[str]] = {}
    monthly: dict[str, int] = {m: 0 for m in window}
    first: datetime | None = None
    for org_id, event, actor, created in db.execute(
            select(UsageEvent.organization_id, UsageEvent.event, UsageEvent.actor,
                   UsageEvent.created_at)).all():
        stamp = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        if first is None or stamp < first:
            first = stamp
        month = _month_key(stamp)
        if month not in window:
            continue
        key = (month, event, org_id)
        counts[key] = counts.get(key, 0) + 1
        if actor:
            actors.setdefault(key, set()).add(actor)
        monthly[month] += 1

    rows = [
        UsageRow(month=month, event=event, organization_id=org_id,
                 organization=names.get(org_id, ""), count=count,
                 participants=len(actors.get((month, event, org_id), ())))
        for (month, event, org_id), count in sorted(counts.items())
    ]
    summary = UsageSummary(generated_at=now, months=months, rows=rows,
                           monthly=sorted(monthly.items()), first_event_at=first,
                           collecting=collecting())
    summary.notes = _summary_notes(summary)
    return summary


def _summary_notes(summary: UsageSummary) -> list[str]:
    """Чего эта выгрузка **не** значит. Едет в самом файле, а не остаётся на экране:
    таблица, доехавшая до чужой презентации без оговорок, утверждает больше, чем
    платформа измеряла."""
    notes = [
        "Участника в этой выгрузке нет вовсе: ни почты, ни отпечатка. «Участников» — "
        "это сколько разных людей стоит за числом, а не кто они.",
        "Это не журнал действий. Журнал отвечает организации «кто это сделал» и не "
        "пишет чтение; здесь наоборот — платформа считает, как пользуются, и чтение "
        "считает тоже.",
        "Чисел из моделей клиентов здесь нет: их нет и в самих событиях — перечень "
        "того, что попадает в событие, закрыт.",
        "Строки есть только там, где события были: отсутствие строки — это ноль. "
        "Помесячный итог, наоборот, идёт со всеми месяцами окна, включая нулевые.",
    ]
    if summary.first_event_at is None:
        notes.append(
            "Событий не записано ни одного. Это не значит «никто не пользовался»: "
            "сбор включается рубильником установки, и до его включения не пишется ничего.")
    else:
        notes.append(
            f"Первое событие записано {summary.first_event_at.strftime('%d.%m.%Y')}. "
            "Раньше этой даты ноль означает «не записывали», а не «не пользовались».")
    notes.append(
        "Сбор событий сейчас включён: ряд продолжается." if summary.collecting else
        "Сбор событий сейчас выключен — новые события не пишутся. На части периода он "
        "тоже мог быть выключен, и провал в ряду это не отсутствие работы.")
    return notes
