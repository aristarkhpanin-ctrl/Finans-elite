"""Аутентификация: регистрация, вход, активация приглашения, профиль (6.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..db_models import User
from ..deps import current_user
from ..ratelimit import rate_limit
from ..schemas import (
    ActivateRequest,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from ..security import (
    create_access_token,
    decode_reset_token,
    decode_token,
    hash_password,
    password_stamp,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Защита от перебора: ограничение попыток в минуту с одного IP.
_register_limit = rate_limit("register", limit=10, window_seconds=60)
_login_limit = rate_limit("login", limit=20, window_seconds=60)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_limit)],
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Регистрация: создаёт пользователя, его организацию и членство (owner)."""
    _check_password(body.password)
    if crud.get_user_by_email(db, body.email) is not None:
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован")
    user = crud.create_user(db, body.email, body.full_name, hash_password(body.password))
    org = crud.create_organization(db, body.organization_name)
    crud.add_membership(db, org.id, user.id, role="owner")
    crud.log_action(db, org.id, user, "org.create", entity_type="organization",
                    entity_id=org.id, entity_name=org.name)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_login_limit)])
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Вход по email и паролю → токен доступа."""
    user = crud.get_user_by_email(db, body.email)
    if user is None or not verify_password(user.hashed_password, body.password):
        # Неудача известного пользователя — событие для его организаций: подбор пароля
        # виден только так. Неизвестный адрес не пишется никуда (см. log_user_action).
        crud.log_user_action(db, user, "auth.login_failed", details="неверный пароль")
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    crud.log_user_action(db, user, "auth.login")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    """Данные текущего пользователя."""
    return UserOut(id=user.id, email=user.email, full_name=user.full_name)


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
def activate(body: ActivateRequest, db: Session = Depends(get_db)) -> TokenResponse:
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
    return TokenResponse(access_token=create_access_token(user.id))


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> UserOut:
    """Профиль: имя. Почта не меняется — она же логин и адрес приглашений."""
    updated = crud.set_full_name(db, user, body.full_name)
    return UserOut(id=updated.id, email=updated.email, full_name=updated.full_name)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> None:
    """Смена своего пароля. Текущий обязателен: иначе украденная сессия меняет пароль
    и запирает владельца снаружи."""
    if not verify_password(user.hashed_password, body.current_password):
        crud.log_user_action(db, user, "auth.password_change_failed",
                             details="текущий пароль неверен")
        raise HTTPException(status_code=400, detail="Текущий пароль неверен")
    _check_password(body.new_password)
    crud.set_password(db, user, hash_password(body.new_password))
    crud.log_user_action(db, user, "auth.password_change")
