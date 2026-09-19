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

**Подписка на ветку вместо дайджеста** (OPEN-DECISIONS §5). Дайджест «что произошло за
день» перестают читать на второй неделе; вопрос, который человек на самом деле задаёт, —
«мне ответили?». Поэтому письмо о новой реплике уходит тем, кто **участвует** в ветке
(написал или упомянут), не чаще раза в час на ветку, и в каждом письме есть отписка.
Правила отбора — чистые функции в ``app/comments.py``; здесь только почта и база.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..comments import (
    NOTIFY_PAUSE,
    check_body,
    parse_mentions,
    reply_targets,
    thread_participants,
    visible_body,
)
from ..database import get_db
from ..db_models import Comment, User
from ..deps import current_user, require_permission
from ..mail import Letter, mail_enabled, public_url, unsubscribe_url
from ..notify import send_and_log
from ..rbac import Perm, has_permission
from ..schemas import (
    CommentCreate,
    CommentCreated,
    CommentOut,
    MailReport,
    ThreadSubscriptionOut,
    ThreadSubscriptionUpdate,
    ThreadUnsubscribeRequest,
)
from ..security import create_thread_mute_token, decode_thread_mute_token

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


_SIGNATURE = ("\n\n—\nЭто письмо отправила платформа «Финанс-Элит».\n"
              "Отвечать на него бесполезно: ящик входящие письма не принимает.")


def _unsubscribe_block(mute_link: str, *, mention: bool) -> str:
    """Чем закончить письмо об обсуждении: как перестать их получать.

    **Без отписки это рассылка, а не уведомление** — но отписка, которая останавливает не
    то, что обещала, хуже её отсутствия. Поэтому у письма об упоминании рядом со ссылкой
    сказано, чего она **не** остановит: прямое обращение по имени приходит и из ветки, от
    которой человек отписался, — проглотить его значило бы обмануть сразу обоих, и
    позвавшего, и позванного. Выключатель, который выключает всё, тоже назван.
    """
    if not mute_link:
        # Без ``PUBLIC_URL`` ссылка вела бы в никуда. Молчать нельзя: письмо без выхода
        # это рассылка — поэтому называем второй путь, который работает всегда.
        return ("\n\nВыключить письма об обсуждениях можно в профиле, раздел «Письма об "
                "обсуждениях».")
    if mention:
        return (f"\n\nНе следить за этим обсуждением: {mute_link}\n"
                "Письма о том, что вас позвали по имени, это не остановит — они приходят "
                "и из обсуждений, за которыми вы не следите. Выключить письма об "
                "обсуждениях совсем можно в профиле.")
    return (f"\n\nНе писать мне об этом обсуждении: {mute_link}\n"
            "Выключить письма об обсуждениях совсем можно в профиле.")


def _mention_letter(*, author: str, subject_name: str, where: str, body: str,
                    link: str, mute_link: str) -> Letter:
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
              + _unsubscribe_block(mute_link, mention=True)
              + _SIGNATURE),
        # Рассказ о чужой активности: на неподтверждённый адрес не уходит (см. Letter).
        informational=True,
    )


