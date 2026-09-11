"""Обсуждение рядом с числами: комментарии к проекту и к делу (ADMIN-DECOMPOSITION, D3).

Один роутер на оба продукта: обсуждение у проекта и у дела устроено одинаково, и вторая
копия этих правил разошлась бы с первой — тот же довод, что у общей таблицы. Различаются
только дверь (право на сущность) и продукт, чья подписка отвечает за маршрут.

**Комментарий привязан к месту.** «Обсуждение проекта» — это чат, из которого через месяц
не понять, о какой строке шла речь. Место (`anchor`) и его подпись **на момент написания**
приходят с экрана: он один знает, на что смотрел человек.

**Упоминание не даёт прав.** Оно зовёт посмотреть; открыть проект решает роль в
организации. Упомянуть можно только участника своей организации — чужой адрес это либо
утечка (он уедет в письмо), либо ложь (никто не придёт).

**Письмо об упоминании — только там, где почта настроена** (D1), и ответ об этом
говорит: обещание «мы позвали» в установке без почты некому выполнить.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..comments import check_body, parse_mentions, visible_body
from ..database import get_db
from ..db_models import Comment, User
from ..deps import current_user, require_permission
from ..mail import Letter, mail_enabled, public_url
from ..notify import send_and_log
from ..rbac import Perm, has_permission
from ..schemas import CommentCreate, CommentCreated, CommentOut, MailReport

router = APIRouter(prefix="/api/v1", tags=["comments"])


def _out(comment: Comment) -> CommentOut:
    return CommentOut(
        id=comment.id, subject_type=comment.subject_type, subject_id=comment.subject_id,
        anchor=comment.anchor, anchor_label=comment.anchor_label,
        author_email=comment.author_email, author_name=comment.author_name,
        body=visible_body(comment),
        mentions=[m for m in comment.mentions.split(",") if m],
        created_at=comment.created_at,
        resolved=comment.resolved_at is not None, resolved_at=comment.resolved_at,
        resolved_by=comment.resolved_by, deleted=comment.deleted_at is not None,
    )


def _subject_or_404(db: Session, org_id: str, subject_type: str, subject_id: str) -> str:
    """Проверить, что сущность существует **в этой организации**, и вернуть её имя.

    Комментарий к чужому проекту невозможен не потому, что так вежливее: без проверки
    обсуждение стало бы способом писать в чужую организацию, минуя её права.
    """
    if subject_type == "project":
        subject = crud.get_project(db, org_id, subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="Проект не найден")
        return subject.name
    subject = crud.get_audit_subject(db, org_id, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    return subject.name


def _mention_letter(*, author: str, subject_name: str, where: str, body: str,
                    link: str) -> Letter:
    """Письмо об упоминании. Текст реплики внутри — иначе письмо заставляет открыть
    систему, чтобы узнать, стоило ли её открывать."""
    return Letter(
        subject=f"Вас упомянули: {subject_name} — Финанс-Элит",
        text=(f"{author} упомянул вас в обсуждении «{subject_name}»"
              + (f", раздел «{where}»" if where else "") + ":\n\n"
              f"{body}\n\n"
              + (f"Открыть: {link}\n\n" if link else "")
              + "Упоминание не открывает доступ: если раздела не видно, попросите права "
                "у администратора организации."
              "\n\n—\nЭто письмо отправила платформа «Финанс-Элит».\n"
              "Отвечать на него бесполезно: ящик входящие письма не принимает."),
    )


def _create(db: Session, background: BackgroundTasks, *, org_id: str, author: User,
            subject_type: str, subject_id: str, body: CommentCreate) -> CommentCreated:
    """Общее тело для обоих продуктов: правила у обсуждения одни."""
    subject_name = _subject_or_404(db, org_id, subject_type, subject_id)
    problem = check_body(body.body)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    members = {u.email.lower(): u.email for _, u in crud.list_members(db, org_id)}
    mentions = parse_mentions(body.body, members)
    if mentions.too_many:
        raise HTTPException(
            status_code=422,
            detail="Слишком много упоминаний в одной реплике — это уже рассылка, "
                   "а не разговор.")
    # Себя в списке позванных не держим: письмо самому себе о собственной реплике —
    # шум, из-за которого перестают читать остальные.
    called = [m for m in mentions.known if m.lower() != (author.email or "").lower()]

    comment = crud.create_comment(
        db, org_id, subject_type=subject_type, subject_id=subject_id, author=author,
        body=body.body.strip(), anchor=body.anchor, anchor_label=body.anchor_label,
        mentions=called)

    report = MailReport()
    if called and mail_enabled():
        base = public_url()
        path = (f"/projects/{subject_id}" if subject_type == "project"
                else f"/audit/subjects/{subject_id}")
        letter = _mention_letter(
            author=author.email, subject_name=subject_name,
            where=body.anchor_label, body=body.body.strip(),
            link=f"{base}{path}" if base else "")
        for email in called:
            target = crud.get_user_by_email(db, email)
            if target is not None:
                background.add_task(send_and_log, db.get_bind(), target.id, email,
                                    letter, "comment.mention_mail")
        # Отправка идёт после ответа, поэтому её исход здесь ещё не известен: обещаем
        # только то, что письма **поставлены в очередь**, а результат каждого уходит в
        # журнал того, кого позвали.
        report = MailReport(attempted=True, ok=True)
    return CommentCreated(comment=_out(comment), notified=called,
                          unknown_mentions=mentions.unknown, mail=report)


# --- Проект («Финанс-Элит») ---

@router.get("/projects/{project_id}/comments", response_model=list[CommentOut])
def list_project_comments(project_id: str, anchor: str | None = None,
                          org_id: str = Depends(require_permission(Perm.PROJECT_READ)),
                          db: Session = Depends(get_db)) -> list[CommentOut]:
    """Обсуждение проекта, старые сверху. ``anchor`` сужает до одного места."""
    _subject_or_404(db, org_id, "project", project_id)
    return [_out(c) for c in crud.list_comments(db, org_id, "project", project_id,
                                                anchor=anchor)]


@router.post("/projects/{project_id}/comments", response_model=CommentCreated,
             status_code=status.HTTP_201_CREATED)
def add_project_comment(project_id: str, body: CommentCreate,
                        background: BackgroundTasks,
                        org_id: str = Depends(require_permission(Perm.COMMENT_WRITE)),
                        author: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> CommentCreated:
    """Написать реплику в обсуждении проекта."""
    return _create(db, background, org_id=org_id, author=author, subject_type="project",
                   subject_id=project_id, body=body)


# --- Дело («Финанс-Аудит») ---

@router.get("/audit/subjects/{subject_id}/comments", response_model=list[CommentOut])
def list_case_comments(
    subject_id: str, anchor: str | None = None,
    org_id: str = Depends(require_permission(Perm.PROJECT_READ, product="audit")),
    db: Session = Depends(get_db),
) -> list[CommentOut]:
    """Обсуждение дела, старые сверху."""
    _subject_or_404(db, org_id, "case", subject_id)
    return [_out(c) for c in crud.list_comments(db, org_id, "case", subject_id,
                                                anchor=anchor)]


@router.post("/audit/subjects/{subject_id}/comments", response_model=CommentCreated,
             status_code=status.HTTP_201_CREATED)
def add_case_comment(
    subject_id: str, body: CommentCreate, background: BackgroundTasks,
    org_id: str = Depends(require_permission(Perm.COMMENT_WRITE, product="audit")),
    author: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CommentCreated:
    """Написать реплику в обсуждении дела."""
    return _create(db, background, org_id=org_id, author=author, subject_type="case",
                   subject_id=subject_id, body=body)


# --- Общие действия над репликой ---

def _comment_or_404(db: Session, org_id: str, comment_id: str) -> Comment:
    comment = crud.get_comment(db, org_id, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Реплика не найдена")
    return comment


@router.post("/comments/{comment_id}/resolve", response_model=CommentOut)
def resolve(comment_id: str,
            org_id: str = Depends(require_permission(Perm.COMMENT_WRITE)),
            actor: User = Depends(current_user),
            db: Session = Depends(get_db)) -> CommentOut:
    """Закрыть обсуждение: вопрос снят.

    Закрыть может **любой участник**, а не только автор: снимает вопрос обычно тот, кто
    на него ответил. Кто именно — записано: «вопрос снят» без имени снявшего это не
    ответ, а тишина.
    """
    comment = _comment_or_404(db, org_id, comment_id)
    if comment.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Реплика удалена: закрывать нечего")
    return _out(crud.resolve_comment(db, comment, by=actor.email))


@router.delete("/comments/{comment_id}/resolve", response_model=CommentOut)
def reopen(comment_id: str,
           org_id: str = Depends(require_permission(Perm.COMMENT_WRITE)),
           db: Session = Depends(get_db)) -> CommentOut:
    """Открыть обсуждение заново: вопрос сняли рано."""
    comment = _comment_or_404(db, org_id, comment_id)
    return _out(crud.resolve_comment(db, comment, by="", resolved=False))


@router.delete("/comments/{comment_id}", response_model=CommentOut)
def delete(comment_id: str,
           org_id: str = Depends(require_permission(Perm.COMMENT_WRITE)),
           actor: User = Depends(current_user),
           db: Session = Depends(get_db)) -> CommentOut:
    """Удалить реплику — свою или, если вы администратор, чужую.

    Текст стирается, но **«надгробие» остаётся**: пропавшая без следа строка читается как
    не сказанная никогда, а на неё уже могли ответить. Своё удаление и административное
    названы по-разному — «удалена автором» под чужим решением приписало бы его человеку.

    Правки текста нет вовсе: отредактированная реплика, на которую ответили, переписывает
    историю — спор становится непонятным, а согласие приписанным.
    """
    comment = _comment_or_404(db, org_id, comment_id)
    mine = comment.author_id == actor.id
    role = crud.get_role(db, org_id, actor.id)
    if not mine and not has_permission(role, Perm.MEMBER_MANAGE):
        raise HTTPException(
            status_code=403,
            detail="Удалить чужую реплику может только администратор организации.")
    if comment.deleted_at is not None:
        return _out(comment)
    return _out(crud.delete_comment(db, comment, by=actor.email))
