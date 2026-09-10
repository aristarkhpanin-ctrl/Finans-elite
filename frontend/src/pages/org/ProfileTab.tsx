import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { changePassword, disableTotp, enableTotp, getPasswordPolicy, getSessions,
         getTotpStatus, reissueRecoveryCodes, revokeAllSessions, revokeSession,
         startTotpSetup, updateProfile, type TotpSetup } from "../../api/auth";
import { httpDetail, httpStatus } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Button, Chip, Field, Loading, Modal } from "../../components/ui";

/**
 * Профиль пользователя (макет «Экран 15»): имя и смена пароля.
 *
 * Почта не меняется: она одновременно логин и адрес, по которому пришло приглашение.
 * Смена почты — это смена личности в системе, и делать её тихой правкой поля нельзя.
 *
 * Восстановления пароля здесь нет: честный сброс требует письма на подтверждённый
 * адрес, а почтовой отправки у платформы нет.
 */
export function ProfileTab() {
  const { user } = useAuth();
  const toast = useToast();

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");

  const saveName = useMutation({
    mutationFn: () => updateProfile(fullName.trim()),
    onSuccess: () => toast("Имя сохранено", { kind: "success" }),
    onError: () => toast("Не удалось сохранить имя", { kind: "error" }),
  });

  const savePassword = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      setCurrent(""); setNext(""); setRepeat("");
      toast("Пароль изменён", { kind: "success" });
    },
    // Отказ по новому паролю сервер называет словами — показываем их, а не своё
    // предположение о причине: список требований шире длины, и «короче 8 символов»
    // сбивало бы с толку там, где дело в «qwerty» или в собственном адресе.
    onError: (e: unknown) =>
      toast(httpStatus(e) === 400 ? "Текущий пароль неверен"
        : (httpStatus(e) === 422 && httpDetail(e)) || "Не удалось изменить пароль",
        { kind: "error" }),
  });

  /**
   * Требования к паролю берутся **с сервера**: перечисленные здесь своим текстом, они
   * однажды разойдутся с проверкой, и человек прочтёт одно, а получит другое. Пока
   * список не пришёл — не обещаем ничего.
   */
  const { data: policy } = useQuery({ queryKey: ["password-policy"],
                                      queryFn: getPasswordPolicy });
  const policyRules = policy?.rules ?? [];

  const mismatch = repeat.length > 0 && next !== repeat;
  const canChange = current.length > 0 && next.length >= 8 && next === repeat
    && !savePassword.isPending;

  return (
    <div style={{ display: "grid", gap: 18, maxWidth: 520 }}>
      <div className="audit-block">
        <div className="audit-block__title">Профиль</div>
        <Field label="Почта" value={user?.email ?? ""} disabled
               note="Почта — это логин и адрес приглашения; сменить её здесь нельзя." />
        <Field label="Имя" placeholder="Имя и фамилия" value={fullName}
               disabled={saveName.isPending}
               onChange={(e) => setFullName(e.target.value)} />
        <Button onClick={() => saveName.mutate()} loading={saveName.isPending}
                disabled={fullName.trim() === (user?.full_name ?? "")}>
          Сохранить имя
        </Button>
      </div>

      <TotpBlock />

      <SessionsBlock />

      <div className="audit-block">
        <div className="audit-block__title">Смена пароля</div>
        <Field label="Текущий пароль" type="password" value={current}
               disabled={savePassword.isPending}
               note="Текущий пароль обязателен: без него любую открытую сессию можно было бы использовать, чтобы запереть владельца снаружи."
               onChange={(e) => setCurrent(e.target.value)} />
        <Field label="Новый пароль" type="password" value={next}
               disabled={savePassword.isPending}
               onChange={(e) => setNext(e.target.value)} />
        {/* Требования — видимым списком, а не подсказкой под знаком вопроса: правило,
            которое надо навести курсором, чтобы прочесть, — это правило, которое
            нарушают. Текст приходит с сервера: перечисленный здесь своими словами, он
            однажды разошёлся бы с проверкой. */}
        {policyRules.length > 0 && (
          <ul className="mnotes" style={{ marginTop: -4 }}>
            {policyRules.map((rule) => <li key={rule}>{rule}</li>)}
          </ul>
        )}
        <Field label="Новый пароль ещё раз" type="password" value={repeat}
               disabled={savePassword.isPending}
               error={mismatch ? "Пароли не совпадают" : undefined}
               note="Смена пароля закроет остальные входы; этот останется."
               onChange={(e) => setRepeat(e.target.value)} />
        <Button onClick={() => savePassword.mutate()} loading={savePassword.isPending}
                disabled={!canChange}>
          Изменить пароль
        </Button>
      </div>
    </div>
  );
}


