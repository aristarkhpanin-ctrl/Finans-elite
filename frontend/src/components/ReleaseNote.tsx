import type { CalcResponse } from "../api/calc";
import { signedMoney } from "../format";

type Release = NonNullable<CalcResponse["working_capital_release"]>;

/**
 * Закрытие расчётов на конец горизонта (движок 0.9.57, пакет K): оговорка с сервера и
 * состав. В последнем месяце поток показателей получает дебиторку, запасы и НДС к
 * получению плюсом, налоги, кредиторку и полученные авансы минусом; без расшифровки это
 * число читалось бы как выручка месяца. Текст оговорки — с сервера: второй его копией
 * экран разошёлся бы с печатью и документом. При выключенном закрытии блок остаётся —
 * он называет, что в показатели не вошло.
 */
export function ReleaseNote({ release }: { release?: Release | null }) {
  if (!release) return null;
  return (
    <div className="release-note">
      <div className="field-note">{release.note}</div>
      {release.items.length > 0 && (
        <ul className="release-note__items" aria-label="Состав закрытия расчётов">
          {release.items.map((item) => (
            <li key={item.code} className="release-note__item">
              <span className="release-note__label">{item.label}</span>
              <span className="release-note__amount">{signedMoney(item.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