def _reply_letter(*, author: str, subject_name: str, where: str, body: str,
                  link: str, mute_link: str) -> Letter:
    """Письмо участнику ветки: «мне ответили?».

    **Пауза названа в самом письме.** Следующие реплики ближайшего часа письма не дадут, и
    не сказать об этом значило бы позволить прочесть тишину как «больше никто не ответил»
    — ровно та ошибка, ради которой уведомления и заводят.
    """
    hours = int(NOTIFY_PAUSE.total_seconds() // 3600)
    return Letter(
        subject=f"Новая реплика: {subject_name} — Финанс-Элит",
        text=(f"{author} написал в обсуждении «{subject_name}»"
              + (f", раздел «{where}»" if where else "") + ":\n\n"
              f"{body}\n\n"
              + (f"Открыть обсуждение: {link}\n\n" if link else "")
              + "Письмо пришло, потому что вы участвуете в этом обсуждении: написали в "
                "нём или вас в нём упомянули.\n"
              + ("Если в ближайший час появятся новые реплики, отдельных писем о них не "
                 "будет — откройте обсуждение целиком." if hours == 1 else
                 f"Следующие {hours} ч письма о новых репликах не приходят — откройте "
                 f"обсуждение целиком.")
              + _unsubscribe_block(mute_link, mention=False)
              + _SIGNATURE),
        # Рассказ о чужой активности: на неподтверждённый адрес не уходит (см. Letter).
        informational=True,
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

    # Кому ещё уйдёт письмо: участникам ветки. Отбор — чистая функция; здесь только то,
    # что ей нужно из базы. Считается **до** отправки и при выключенной почте тоже:
    # ответ обязан быть одинаковым по смыслу, а «кому бы ушло» — часть этого смысла.
    thread = crud.list_comments(db, org_id, subject_type, subject_id,
                                anchor=body.anchor or "")
    by_email = {u.email.lower(): u for _, u in crud.list_members(db, org_id)}
    state = crud.thread_notify_state(db, [u.id for u in by_email.values()],
                                     subject_type, subject_id, body.anchor or "")
    followed = reply_targets(
        thread_participants(thread), author_email=author.email or "", mentioned=called,
        members=by_email.keys(),
        # Ключ состояния — адрес: правила отбора о пользователях не знают, они читают
        # разговор, а в разговоре люди названы почтой.
        state={email: state[user.id] for email, user in by_email.items()
               if user.id in state},
        now=datetime.now(timezone.utc))

    report = MailReport()
    if (called or followed) and mail_enabled():
        base = public_url()
        path = (f"/projects/{subject_id}" if subject_type == "project"
                else f"/audit/subjects/{subject_id}")
        link = f"{base}{path}" if base else ""
        sent_to: list[str] = []
        for email, mention in [(e, True) for e in called] + [(e, False) for e in followed]:
            target = by_email.get(email.lower())
            if target is None:                 # ушёл из организации — письма не будет
                continue
            # Общий выключатель гасит **всё**, включая обращение по имени: это последний
            # рубеж «не пишите мне», и щель в нём сделала бы его неправдой.
            if not target.comment_emails:
                continue
            build = _mention_letter if mention else _reply_letter
            letter = build(author=author.email, subject_name=subject_name,
                           where=body.anchor_label, body=body.body.strip(), link=link,
                           mute_link=unsubscribe_url(create_thread_mute_token(
                               target.id, subject_type, subject_id, body.anchor or "")))
            background.add_task(send_and_log, db.get_bind(), target.id, email, letter,
                                "comment.mention_mail" if mention else "comment.reply_mail")
            sent_to.append(target.id)
        # Пауза отсчитывается от **постановки в очередь**: очередь разбирается уже за
        # пределами запроса, и ждать её исхода значило бы выпустить второе письмо, пока
        # первое ещё летит. Упомянутые в счёт идут тоже — иначе «позвали, а через минуту
        # ответили» дало бы два письма об одной ветке.
        crud.mark_thread_notified(db, sent_to, subject_type, subject_id, body.anchor or "")
        # Отправка идёт после ответа, поэтому её исход здесь ещё не известен: обещаем
        # только то, что письма **поставлены в очередь**, а результат каждого уходит в
        # журнал того, кого позвали.
        report = MailReport(attempted=True, ok=True)
    return CommentCreated(comment=_out(comment), notified=called,
                          unknown_mentions=mentions.unknown, followed=followed,
                          mail=report)


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


# --- Письма об обсуждении: отписка от ветки (OPEN-DECISIONS §5) ---

#: Что значит отписка — один текст на API, экран и письмо: три формулировки одного
#: обещания однажды разойдутся, и разойдутся именно там, где человек проверяет, сработало
#: ли «не пишите мне».
MUTED_NOTE = ("Письма о новых репликах в этом обсуждении не приходят. Если вас позовут "
              "по имени, письмо придёт — это прямое обращение; выключить письма об "
              "обсуждениях совсем можно в профиле.")
FOLLOWING_NOTE = ("Письма о новых репликах приходят участникам обсуждения — тем, кто в "
                  "нём написал или был упомянут, — не чаще раза в час.")


def _subscription_out(muted: bool) -> ThreadSubscriptionOut:
    return ThreadSubscriptionOut(muted=muted,
                                 note=MUTED_NOTE if muted else FOLLOWING_NOTE)


@router.get("/comments/subscription", response_model=ThreadSubscriptionOut)
def thread_subscription(subject_type: str, subject_id: str, anchor: str = "",
                        user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> ThreadSubscriptionOut:
    """Приходят ли письма об этой ветке — и что это значит.

    Права организации здесь не спрашиваются намеренно: это **личная настройка человека**,
    а не содержимое организации, и строка «не писать мне об этом» не открывает и не
    показывает ничего. Тот же довод, по которому у неё нет ни ``organization_id``, ни
    RLS-политики.
    """
    row = crud.get_comment_subscription(db, user.id, subject_type, subject_id, anchor)
    return _subscription_out(row is not None and row.muted_at is not None)


@router.post("/comments/subscription", response_model=ThreadSubscriptionOut)
def set_thread_subscription(body: ThreadSubscriptionUpdate,
                            user: User = Depends(current_user),
                            db: Session = Depends(get_db)) -> ThreadSubscriptionOut:
    """Отписаться от ветки или вернуть письма о ней.

    Возврат обязателен: отписка, из которой нет дороги назад, — ловушка, и нажимают её
    один раз на всю жизнь.
    """
    row = crud.set_thread_muted(db, user.id, body.subject_type, body.subject_id,
                                body.anchor, muted=body.muted)
    return _subscription_out(row.muted_at is not None)


@router.post("/comments/unsubscribe", response_model=ThreadSubscriptionOut)
def unsubscribe_by_token(body: ThreadUnsubscribeRequest,
                         db: Session = Depends(get_db)) -> ThreadSubscriptionOut:
    """Отписка по ссылке из письма — **без входа**.

    Требовать пароль ради «перестаньте мне писать» значит заставить человека отправить
    письмо в спам вместо отписки: спам-жалоба обходится дороже, чем эта строка кода.

    Ветка берётся **из подписанного токена**, а не из тела запроса: иначе ссылку можно
    было бы переписать и отписать человека от чужого разговора. Сам запрос — ``POST``:
    почтовые фильтры организаций ходят по ссылкам заранее, и отписка по ``GET``
    срабатывала бы у тех, кто её не нажимал.
    """
    claims = decode_thread_mute_token(body.token)
    if claims is None:
        raise HTTPException(status_code=400,
                            detail="Ссылка недействительна или устарела. Письма об "
                                   "обсуждениях можно выключить в профиле.")
    user_id, subject_type, subject_id, anchor = claims
    if crud.get_user(db, user_id) is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или устарела")
    row = crud.set_thread_muted(db, user_id, subject_type, subject_id, anchor,
                                muted=body.muted)
    return _subscription_out(row.muted_at is not None)
