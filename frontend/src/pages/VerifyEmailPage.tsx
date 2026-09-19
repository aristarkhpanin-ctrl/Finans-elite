import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/auth";
import { httpDetail } from "../api/client";
import { Button } from "../components/ui";

/**
 * Подтверждение адреса по ссылке из письма (OPEN-DECISIONS §4).
 *
 * Страница живёт **вне защищённых маршрутов**: ссылку открывают из почты, и требовать
 * сначала войти значило бы отправить человека искать пароль ради того, что он уже
 * доказал переходом сюда.
 *
 * Подтверждение **ничего не открывает и ничего не запирает** — и страница говорит это
 * словами. Иначе «подтвердите адрес» читается как условие доступа, а человек, у которого
 * ссылка протухла, решит, что потерял учётную запись.
 *
 * Запрос уходит **сам**, без кнопки «подтвердить»: человек уже нажал — в письме.
 * Вторая кнопка здесь была бы данью форме, а не смыслом.
 */
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"busy" | "done" | "fail">(token ? "busy" : "fail");
  const [error, setError] = useState(token ? "" : "В ссылке нет токена подтверждения.");
  const [note, setNote] = useState("");
  // React 18 в строгом режиме вызывает эффект дважды; второй запрос дал бы человеку
  // ошибку поверх уже случившегося успеха.
  const asked = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!token || asked.current) return;
    asked.current = true;
    verifyEmail(token)
      .then((r) => { setNote(r.note); setState("done"); })
      .catch((e) => {
        setError(httpDetail(e) ?? "Ссылка недействительна или устарела.");
        setState("fail");
      });
  }, [token]);

  return (
    <div className="auth-card">
      <h1 className="auth-title">Подтверждение адреса</h1>
      {state === "busy" && <p className="page-sub">Подтверждаем…</p>}
      {state === "done" && <p className="page-sub">{note}</p>}
      {state === "fail" && (
        <>
          <div className="error" role="alert">{error}</div>
          {/* Протухшая ссылка — не потеря доступа: подтверждение ничего не открывает.
              Сказать это здесь важнее, чем предложить новую ссылку. */}
          <p className="page-sub" style={{ marginTop: 10 }}>
            Это не мешает работе: вход, восстановление пароля и приглашения не зависят от
            подтверждения. Новое письмо можно запросить в профиле.
          </p>
        </>
      )}
      {state !== "busy" && (
        <Button variant="ghost" onClick={() => navigate("/")}>
          Перейти в рабочую область
        </Button>
      )}
    </div>
  );
}
