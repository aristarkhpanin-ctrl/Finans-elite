import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { unsubscribeByToken } from "../api/comments";
import { httpDetail } from "../api/client";
import { Button } from "../components/ui";

/**
 * «Не писать мне об этом обсуждении» — по ссылке из письма (OPEN-DECISIONS §5).
 *
 * Страница живёт **вне защищённых маршрутов**: требовать пароль ради «перестаньте мне
 * писать» — способ получить жалобу на спам вместо отписки.
 *
 * Отписка происходит **здесь, из кода страницы**, а не по самой ссылке: корпоративные
 * почтовые фильтры ходят по ссылкам из писем заранее, и отписка по `GET` срабатывала бы
 * у людей, которые её не нажимали, — молча и без их ведома.
 *
 * Дорога назад — на этом же экране: отписка, из которой нет возврата, это ловушка, и
 * нажимают её один раз на всю жизнь.
 */
export function UnsubscribePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"busy" | "done" | "fail">(token ? "busy" : "fail");
  const [error, setError] = useState(token ? "" : "В ссылке нет токена отписки.");
  const [note, setNote] = useState("");
  const [muted, setMuted] = useState(true);
  const [busy, setBusy] = useState(false);
  // React 18 в строгом режиме вызывает эффект дважды; второй запрос дал бы человеку
  // ошибку поверх уже случившейся отписки.
  const asked = useRef(false);
  const navigate = useNavigate();

  const apply = (next: boolean) => {
    setBusy(true);
    unsubscribeByToken(token, next)
      .then((r) => { setNote(r.note); setMuted(r.muted); setState("done"); })
      .catch((e) => {
        setError(httpDetail(e) ?? "Ссылка недействительна или устарела.");
        setState("fail");
      })
      .finally(() => setBusy(false));
  };

  useEffect(() => {
    if (!token || asked.current) return;
    asked.current = true;
    apply(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="auth-card">
      <h1 className="auth-title">Письма об обсуждении</h1>
      {state === "busy" && <p className="page-sub">Выполняем…</p>}
      {state === "done" && (
        <>
          <p className="page-sub">{note}</p>
          {/* Возврат — на том же экране: искать его в профиле человек не пойдёт. */}
          <Button variant="ghost" loading={busy} onClick={() => apply(!muted)}>
            {muted ? "Вернуть письма об этом обсуждении" : "Всё-таки не писать"}
          </Button>
        </>
      )}
      {state === "fail" && (
        <>
          <div className="error" role="alert">{error}</div>
          <p className="page-sub" style={{ marginTop: 10 }}>
            Письма об обсуждениях можно выключить целиком в профиле — этой ссылки для
            этого не нужно.
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