/** Когда вход был активен: «сейчас / N ч. назад / дата». `null` — не обращался с входа. */
function seen(iso: string | null | undefined): string {
  if (!iso) return "с момента входа не обращался";
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 60) return "активен сейчас";
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} ч. назад`;
  return new Date(iso).toLocaleDateString("ru-RU",
    { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Входы в учётную запись (C1).
 *
 * Показываются только **действующие**: список закрытых не отвечает на вопрос, ради
 * которого его открывают («кто сейчас внутри?»). История входов есть в журнале
 * организации — второй её копии здесь не заводим, разошлись бы.
 *
 * Устройство и адрес приходят от самого браузера и подделываются кем угодно. Это
 * подсказка владельцу, а не удостоверение, и оговорка стоит рядом со списком: без неё
 * знакомая строка читается как доказательство, что вход был свой.
 */
function SessionsBlock() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["sessions"], queryFn: getSessions });
  const refresh = () => qc.invalidateQueries({ queryKey: ["sessions"] });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeSession(id),
    onSuccess: () => { refresh(); toast("Вход закрыт", { kind: "success" }); },
    onError: () => toast("Не удалось закрыть вход", { kind: "error" }),
  });
  const revokeAll = useMutation({
    mutationFn: revokeAllSessions,
    // Текущий вход тоже закрыт — страница перестанет отвечать, и это правильно:
    // человек просил выйти везде. Перезагрузка отправит его на экран входа.
    onSuccess: (closed) => {
      toast(`Закрыто входов: ${closed}. Войдите заново.`, { kind: "success" });
      window.setTimeout(() => window.location.reload(), 1200);
    },
    onError: () => toast("Не удалось закрыть входы", { kind: "error" }),
  });

  const rows = data ?? [];
  return (
    <div className="audit-block">
      <div className="audit-block__title">Входы в учётную запись</div>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Действующие входы. Устройство и адрес присылает сам браузер — их можно подделать,
        поэтому это подсказка, а не доказательство. История входов — в журнале организации.
      </p>
      {isLoading ? <Loading /> : (
        <div className="sess-list">
          {rows.map((s) => (
            <div className="sess-row" key={s.id}>
              <div style={{ minWidth: 0 }}>
                <div className="sess-row__device" title={s.user_agent || undefined}>
                  {s.device}
                  {s.current && <Chip kind="active">этот вход</Chip>}
                </div>
                <div className="sess-row__meta">
                  {s.ip || "адрес неизвестен"} · {seen(s.last_seen_at)}
                </div>
              </div>
              {!s.current && (
                <Button variant="ghost" onClick={() => revoke.mutate(s.id)}
                        disabled={revoke.isPending}>Закрыть</Button>
              )}
            </div>
          ))}
        </div>
      )}
      <Button variant="ghost" onClick={() => revokeAll.mutate()}
              disabled={revokeAll.isPending}>
        Выйти на всех устройствах
      </Button>
    </div>
  );
}

/**
 * Второй фактор: одноразовые коды из приложения (C2).
 *
 * **QR-кода платформа не рисует** — библиотеки для этого нет, и вместо картинки здесь
 * ключ группами по четыре плюс ссылка `otpauth://`. Это неудобно, и об этом сказано
 * прямо: спрятанное неудобство человек всё равно обнаружит, только позже и злее.
 *
 * Резервные коды показываются **один раз**. Почты у платформы нет, значит письма
 * «восстановите доступ» не будет: без кодов потерянный телефон означал бы потерянную
 * учётную запись — и последней инстанцией остаётся платформа, к которой придётся идти.
 */
