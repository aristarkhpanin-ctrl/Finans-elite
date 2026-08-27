import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { changePassword, updateProfile } from "../../api/auth";
import { httpStatus } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Button, Field } from "../../components/ui";

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
               onChange={(e) => setRepeat(e.target.value)} />
        <Button onClick={() => savePassword.mutate()} loading={savePassword.isPending}
                disabled={!canChange}>
          Изменить пароль
        </Button>
      </div>
    </div>
  );
}
