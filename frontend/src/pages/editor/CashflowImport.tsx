import { useMemo, useState } from "react";
import type { Actualization } from "../../api/model";
import {
  applyCashflow, articleKey, FACT_LINES, suggest, type CashflowReport, type ParsedSheet,
  type Source,
} from "../../cashflowXlsx";
import { Button, Modal, ScrollRegion, SelectField } from "../../components/ui";

/**
 * Факт ДДС из файла (L7): человек **видит сопоставление до загрузки** — куда ляжет каждая
 * статья и откуда это взято (сохранено с прошлого раза, точное название, подсказка по
 * словам), — и может поменять. После загрузки — отчёт: что легло куда, что нет и почему.
 */

const SOURCE: Record<Source, string> = {
  saved: "как в прошлый раз",
  exact: "по названию",
  hint: "подсказка — проверьте",
  none: "не сопоставлена",
};

const OPTIONS: [string, string][] = [
  ["", "— не загружать —"],
  ...FACT_LINES.map((l): [string, string] => [l.code, `${l.code} · ${l.label}`]),
];

export function CashflowImport({ sheet, actualization, n, onApply, onClose }: {
  sheet: ParsedSheet;
  actualization: Actualization;
  n: number;
  onApply: (next: Actualization) => void;
  onClose: () => void;
}) {
  const initial = useMemo(() => Object.fromEntries(sheet.articles.map((a) => {
    const s = suggest(a.label, actualization.mapping ?? {});
    return [articleKey(a.label), s];
  })), [sheet, actualization.mapping]);
  const [choice, setChoice] = useState<Record<string, string>>(
    () => Object.fromEntries(Object.entries(initial).map(([k, s]) => [k, s.code])));
  const [report, setReport] = useState<CashflowReport | null>(null);

  const months = sheet.months;
  const range = months.length
    ? `М${months[0] + 1}${months.length > 1 ? `–М${months[months.length - 1] + 1}` : ""}`
    : "—";

  const apply = () => {
    const result = applyCashflow(actualization, sheet, choice, n);
    onApply(result.actualization);
    setReport(result.report);
  };

  return (
    <Modal open onClose={onClose} title="Факт ДДС из файла" maxWidth={760}
           sub={`Статей: ${sheet.articles.length}, месяцы горизонта: ${range}. Сопоставление ` +
                "запомнится — в следующий раз спрашивать не придётся."}
           actions={report ? <Button onClick={onClose}>Готово</Button> : (
             <>
               <Button variant="ghost" onClick={onClose}>Отмена</Button>
               <Button onClick={apply}>Загрузить факт</Button>
             </>
           )}>
      {!report && (
        <>
          {(sheet.skippedColumns.length > 0 || sheet.skippedRows.length > 0) && (
            <ul className="cfi-notes">
              {sheet.skippedColumns.map((c) => <li key={c}>Не загружается колонка {c}.</li>)}
              {sheet.skippedRows.map((r) => (
                <li key={r}>Пропущена строка «{r}» — итог или остаток, а не поток.</li>
              ))}
            </ul>
          )}
          <ScrollRegion className="cfi-list" label="Сопоставление статей">
            {sheet.articles.map((a) => {
              const key = articleKey(a.label);
              const source = initial[key]?.source ?? "none";
              return (
                <div key={key} className="cfi-row">
                  <SelectField label={a.label} value={choice[key] ?? ""} options={OPTIONS}
                               onChange={(v) => setChoice((c) => ({ ...c, [key]: v }))} />
                  <span className={"cfi-source cfi-source--" + source}>{SOURCE[source]}</span>
                </div>
              );
            })}
          </ScrollRegion>
        </>
      )}
      {report && (
        <div className="cfi-report" role="status">
          <div className="cfi-report__title">
            Загружено статей: {report.loaded.length}; факт — до М{report.actualUntil + 1}.
          </div>
          <ul className="cfi-notes">
            {report.loaded.map((l) => (
              <li key={l.label}>«{l.label}» → {l.code}, месяцев: {l.months}.</li>
            ))}
            {report.ignored.map((i) => <li key={i.label}>«{i.label}» не загружена: {i.reason}.</li>)}
            {report.unreadable.map((u) => <li key={u}>{u}.</li>)}
            {report.signs.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
      )}
    </Modal>
  );
}
