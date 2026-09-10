import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { changePassword, getSessions, revokeAllSessions, revokeSession,
         updateProfile } from "../../api/auth";
import { httpStatus } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Button, Chip, Field, Loading } from "../../components/ui";

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
    onError: (e: unknown) =>
      toast(httpStatus(e) === 400 ? "Текущий пароль неверен"
        : httpStatus(e) === 422 ? "Новый пароль короче 8 символов"
          : "Не удалось изменить пароль", { kind: "error" }),
  });

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

      <SessionsBlock />

      <div className="audit-block">
        <div className="audit-block__title">Смена пароля</div>
        <Field label="Текущий пароль" type="password" value={current}
               disabled={savePassword.isPending}
               note="Текущий пароль обязателен: без него любую открытую сессию можно было бы использовать, чтобы запереть владельца снаружи."
               onChange={(e) => setCurrent(e.target.value)} />
        <Field label="Новый пароль" type="password" value={next} hint="Не короче 8 символов."
               disabled={savePassword.isPending}
               onChange={(e) => setNext(e.target.value)} />
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
