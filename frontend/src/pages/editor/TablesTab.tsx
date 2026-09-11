import type { UserRow, UserTable } from "../../api/model";
import { IconTrash } from "../../components/icons";
import { Button } from "../../components/ui";

interface Props {
  tables: UserTable[];
  onChange: (tables: UserTable[]) => void;
}

const FUNCTIONS_HELP =
  "СДВИГ(x,k) · АККУМ(x) · РАЗН(x) · ДИСК(x,ставка) · ЧПС(x,ставка) · ВНД(x) · СУММ(x) · " +
  "СРЗНАЧ(x) · МИН/МАКС(x[,y]) · МОДУЛЬ(x) · ОКРУГЛ(x[,зн]) · СТЕПЕНЬ(x,p) · " +
  "ЕСЛИ(усл,а,б) · ЭЛЕМЕНТ(x,t) · ЧАСТЬ(x,от,до) · EXP · LN";

/** Вкладка «Таблицы»: пользовательские таблицы из строк-формул над результатом расчёта. */
export function TablesTab({ tables, onChange }: Props) {
  const addTable = () =>
    onChange([...tables, { id: crypto.randomUUID(), name: `Таблица ${tables.length + 1}`,
                           rows: [{ name: "Строка 1", formula: "" }] }]);
  const updTable = (i: number, patch: Partial<UserTable>) =>
    onChange(tables.map((t, k) => (k === i ? { ...t, ...patch } : t)));
  const rmTable = (i: number) => onChange(tables.filter((_, k) => k !== i));

  const updRow = (ti: number, ri: number, patch: Partial<UserRow>) =>
    updTable(ti, { rows: tables[ti].rows.map((r, k) => (k === ri ? { ...r, ...patch } : r)) });
  const addRow = (ti: number) =>
    updTable(ti, { rows: [...tables[ti].rows, { name: `Строка ${tables[ti].rows.length + 1}`, formula: "" }] });
  const rmRow = (ti: number, ri: number) =>
    updTable(ti, { rows: tables[ti].rows.filter((_, k) => k !== ri) });

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Таблицы пользователя</div>
          <div className="tab-head__sub">
            Собственные показатели формулами над строками отчётов — считаются при каждом расчёте.
          </div>
        </div>
        <Button onClick={addTable}>＋&nbsp;&nbsp;Таблица</Button>
      </div>

      <div className="ft-help">
        <div className="ft-help__row">
          <b>Идентификаторы:</b> строки отчётов по кодам — I1…I28 (ОПУ), C1…C29 (Кэш-фло),
          B1…B34 (Баланс), P1…P7 (прибыль), N — горизонт (мес.).
        </div>
        <div className="ft-help__row"><b>Функции:</b> {FUNCTIONS_HELP}</div>
        <div className="ft-help__row">
          <b>Пример:</b> <code>ОКРУГЛ(I8 / I4 * 100, 1)</code> — валовая маржа, %;{" "}
          <code>АККУМ(C13 + C20)</code> — накопленный поток до финансирования.
        </div>
      </div>

      {tables.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Нет таблиц</div>
          <div className="tab-empty__sub">
            Добавьте таблицу и строки-формулы — результат появится на странице результатов
            во вкладке «Таблицы».
          </div>
          <Button onClick={addTable}>＋&nbsp;&nbsp;Добавить первую таблицу</Button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {tables.map((t, ti) => (
            <div className="line-card" key={t.id}>
              <div className="line-card__head">
                <div className="line-card__idx">{ti + 1}</div>
                <div className="line-card__name">
                  <input value={t.name ?? ""} placeholder="Название таблицы"
                         onChange={(e) => updTable(ti, { name: e.target.value })} />
                </div>
                <button type="button" className="line-card__del" title="Удалить таблицу"
                        onClick={() => rmTable(ti)}>
                  <IconTrash size={16} />
                </button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {t.rows.map((r, ri) => (
                  <div className="ft-row" key={ri}>
                    <input className="ft-row__name" value={r.name} placeholder="Имя строки"
                           onChange={(e) => updRow(ti, ri, { name: e.target.value })} />
                    <input className="ft-row__formula" value={r.formula}
                           placeholder="Формула, напр. СУММ(I1) или I8 / I4"
                           spellCheck={false}
                           onChange={(e) => updRow(ti, ri, { formula: e.target.value })} />
                    <button type="button" className="line-card__del" title="Удалить строку"
                            onClick={() => rmRow(ti, ri)}>
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
                <button type="button" className="add-row add-row--sm" onClick={() => addRow(ti)}>
                  ＋&nbsp;&nbsp;Строка-формула
                </button>
              </div>
            </div>
          ))}
          <button type="button" className="add-row" onClick={addTable}>
            ＋&nbsp;&nbsp;Добавить таблицу
          </button>
        </div>
      )}
    </div>
  );
}
