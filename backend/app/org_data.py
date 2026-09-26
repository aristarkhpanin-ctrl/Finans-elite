"""Организация может забрать всё и уйти (ADMIN-PHASE-F, F6).

У человека права 152-ФЗ закрыты (C3): он забирает свои данные и удаляет учётную запись.
У **организации** не было ни того, ни другого. Выгрузка существовала только по одному
проекту или делу, а удалить компанию было нельзя вовсе: единственный путь к
:func:`personal_data._purge_organization` шёл через удаление её последнего владельца —
то есть закрыть компанию можно было, только уничтожив заодно чью-то учётную запись.

Отсюда два обещания, которые платформа обязана держать не на словах:

1. **Забрать всё.** Один файл: организация, участники, подписки и платежи, проекты
   с моделями целиком, дела, группы, ориентиры, чек-листы, обсуждения, журнал. Файл
   **объясняет себя сам** первым блоком и **называет своё обрезание** — молча урезанная
   выгрузка выглядит как полная, и обнаруживается это уже у клиента.
2. **Уйти.** Предпросмотр говорит, что именно исчезнет, — и собирается **заново** перед
   самим удалением (правило C3): между «показали» и «сделали» проходит время, за
   которое кто-то мог завести ещё десять проектов.

**Участники не удаляются** — исчезает их членство. Человек состоит и в других компаниях,
и его учётная запись не принадлежит ни одной из них; у кого эта организация была
единственной, тот останется без организаций, и предпросмотр говорит это числом.

Функции здесь **читают и собирают**; само стирание идёт общим
:func:`personal_data._purge_organization` — второго порядка удаления не заводим, иначе
один из двух однажды отстанет от новой таблицы (а один уже отставал — F6 нашла шесть).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import apikeys, crud
from .database import as_tenant
from .db_models import (
    ApiKey,
    AuditChecklist,
    AuditGroup,
    AuditSubject,
    Comment,
    IndustryBenchmark,
    Organization,
    Project,
    SupportGrant,
)
from .personal_data import KEPT_AFTER_ORGANIZATION, _iso, _purge_organization
from .plans import get_plan

#: Сколько записей журнала кладём в выгрузку организации. Тот же довод, что и у
#: выгрузки человека: предел назван, и файл **говорит о своей неполноте**.
MAX_EXPORT_LOG = 20_000


def _count(db: Session, model, org_id: str) -> int:
    """Сколько строк этой таблицы у организации. Зовётся внутри арендатора."""
    return int(db.scalar(select(func.count()).select_from(model)
                         .where(model.organization_id == org_id)) or 0)


def build_export(db: Session, org: Organization) -> dict:
    """Всё, что принадлежит организации, — одним файлом.

    Первым блоком идёт объяснение, что внутри и чего внутри нет: файл уедет к клиенту
    без нас, и приложить оговорку к нему больше будет негде. Модели проектов и дел идут
    **целиком** — это и есть то, ради чего выгрузку просят.
    """
    org_id = org.id
    with as_tenant(db, org_id):
        projects = list(db.scalars(select(Project).where(
            Project.organization_id == org_id).order_by(Project.created_at)))
        cases = list(db.scalars(select(AuditSubject).where(
            AuditSubject.organization_id == org_id).order_by(AuditSubject.created_at)))
        groups = list(db.scalars(select(AuditGroup).where(
            AuditGroup.organization_id == org_id).order_by(AuditGroup.created_at)))
        benchmarks = list(db.scalars(select(IndustryBenchmark).where(
            IndustryBenchmark.organization_id == org_id)))
        checklists = list(db.scalars(select(AuditChecklist).where(
            AuditChecklist.organization_id == org_id)))
        keys = list(db.scalars(select(ApiKey).where(ApiKey.organization_id == org_id)))
        grants = list(db.scalars(select(SupportGrant).where(
            SupportGrant.organization_id == org_id).order_by(SupportGrant.created_at)))
        comments = list(db.scalars(select(Comment).where(
            Comment.organization_id == org_id).order_by(Comment.created_at)))
        log_total = crud.count_audit_log(db, org_id)
        log = crud.list_audit_log(db, org_id, limit=MAX_EXPORT_LOG)
        members = crud.list_members(db, org_id)

    about = [
        "Здесь всё, что платформа хранит для этой организации: состав, подписки и "
        "платежи, проекты и дела с моделями целиком, группы, ориентиры, чек-листы, "
        "обсуждения и журнал доступа.",
        "Результатов расчётов внутри нет: они не хранятся, а считаются из модели — и "
        "будут посчитаны заново, где бы модель ни открыли. Отчёты в виде таблиц и "
        "документов выгружаются с экранов проектов и дел.",
        "Файлов внутри нет, потому что платформа их не хранит вовсе: в обсуждениях "
        "сохранены только ссылки на вашу комнату данных, а не сами материалы.",
        "Секретов ключей доступа к API внутри нет: платформа хранит лишь их отпечатки "
        "и показать сам ключ не может — ни вам, ни себе.",
        "Учётные записи участников здесь не выгружаются — они принадлежат людям, а не "
        "организации. Свои данные каждый забирает сам в профиле.",
    ]
    if log_total > len(log):
        about.append(f"Записей журнала {log_total}, в файл вошли последние {len(log)}: "
                     f"остальные видны на вкладке «Журнал доступа».")

    return {
        "о_выгрузке": {
            "составлена": _iso(datetime.now(timezone.utc)),
            "что_внутри": about,
        },
        "организация": {
            "название": org.name,
            "создана": _iso(org.created_at),
            "приостановлена": _iso(org.suspended_at),
            "причина_приостановки": org.suspend_reason or None,
        },
        "подписки": [
            {
                "продукт": s.product,
                "тариф": get_plan(s.plan_code, s.product).name,
                "код_тарифа": s.plan_code,
                "состояние": s.status,
                "оплачено_до": _iso(s.current_period_end),
            }
            for s in crud.list_subscriptions(db, org_id)
        ],
        "платежи": [
            {
                "когда": _iso(p.created_at),
                "тариф": p.plan_code,
                "сумма_руб": p.amount_rub,
                "состояние": p.status,
                "провайдер": p.provider,
            }
            # Без арендатора и с фильтром: у `payments` нет RLS-политики намеренно (F2).
            for p in crud.list_payments(db, org_id, limit=MAX_EXPORT_LOG)
        ],
        "участники": [
            {
                "адрес": u.email,
                "имя": u.full_name,
                "роль": m.role,
                "участник_с": _iso(m.created_at),
                "последнее_обращение": _iso(m.last_seen_at),
                "доступ_приостановлен": _iso(m.blocked_at),
            }
            for m, u in members
        ],
        "проекты": [
            {
                "название": p.name,
                "создан": _iso(p.created_at),
                "изменён": _iso(p.updated_at),
                "статус": p.status,
                "модель": p.model,
            }
            for p in projects
        ],
        "дела": [
            {
                "название": s.name,
                "создано": _iso(s.created_at),
                "изменено": _iso(s.updated_at),
                "модель": s.model,
            }
            for s in cases
        ],
        "группы_предприятий": [
            {"название": g.name, "создана": _iso(g.created_at), "состав": g.model}
            for g in groups
        ],
        "отраслевые_ориентиры": [
            {"отрасль": b.industry, "база": b.metric, "значение": b.value,
             "источник": b.source, "обновлён": _iso(b.updated_at)}
            for b in benchmarks
        ],
        "чек_листы": [
            {"название": c.name, "область": c.scope, "процедуры": c.items,
             "автор": c.author_email}
            for c in checklists
        ],
        "ключи_доступа": [
            {"имя": k.name, "видимая_часть": apikeys.masked(k.prefix),
             "завёл": k.created_by, "создан": _iso(k.created_at),
             "последнее_обращение": _iso(k.last_used_at), "отозван": _iso(k.revoked_at)}
            for k in keys
        ],
        "доступ_поддержки": [
            {"открыл": g.granted_by_email, "причина": g.reason,
             "открыт": _iso(g.created_at), "до": _iso(g.expires_at),
             "закрыт": _iso(g.revoked_at)}
            for g in grants
        ],
        "обсуждения": [
            {
                "когда": _iso(c.created_at),
                "автор": c.author_email,
                "о_чём_речь": c.subject_type,
                "место": c.anchor_label or c.anchor,
                "текст": c.body,
                "удалена": _iso(c.deleted_at),
            }
            for c in comments
        ],
        "журнал_доступа": [
            {
                "когда": _iso(e.created_at),
                "кто": e.actor_email,
                "действие": e.action,
                "над_чем": e.entity_name or e.entity_type,
                "через_ключ": e.via_key or None,
                "примечание": e.details,
            }
            for e in log
        ],
    }


@dataclass
class OrgDeletionPlan:
    """Что исчезнет вместе с организацией — **до** нажатия кнопки.

    Удаление необратимо и задевает не только того, кто нажимает: вместе с организацией
    уходят модели всех её проектов и дел, а участники теряют рабочее пространство.
    Показать это числами — не вежливость, а единственный способ дать согласие осознанно.
    """

    name: str = ""
    projects: int = 0
    cases: int = 0
    groups: int = 0
    members: int = 0
    #: Сколько участников останутся **без единой организации**: для них это не «выход
    #: из компании», а пустой продукт при следующем входе.
    members_left_homeless: int = 0
    comments: int = 0
    log_entries: int = 0
    api_keys: int = 0
    #: Что останется после удаления — и почему. Пустым не бывает.
    kept: list[str] = field(default_factory=list)
    #: Что мешает. Пусто — удалять можно.
    blockers: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return not self.blockers


def deletion_plan(db: Session, org: Organization) -> OrgDeletionPlan:
    """Собрать план удаления организации: что исчезнет, что останется, что мешает.

    Препятствий у владельца **нет** и по замыслу быть не должно: уйти — его право, и
    удерживать компанию оплаченным периодом или открытым доступом значило бы держать
    данные в заложниках (правило 7 пакета). Всё, что могло бы стать препятствием,
    названо в ``kept`` как предупреждение, а не как запрет.
    """
    org_id = org.id
    plan = OrgDeletionPlan(name=org.name)
    members = crud.list_members(db, org_id)
    plan.members = len(members)
    for _membership, user in members:
        if len(crud.list_user_memberships(db, user.id)) == 1:
            plan.members_left_homeless += 1

    with as_tenant(db, org_id):
        plan.projects = crud.count_projects(db, org_id)
        plan.cases = crud.count_audit_subjects(db, org_id)
        plan.groups = _count(db, AuditGroup, org_id)
        plan.comments = _count(db, Comment, org_id)
        plan.api_keys = _count(db, ApiKey, org_id)
        plan.log_entries = crud.count_audit_log(db, org_id)

    plan.kept = [
        "Учётные записи участников: они принадлежат людям, а не организации. "
        + (f"У {plan.members_left_homeless} из них это единственная организация — "
           "после удаления они войдут в пустой продукт."
           if plan.members_left_homeless else "Все они состоят и в других организациях."),
        "Записи служебного журнала платформы о визитах её сотрудников к вам: "
        "это её собственность, а не ваша, — иначе уход клиента стирал бы её "
        "собственную подотчётность.",
        "Платёжные документы у платёжного провайдера: платформа ими не распоряжается. "
        "Оплаченный, но не использованный период при удалении не возвращается.",
    ]
    return plan


def delete_organization(db: Session, org: Organization) -> OrgDeletionPlan:
    """Удалить организацию. План собирается **заново** — и возвращается как отчёт.

    Между предпросмотром и нажатием проходит время, за которое кто-то мог завести ещё
    десять проектов: показать одно, а стереть другое — худший исход необратимого
    действия (правило C3, здесь оно же).

    Само стирание — общий :func:`personal_data._purge_organization`: второго порядка
    удаления не заводим.
    """
    plan = deletion_plan(db, org)
    if not plan.allowed:
        raise ValueError("удаление невозможно: есть препятствия")
    _purge_organization(db, org.id)
    return plan


#: Что уход клиента **не стирает** — перечень из `personal_data`, а не его копия здесь.
KEPT_TABLES = KEPT_AFTER_ORGANIZATION
