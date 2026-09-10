"""Аутентификация: регистрация, вход, активация приглашения, профиль (6.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..db_models import User, UserSession
from ..deps import account_blocked_detail, current_session, current_user
from ..ratelimit import rate_limit
from ..schemas import (
    ActivateRequest,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
    RevokeAllOut,
    SessionOut,
    TokenResponse,
    UserOut,
)
from ..security import (
    access_ttl,
    create_access_token,
    decode_reset_token,
    decode_token,
    hash_password,
    password_stamp,
    verify_password,
)
from ..sessions import client_ip, device_label

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Защита от перебора: ограничение попыток в минуту с одного IP.
_register_limit = rate_limit("register", limit=10, window_seconds=60)
_login_limit = rate_limit("login", limit=20, window_seconds=60)




def _issue_token(db: Session, user: User, request: Request,
                 remember: bool = False) -> TokenResponse:
    """Завести сеанс и выдать привязанный к нему токен (C1).

    Одна функция на все три двери входа — регистрацию, вход и активацию ссылки: три
    копии этой пары («создать сеанс» + «подписать токен») однажды разошлись бы, и одна
    из дверей начала бы выдавать токен без сеанса, то есть неотзываемый.
    """
    ttl = access_ttl(remember)
    session = crud.create_session(
        db, user.id, ttl_seconds=ttl,
        user_agent=request.headers.get("user-agent", ""),
        ip=client_ip(forwarded_for=request.headers.get("x-forwarded-for"),
                     remote=request.client.host if request.client else ""),
    )
    return TokenResponse(access_token=create_access_token(user.id, session.id, ttl))


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_limit)],
)
def register(body: RegisterRequest, request: Request,
             db: Session = Depends(get_db)) -> TokenResponse:
    """Регистрация: создаёт пользователя, его организацию и членство (owner)."""
    _check_password(body.password)
    if crud.get_user_by_email(db, body.email) is not None:
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
    user = crud.create_user(db, body.email, body.full_name, hash_password(body.password))
    org = crud.create_organization(db, body.organization_name)
    crud.add_membership(db, org.id, user.id, role="owner")
    crud.log_action(db, org.id, user, "org.create", entity_type="organization",
                    entity_id=org.id, entity_name=org.name)
    return _issue_token(db, user, request)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_login_limit)])
def login(body: LoginRequest, request: Request,
          db: Session = Depends(get_db)) -> TokenResponse:
    """Вход по email и паролю → токен доступа."""
    user = crud.get_user_by_email(db, body.email)
    if user is None or not verify_password(user.hashed_password, body.password):
        # Неудача известного пользователя — событие для его организаций: подбор пароля
        # виден только так. Неизвестный адрес не пишется никуда (см. log_user_action).
        crud.log_user_action(db, user, "auth.login_failed", details="неверный пароль")
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if user.blocked_at is not None:
        # Пароль верен — значит человек тот самый, и молчать о причине незачем: выдать
        # ему рабочий на вид токен, который отвергнет первый же запрос, хуже, чем сразу
        # сказать, что случилось. Событие пишется: попытка входа заблокированного —
        # именно то, ради чего блокировку и ставили.
        crud.log_user_action(db, user, "auth.login_blocked", details=user.block_reason)
        raise HTTPException(status_code=403, detail=account_blocked_detail(user))
    crud.log_user_action(db, user, "auth.login")
    return _issue_token(db, user, request, remember=body.remember)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    """Данные текущего пользователя."""
    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                   is_staff=user.is_staff)


#: Минимальная длина пароля. Одно правило на все три места, где пароль задаётся:
#: регистрация, активация приглашения и смена. Разные пороги в разных дверях —
#: это не строгость, а иллюзия строгости.
MIN_PASSWORD_LEN = 8


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов",
        )


@router.post("/activate", response_model=TokenResponse)
def activate(body: ActivateRequest, request: Request,
             db: Session = Depends(get_db)) -> TokenResponse:
    """Задать пароль по ссылке и сразу войти — приглашение или сброс.

    Дорога одна на оба случая намеренно: для пользователя это один и тот же шаг
    («откройте ссылку, придумайте пароль»), и вторая страница с той же формой
    отличалась бы только словом в заголовке. Правила при этом разные и строгие —
    приглашение срабатывает, пока пароля нет; сброс — пока не сменился отпечаток.

    До этого приглашённый участник существовал, но войти не мог никогда:
    ``crud.add_member`` заводит пользователя без пароля, а других путей его задать
    не было — приглашение вело в никуда.

    Токен приглашения **не является токеном входа** (см. ``decode_token``): им можно
    только завести пароль. И только один раз: если пароль уже есть, активация
    отклоняется — иначе ссылка-приглашение осталась бы вечным способом сбросить
    чужой пароль, минуя знание текущего.
    """
    _check_password(body.password)
    user_id = decode_token(body.token, expect="invite")
    reset = None if user_id else decode_reset_token(body.token)
    if user_id is None and reset is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или устарела")

    user = crud.get_user(db, user_id or reset[0])          # type: ignore[index]
    if user is None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна")
    if user_id is not None and user.hashed_password:
        raise HTTPException(status_code=409, detail="Приглашение уже активировано — "
                                                    "войдите по паролю")
    if reset is not None and reset[1] != password_stamp(user.hashed_password):
        # Отпечаток не совпал: пароль с тех пор менялся — либо этой же ссылкой,
        # либо самим пользователем. Одноразовость сброса держится на этом.
        raise HTTPException(status_code=409, detail="Ссылка уже использована — "
                                                    "попросите выдать новую")
    crud.set_password(db, user, hash_password(body.password))
    if body.full_name:
        crud.set_full_name(db, user, body.full_name)
    crud.log_user_action(db, user, "auth.activate",
                         details="сброс пароля" if reset is not None else "приглашение")
    # Сброс пароля закрывает прежние входы: ссылку и выдают тогда, когда доступ к
    # учётной записи под вопросом, — оставить чужой сеанс живым значило бы отдать
    # аккаунт тому, из-за кого сброс и понадобился.
    crud.revoke_user_sessions(db, user.id)
    return _issue_token(db, user, request)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> UserOut:
    """Профиль: имя. Почта не меняется — она же логин и адрес приглашений."""
    updated = crud.set_full_name(db, user, body.full_name)
    return UserOut(id=updated.id, email=updated.email, full_name=updated.full_name,
                   is_staff=updated.is_staff)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user: User = Depends(current_user),
                    session: UserSession = Depends(current_session),
                    db: Session = Depends(get_db)) -> None:
    """Смена своего пароля. Текущий обязателен: иначе украденная сессия меняет пароль
    и запирает владельца снаружи."""
    if not verify_password(user.hashed_password, body.current_password):
        crud.log_user_action(db, user, "auth.password_change_failed",
                             details="текущий пароль неверен")
        raise HTTPException(status_code=400, detail="Текущий пароль неверен")
    _check_password(body.new_password)
    crud.set_password(db, user, hash_password(body.new_password))
    # Смена пароля закрывает **остальные** входы, а текущий оставляет: пароль меняют в
    # том числе потому, что подозревают чужой доступ, и оставить его живым значило бы
    # сделать смену бессмысленной. Выкидывать при этом самого себя — тоже плохо: человек
    # только что подтвердил, что он это он.
    closed = crud.revoke_user_sessions(db, user.id, keep=session.id)
    crud.log_user_action(db, user, "auth.password_change",
                         details=f"закрыто входов: {closed}" if closed else "")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(current_user),
                  session: UserSession = Depends(current_session),
                  db: Session = Depends(get_db)) -> list[SessionOut]:
    """Действующие входы в свою учётную запись (C1).

    Показываются только живые: список закрытых не отвечает на вопрос, ради которого его
    открывают («кто сейчас внутри?»). История входов есть в журнале организации — второй
    её копии здесь не заводим, разошлись бы.

    Устройство и адрес приходят от самого клиента и подделываются кем угодно, поэтому
    они **подсказка владельцу**, а не удостоверение: ни один отказ платформы на них не
    опирается, и на экране это сказано.
    """
    return [
        SessionOut(
            id=s.id, device=device_label(s.user_agent), user_agent=s.user_agent,
            ip=s.ip, created_at=s.created_at, last_seen_at=s.last_seen_at,
            expires_at=s.expires_at, current=s.id == session.id,
        )
        for s in crud.list_sessions(db, user.id)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> None:
    """Закрыть конкретный вход. **Только свой**: чужой сеанс не находится, а не
    отказывается по правам — знать о существовании чужих входов незачем."""
    target = crud.get_session(db, session_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(status_code=404, detail="Вход не найден")
    crud.revoke_session(db, target)
    crud.log_user_action(db, user, "auth.session_revoke",
                         details=device_label(target.user_agent))


@router.post("/sessions/revoke-all", response_model=RevokeAllOut)
def revoke_all_sessions(user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> RevokeAllOut:
    """«Выйти на всех устройствах» — включая текущее.

    Текущее тоже закрывается намеренно: человек нажимает эту кнопку, когда не уверен,
    что контролирует учётную запись, и оставленный «свой» вход в такой ситуации — это
    ровно тот вход, из-за которого всё и началось.
    """
    closed = crud.revoke_user_sessions(db, user.id)
    crud.log_user_action(db, user, "auth.sessions_revoke_all",
                         details=f"закрыто входов: {closed}")
    return RevokeAllOut(closed=closed)
