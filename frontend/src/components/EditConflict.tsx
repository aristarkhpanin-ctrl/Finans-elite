import { useState } from "react";
import { httpDetail, httpStatus } from "../api/client";
import { Button, Modal } from "./ui";

/**
 * Конфликт одновременной правки (G2) — один на оба продукта.
 *
 * Раньше ``PUT`` перезаписывал модель целиком, и правки того, кто сохранил первым,
 * исчезали молча. Теперь сервер отвечает 409 и называет, кто и когда сохранил раньше, а
 * этот экран предлагает три выхода — и **ни один не выбирается за человека**:
 *
 * 1. **Сохранить свои правки отдельно** (новый проект / новое дело) — безопасный выход:
 *    ничьи правки не пропадают, сравнить обе версии можно спокойно. Поэтому он первый.
 * 2. **Открыть их версию** — свои несохранённые правки пропадут.
 * 3. **Сохранить свои поверх** — пропадут правки, сохранённые раньше (их мог оставить
 *    коллега, а мог и сам человек в соседней вкладке — поэтому не «правки коллеги»).
 *
 * Оба разрушительных выхода требуют второго нажатия и прямо говорят, **чьи** правки
 * пропадут: модалка, где «перезаписать» стоит рядом с «отменой», однажды нажмут не глядя.
 *
 * Копия логики на каждой странице разошлась бы: поэтому здесь и хук, и сама модалка.
 */

/** Запасной текст, если сервер почему-то не прислал причину. */
export const CONFLICT_FALLBACK =
  "Пока вы правили, это сохранил кто-то другой. Ваши правки не записаны.";

/** Состояние конфликта: открыт ли он и что сказал сервер. */
export function useEditConflict() {
  const [detail, setDetail] = useState<string | null>(null);
  return {
    detail,
    open: detail !== null,
    close: () => setDetail(null),
    /** Если ошибка — конфликт правок, открыть его и вернуть ``true``. */
    catchConflict(e: unknown): boolean {
      if (httpStatus(e) !== 409) return false;
      setDetail(httpDetail(e) ?? CONFLICT_FALLBACK);
      return true;
    },
  };
}

type Kind = "project" | "case";

/** Род у проекта и дела разный — формулировки заданы на каждый, а не склеены. */
const WORDS: Record<Kind, { title: string; copy: string; copyHint: string }> = {
  project: {
    title: "Пока вы правили, проект изменили",
    copy: "Сохранить мои правки новым проектом",
    copyHint: "Обе версии останутся: ничьи правки не пропадут.",
  },
  case: {
    title: "Пока вы правили, дело изменили",
    copy: "Сохранить мои правки новым делом",
    copyHint: "Обе версии останутся: ничьи правки не пропадут.",
  },
};

type Action = "theirs" | "overwrite";

export function EditConflictModal({
  kind, detail, open, busy, onClose, onSaveCopy, onTakeTheirs, onOverwrite,
}: {
  kind: Kind;
  detail: string | null;
  open: boolean;
  busy?: boolean;
  onClose: () => void;
  onSaveCopy: () => void;
  onTakeTheirs: () => void;
  onOverwrite: () => void;
}) {
  const [armed, setArmed] = useState<Action | null>(null);
  const words = WORDS[kind];

  const close = () => { setArmed(null); onClose(); };
  const press = (action: Action, run: () => void) => {
    if (armed === action) { setArmed(null); run(); } else { setArmed(action); }
  };

  return (
    <Modal open={open} onClose={close} title={words.title} maxWidth={560}
           actions={<Button variant="ghost" onClick={close} disabled={busy}>Отмена</Button>}>
      <p className="page-sub" style={{ marginTop: 0 }}>{detail}</p>
      <div style={{ display: "grid", gap: 10 }}>
        <div>
          <Button block loading={busy && armed === null} onClick={onSaveCopy} disabled={busy}>
            {words.copy}
          </Button>
          <div className="page-sub" style={{ margin: "4px 0 0" }}>{words.copyHint}</div>
        </div>
        <div>
          <Button block variant="ghost" disabled={busy}
                  onClick={() => press("theirs", onTakeTheirs)}>
            {armed === "theirs" ? "Точно: открыть их версию" : "Открыть их версию"}
          </Button>
          <div className="page-sub" style={{ margin: "4px 0 0" }}>
            {armed === "theirs"
              ? "Нажмите ещё раз: ваши несохранённые правки пропадут."
              : "Ваши несохранённые правки пропадут."}
          </div>
        </div>
        <div>
          <Button block variant="danger" disabled={busy}
                  onClick={() => press("overwrite", onOverwrite)}>
            {armed === "overwrite" ? "Точно: сохранить мои поверх" : "Сохранить мои правки поверх"}
          </Button>
          <div className="page-sub" style={{ margin: "4px 0 0" }}>
            {armed === "overwrite"
              ? "Нажмите ещё раз: правки, сохранённые раньше вас, пропадут."
              : "Правки, сохранённые раньше вас, пропадут — останется ваша версия целиком."}
          </div>
        </div>
      </div>
    </Modal>
  );
}