function TotpBlock() {
  const qc = useQueryClient();
  const toast = useToast();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [password, setPassword] = useState("");
  const [confirming, setConfirming] = useState<null | "disable" | "reissue">(null);

  const { data: status } = useQuery({ queryKey: ["totp"], queryFn: getTotpStatus });
  const refresh = () => qc.invalidateQueries({ queryKey: ["totp"] });

  const begin = useMutation({
    mutationFn: startTotpSetup,
    onSuccess: (fresh) => { setSetup(fresh); setCode(""); },
    onError: () => toast("Не удалось начать настройку", { kind: "error" }),
  });
  const enable = useMutation({
    mutationFn: () => enableTotp(code.trim()),
    onSuccess: (fresh) => {
      setSetup(null);
      setCodes(fresh);
      refresh();
      toast("Второй фактор включён", { kind: "success" });
    },
    onError: (e: unknown) =>
      toast(httpDetail(e) ?? "Код не подошёл", { kind: "error" }),
  });
  const disable = useMutation({
    mutationFn: () => disableTotp(password),
    onSuccess: () => {
      setConfirming(null); setPassword(""); refresh();
      toast("Второй фактор выключен", { kind: "success" });
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось выключить", { kind: "error" }),
  });
  const reissue = useMutation({
    mutationFn: () => reissueRecoveryCodes(password),
    onSuccess: (fresh) => {
      setConfirming(null); setPassword(""); setCodes(fresh); refresh();
    },
    onError: (e: unknown) => toast(httpDetail(e) ?? "Не удалось перевыпустить", { kind: "error" }),
  });

  return (
    <div className="audit-block">
      <div className="audit-block__title">Второй фактор</div>

      {status?.enabled ? (
        <>
          <p className="page-sub" style={{ marginTop: 0 }}>
            Включён. При входе спрашивается код из приложения.
            {" "}Резервных кодов осталось: {status.recovery_left}.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button variant="ghost" onClick={() => { setConfirming("reissue"); setPassword(""); }}>
              Перевыпустить резервные коды
            </Button>
            <Button variant="ghost" onClick={() => { setConfirming("disable"); setPassword(""); }}>
              Выключить
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="page-sub" style={{ marginTop: 0 }}>
            {status?.recommended
              ? "Вы владелец организации: второй фактор защищает не только вашу работу, "
                + "но и тариф, участников и данные всей компании."
              : "Одноразовый код из приложения-аутентификатора в дополнение к паролю."}
            {" "}Пароль в паре с кодом бесполезен для того, кто его подсмотрел.
          </p>
          {!setup ? (
            <Button onClick={() => begin.mutate()} loading={begin.isPending}>
              Настроить
            </Button>
          ) : (
            <>
              <p className="page-sub">
                Добавьте ключ в приложение (Яндекс.Ключ, Google Authenticator, 1Password и
                другие) и введите код, который оно покажет.{" "}
                <b>QR-кода здесь нет</b> — ключ вводится вручную или по ссылке ниже.
              </p>
              <div className="totp-key">{setup.secret_grouped}</div>
              <a className="totp-link" href={setup.otpauth_uri}>
                Открыть в приложении (если эта страница открыта на телефоне)
              </a>
              <Field label="Код из приложения" value={code} inputMode="numeric"
                     placeholder="6 цифр"
                     onChange={(e) => setCode(e.target.value)} />
              <Button onClick={() => enable.mutate()} loading={enable.isPending}
                      disabled={code.trim().length < 6}>
                Включить
              </Button>
            </>
          )}
        </>
      )}

      {/* Коды показываются один раз: восстановить их нельзя, можно только перевыпустить. */}
      <Modal open={codes !== null} title="Резервные коды" onClose={() => setCodes(null)}
             actions={<Button onClick={() => setCodes(null)}>Я сохранил их</Button>}>
        <p className="page-sub" style={{ marginTop: 0 }}>
          Сохраните эти коды. Каждый работает один раз и заменяет код из приложения.
          <b> Больше они не покажутся</b>: у платформы нет почты, и письма «восстановите
          доступ» не будет — без кодов вернуть доступ сможет только поддержка.
        </p>
        <div className="totp-codes">
          {(codes ?? []).map((c) => <div key={c}>{c}</div>)}
        </div>
      </Modal>

      <Modal open={confirming !== null}
             title={confirming === "disable" ? "Выключить второй фактор" : "Перевыпустить коды"}
             onClose={() => setConfirming(null)}
             actions={
               <>
                 <Button variant="ghost" onClick={() => setConfirming(null)}>Отмена</Button>
                 <Button onClick={() => (confirming === "disable" ? disable : reissue).mutate()}
                         disabled={!password || disable.isPending || reissue.isPending}>
                   Подтвердить
                 </Button>
               </>
             }>
        {/* Пароль здесь — разница между «украли сессию» и «украли учётную запись»:
            выключение второго фактора это ровно то, что сделает угонщик. */}
        <p className="page-sub" style={{ marginTop: 0 }}>
          {confirming === "disable"
            ? "Вход снова будет защищён только паролем."
            : "Прежние резервные коды перестанут работать сразу."}
        </p>
        <Field label="Ваш пароль" type="password" value={password} autoFocus
               onChange={(e) => setPassword(e.target.value)} />
      </Modal>
    </div>
  );
}
