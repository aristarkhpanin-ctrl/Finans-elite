import { useEffect, useState } from "react";
import { IconWarning } from "./icons";
import { Button, Modal } from "./ui";

/**
 * Страж несохранённого ввода — один на оба продукта.
 *
 * В модель вводят десятки чисел подряд, и цена потери ввода — переписывать отчётность
 * заново. У редактора проекта такая защита была, у дела и группы «Финанс-Аудита» — нет:
 * закрытая вкладка или переход «← К субъектам» уносили введённое молча. Копий защиты
 * заводить нельзя ровно по той же причине, по какой конвейер разбора один: вторая копия
 * молча отстанет от первой. Поэтому она здесь одна.
 *
 * Закрывается два выхода: закрытие/перезагрузка вкладки (браузерный `beforeunload`) и
 * переходы **внутри приложения**, которые страница делает сама. Переход по ссылке в
 * шапке страж не ловит: приложение собрано на `BrowserRouter`, где блокировщика
 * маршрутизации нет, — и обещать больше, чем страж умеет, было бы хуже, чем не обещать.
 */

/** Отложенный переход: куда собирались и как туда попасть. */
export interface PendingLeave {
  label: string;
  go: () => void;
}

export function useUnsavedGuard(dirty: boolean) {
  const [pending, setPending] = useState<PendingLeave | null>(null);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";      // требуется частью браузеров, чтобы показать диалог
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  /** Уйти со страницы: без правок — сразу, с правками — через вопрос. */
  const tryNav = (label: string, go: () => void) => {
    if (dirty) setPending({ label, go });
    else go();
  };

  return { tryNav, pending, cancel: () => setPending(null) };
}

/**
 * Вопрос перед уходом. Три исхода названы прямо — «сохранить», «уйти без сохранения»,
 * «остаться»: диалог, из которого не видно, что случится с введённым, не лучше
 * молчаливой потери.
 */
export function UnsavedLeaveModal({ pending, saving, onSave, onCancel }: {
  pending: PendingLeave | null;
  saving: boolean;
  /** Сохранить и уйти. Ошибка сохранения оставляет пользователя на странице. */
  onSave: () => Promise<void>;
  onCancel: () => void;
}) {
  return (
    <Modal open={!!pending} onClose={onCancel} maxWidth={420}>
      <div style={{ textAlign: "center" }}>
        <div className="modal-warn-ico">
          <IconWarning size={22} />
        </div>
        <h3 className="modal__title">Несохранённые изменения</h3>
        <div className="modal__sub">
          Введённое ещё не сохранено. Сохранить перед переходом в «{pending?.label}»?
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          <Button loading={saving}
                  onClick={async () => {
                    const go = pending!.go;
                    await onSave();
                    onCancel();
                    go();
                  }}>
            Сохранить и выйти
          </Button>
          <Button variant="ghost"
                  onClick={() => {
                    const go = pending!.go;
                    onCancel();
                    go();
                  }}>
            Выйти без сохранения
          </Button>
          <Button variant="link" style={{ alignSelf: "center" }} onClick={onCancel}>
            Отмена
          </Button>
        </div>
      </div>
    </Modal>
  );
}
