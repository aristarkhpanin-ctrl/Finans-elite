"""Аутентификация: регистрация, вход, активация приглашения, профиль (6.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import crud, totp
from ..database import get_db
from ..db_models import User, UserSession
from ..deps import account_blocked_detail, current_session, current_user
from ..password_policy import MIN_LENGTH, check_password, policy_rules
from ..pwned import leak_check_enabled, leaked_count
from ..ratelimit import rate_limit
from ..schemas import (
    ActivateRequest,
    LoginRequest,
    PasswordChange,
    PasswordConfirmIn,
    PasswordPolicyOut,
    ProfileUpdate,
    RegisterRequest,
    RevokeAllOut,
    SessionOut,
    TokenResponse,
    TotpEnableIn,
    TotpRecoveryOut,
    TotpSetupOut,
    TotpStatusOut,
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
                 remember: bool = False, notice: str = "") -> TokenResponse:
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
    return TokenResponse(access_token=create_access_token(user.id, session.id, ttl),
                         notice=notice)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_limit)],
)
def register(body: RegisterRequest, request: Request,
             db: Session = Depends(get_db)) -> TokenResponse:
    """Регистрация: создаёт пользователя, его организацию и членство (owner)."""
    _check_password(body.password, body.email)
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
    notice = _second_factor(db, user, body.totp_code)
    crud.log_user_action(db, user, "auth.login")
    return _issue_token(db, user, request, remember=body.remember, notice=notice)


#: Код нужен, но не прислан. Отдельный статус, а не 401: пароль **верен**, и человеку
#: нужно не «войти заново», а сделать второй шаг. По 401 интерфейс отправил бы его
#: проверять пароль, которого он не путал.
STATUS_TOTP_REQUIRED = 428


def _second_factor(db: Session, user: User, code: str) -> str:
    """Проверить второй фактор. Возвращает примечание для ответа (или пустую строку).

    Отдельного «половинного» токена между шагами нет: он был бы ещё одним пропуском,
    который надо защищать наравне с настоящим, и жил бы ровно там, где его удобно
    украсть. Код приходит тем же запросом, что и пароль.
    """
    if user.totp_enabled_at is None:
        return ""
    locked = crud.totp_locked_for(user)
    if locked:
        # Подбор шестизначного кода закрывается **по учётной записи**, а не по адресу:
        # адреса меняются, а учётная запись одна.
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много неверных кодов. Попробуйте через {locked // 60 + 1} мин.")
    if not code:
        raise HTTPException(status_code=STATUS_TOTP_REQUIRED,
                            detail="Введите код из приложения-аутентификатора")
    if totp.verify(user.totp_secret, code):
        crud.note_totp_success(db, user)
        return ""
    remaining = totp.take_recovery_code(list(user.totp_recovery or []), code)
    if remaining is not None:
        crud.set_recovery_codes(db, user, remaining)
        crud.note_totp_success(db, user)
        crud.log_user_action(db, user, "auth.totp_recovery_used",
                             details=f"осталось кодов: {len(remaining)}")
        # Человеку говорят, что он потратил резервный код и сколько их осталось: молча
        # съеденный код кончится в самый неподходящий момент.
        return (f"Вход по резервному коду. Осталось кодов: {len(remaining)}. "
                "Перевыпустите их в профиле, когда вернёте доступ к приложению.")
    crud.note_totp_failure(db, user)
    crud.log_user_action(db, user, "auth.totp_failed")
    raise HTTPException(status_code=401, detail="Неверный код второго фактора")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    """Данные текущего пользователя."""
    return UserOut(id=user.id, email=user.email, full_name=user.full_name,
                   is_staff=user.is_staff)


def _check_password(password: str, email: str = "") -> None:
    """Одна проверка на все три двери, где пароль задаётся: регистрация, активация
    ссылки и смена. Разные требования в разных дверях — не строгость, а её иллюзия.

    Сначала правила, которые работают всегда (:mod:`app.password_policy`), затем — если
    включена — проверка по утечкам. Порядок именно такой: сетевой запрос ради пароля,
    который и так не годится, лишний, а недоступность чужого сервиса не должна решать,
    примем мы `qwerty1234` или нет.
    """
    problem = check_password(password, email=email)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    count = leaked_count(password)
    if count:
        raise HTTPException(
            status_code=422,
            detail=(f"Этот пароль встречается в известных утечках ({count:,} раз(а)) — "
                    "его подберут по словарю. Придумайте другой").replace(",", " "),
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
    # Проверка пароля **после** разбора ссылки: адрес человека известен только отсюда, а
    # без него не работает правило «пароль не повторяет вашу почту». Недействительная
    # ссылка при этом называется первой — это более крупная беда, чем слабый пароль.
    _check_password(body.password, user.email)
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
    _check_password(body.new_password, user.email)
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


@router.get("/password-policy", response_model=PasswordPolicyOut)
def password_policy() -> PasswordPolicyOut:
    """Что требуется от пароля — **из тех же правил**, что и проверяют.

    Экран, перечисляющий требования своим текстом, однажды разойдётся с сервером: человек
    прочтёт одно, а получит другое. Открыт без токена: правила нужны на регистрации и на
    активации ссылки, то есть до входа.
    """
    leak_check = leak_check_enabled()
    return PasswordPolicyOut(min_length=MIN_LENGTH, leak_check=leak_check,
                             rules=policy_rules(leak_check=leak_check))


# --- Второй фактор (C2) ---

def _totp_status(db: Session, user: User) -> TotpStatusOut:
    """Состояние второго фактора у человека.

    ``recommended`` — только рекомендация, и только владельцу. Принудительное включение
    без второго канала восстановления (почты у платформы нет) заперло бы того, кто
    потеряет и телефон, и резервные коды; решение «сделать обязательным» — за владельцем
    платформы, а не за кодом. Причина записана в декомпозиции, а не подразумевается.
    """
    roles = {m.role for m in crud.list_user_memberships(db, user.id)}
    return TotpStatusOut(
        enabled=user.totp_enabled_at is not None,
        pending=bool(user.totp_secret) and user.totp_enabled_at is None,
        recovery_left=len(user.totp_recovery or []),
        recommended="owner" in roles,
    )


@router.get("/totp", response_model=TotpStatusOut)
def totp_status(user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> TotpStatusOut:
    return _totp_status(db, user)


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> TotpSetupOut:
    """Завести секрет и показать его для настройки приложения.

    Второй фактор при этом **не включается**: пока код не подтверждён, вход работает как
    прежде. Иначе опечатки в приложении хватило бы, чтобы человек остался снаружи.

    Повторный вызов выдаёт **новый** секрет: сюда приходят, когда настройка не задалась,
    и подсовывать тот же секрет, который уже не сходится, незачем.
    """
    if user.totp_enabled_at is not None:
        raise HTTPException(status_code=409,
                            detail="Второй фактор уже включён — сначала выключите его")
    secret = totp.new_secret()
    crud.start_totp(db, user, secret)
    return TotpSetupOut(secret=secret, secret_grouped=totp.format_secret(secret),
                        otpauth_uri=totp.otpauth_uri(secret, user.email))


@router.post("/totp/enable", response_model=TotpRecoveryOut)
def totp_enable(body: TotpEnableIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> TotpRecoveryOut:
    """Подтвердить настройку кодом и получить резервные коды.

    Коды показываются **один раз** — как пароль: хранятся отпечатками, и восстановить их
    нельзя, можно только перевыпустить.
    """
    if user.totp_enabled_at is not None:
        raise HTTPException(status_code=409, detail="Второй фактор уже включён")
    if not user.totp_secret:
        raise HTTPException(status_code=409,
                            detail="Настройка не начата — получите ключ и добавьте его "
                                   "в приложение")
    if not totp.verify(user.totp_secret, body.code):
        raise HTTPException(status_code=400,
                            detail="Код не подошёл. Проверьте, что в приложении добавлен "
                                   "именно этот ключ и что время на устройстве точное")
    codes = totp.new_recovery_codes()
    crud.enable_totp(db, user, [totp.hash_code(c) for c in codes])
    crud.log_user_action(db, user, "auth.totp_enabled")
    return TotpRecoveryOut(codes=codes)


@router.post("/totp/recovery-codes", response_model=TotpRecoveryOut)
def totp_new_recovery_codes(body: PasswordConfirmIn, user: User = Depends(current_user),
                            db: Session = Depends(get_db)) -> TotpRecoveryOut:
    """Перевыпустить резервные коды. Прежние перестают работать сразу."""
    _confirm_password(user, body.password)
    if user.totp_enabled_at is None:
        raise HTTPException(status_code=409, detail="Второй фактор не включён")
    codes = totp.new_recovery_codes()
    crud.set_recovery_codes(db, user, [totp.hash_code(c) for c in codes])
    crud.log_user_action(db, user, "auth.totp_recovery_reissued")
    return TotpRecoveryOut(codes=codes)


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
def totp_disable(body: PasswordConfirmIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> None:
    """Выключить второй фактор — **по паролю**.

    Выключение второго фактора это ровно то, что сделает угонщик, дорвавшийся до открытой
    вкладки. Пароль здесь — разница между «украли сессию» и «украли учётную запись».
    """
    _confirm_password(user, body.password)
    if user.totp_enabled_at is None and not user.totp_secret:
        raise HTTPException(status_code=409, detail="Второй фактор не настроен")
    crud.disable_totp(db, user)
    crud.log_user_action(db, user, "auth.totp_disabled")


def _confirm_password(user: User, password: str) -> None:
    if not verify_password(user.hashed_password, password):
        raise HTTPException(status_code=400, detail="Пароль неверен")
