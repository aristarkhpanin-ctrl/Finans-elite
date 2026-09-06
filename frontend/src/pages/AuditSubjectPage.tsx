import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ASSET_LINES,
  EQLIAB_LINES,
  INCOME_LINES,
  INCOME_MEMO_LINES,
  MEMO_LINES,
  RATIO_GROUPS,
  REPORTING_STANDARDS,
  REVALUABLE_LINES,
  analyzeAuditSubject,
  downloadAuditReport,
  getAuditSubject,
  updateAuditSubject,
  type AuditLineOut,
  type AuditModel,
  type AuditPeriod,
  type RatioThreshold,
  type ReportingStandard,
  type Revaluation,
  type UserMetric,
} from "../api/audit";
import { IconDownload, IconPrint, IconTrash, IconUpload } from "../components/icons";
import { useToast } from "../components/Toast";
import { Button } from "../components/ui";
import { AuditInputIssues } from "../components/AuditInputIssues";
import { AuditEarnings } from "../components/AuditEarnings";
import { AuditFlags } from "../components/AuditFlags";
import { AuditObligations } from "../components/AuditObligations";
import { AuditProcedures } from "../components/AuditProcedures";
import { AuditSummary } from "../components/AuditSummary";
import { AuditValuation } from "../components/AuditValuation";
import { AuditRisk } from "../components/AuditRisk";
import { AuditPlanFact } from "../components/AuditPlanFact";
import { AuditPrintReport } from "../components/AuditPrintReport";
import { allBalanced, balanceGaps, serverGaps } from "../auditBalance";
import { downloadAuditXlsx } from "../auditExport";
import { downloadAuditTemplate, parseAuditXlsx } from "../auditXlsx";
import { fmtMoney } from "../format";

type Tab = "summary" | "subject" | "input" | "reports" | "ratios" | "trends" | "diagnostics"
  | "flags" | "earnings" | "obligations" | "procedures" | "valuation" | "risk" | "planfact" | "methods" | "opinion";

/** Подписи вкладок (в том же виде, что были — ни одна не исчезла). */
const TAB_LABEL: Record<Tab, string> = {
  summary: "Сводка",
  subject: "Субъект",
  input: "Ввод отчётности",
  reports: "Отчёты",
  ratios: "Коэффициенты",
  trends: "Тренды",
  diagnostics: "Диагностика",
  flags: "Реестр флагов",
  earnings: "Качество прибыли",
  obligations: "Обязательства и залоги",
  procedures: "Чек-лист процедур",
  valuation: "Оценка стоимости",
  risk: "Анализ рисков",
  planfact: "План-факт",
  methods: "Методики",
  opinion: "Заключение",
};

/**
 * Разделы дела по макетам: ввод и отчёты — «Отчётность» (Экран 2), коэффициенты,
 * тренды и диагностика — «Финансовое состояние».
 *
 * Раздела «Финансовое состояние» на макетах нет: они ведут покупателя от скана к цене
 * и не показывают анализ финсостояния цели. Это **осознанное расширение** (решение
 * фазы 0): выбрасывать 16 показателей, горизонталь, вертикаль и три модели Альтмана
 * ради полноты картинки нельзя — это работающая, оттестированная часть продукта.
 *
 * Вкладки не свёрнуты и не переписаны — они сгруппированы. Внутри раздела с
 * несколькими вкладками появляется вторая полоса; содержимое каждой вкладки прежнее.
 */
const SECTIONS: [string, string, Tab[]][] = [
  ["summary", "Сводка", ["summary"]],
  ["subject", "Субъект", ["subject"]],
  ["reporting", "Отчётность", ["input", "reports"]],
  ["health", "Финансовое состояние", ["ratios", "trends", "diagnostics"]],
  ["quality", "Качество прибыли", ["earnings"]],
  ["flags", "Реестр флагов", ["flags"]],
  ["obligations", "Обязательства", ["obligations"]],
  ["procedures", "Процедуры", ["procedures"]],
  ["valuation", "Оценка", ["valuation", "risk"]],
  ["planfact", "План-факт", ["planfact"]],
  ["methods", "Методики", ["methods"]],
  ["opinion", "Заключение", ["opinion"]],
];

/** Раздел, которому принадлежит вкладка. */
function sectionOf(tab: Tab): string {
  return SECTIONS.find(([, , tabs]) => tabs.includes(tab))?.[0] ?? "summary";
}

/** Подписи и тон зон скоринга / статусов нормативов. */
const ZONE_LABEL: Record<string, string> = {
  safe: "устойчивость", grey: "неопределённость", distress: "высокий риск",
};
const STATUS_LABEL: Record<string, string> = {
  good: "норма", warn: "внимание", risk: "вне норматива",
};
const toneOf = (v: string | null): string =>
  v === "safe" || v === "good" ? "tone--ok"
    : v === "grey" || v === "warn" ? "tone--warn"
      : v === "distress" || v === "risk" ? "tone--risk" : "";
const LIGHT_LABEL: Record<string, string> = {
  ok: "Устойчивое состояние", warning: "Есть зоны внимания", risk: "Признаки неустойчивости",
};

/** Число из строки-Decimal (для форматирования; пусто/невалидно → null). */
const dec = (v: string | null | undefined): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

const fmtNum = (v: string | null | undefined, digits = 2): string => {
  const x = dec(v);
  return x === null ? "—" : x.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

const fmtPct = (v: string | null | undefined, digits = 1): string => {
  const x = dec(v);
  return x === null ? "—" : (x * 100).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }) + "%";
};

/** Показатели, которые выводятся как проценты (доли), а не как коэффициенты. */
const PCT_RATIOS = /^(Рентабельность|Коэффициент автономии|Суммарные обязательства)/;
/** Показатели в денежных единицах. */
const MONEY_RATIOS = /^(Чистый оборотный капитал)/;

export function AuditSubjectPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["audit-subject", id],
    queryFn: () => getAuditSubject(id),
  });

  const [name, setName] = useState("");
  const [model, setModel] = useState<AuditModel | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [printMode, setPrintMode] = useState(false);
  const [dirty, setDirty] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (data) { setName(data.name); setModel(data.model); setDirty(false); }
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateAuditSubject(id, name, model!),
    onSuccess: (s) => {
      qc.setQueryData(["audit-subject", id], s);
      qc.invalidateQueries({ queryKey: ["audit-subjects"] });
      qc.invalidateQueries({ queryKey: ["audit-analysis", id] });   // пересчитать анализ
      setDirty(false);
      toast("Сохранено", { kind: "success" });
    },
    onError: () => toast("Не удалось сохранить", { kind: "error" }),
  });

  // Анализ считается по сохранённым данным — только для аналитических вкладок.
  const isAnalysisTab = tab === "reports" || tab === "ratios" || tab === "trends"
    || tab === "diagnostics" || tab === "opinion" || tab === "methods" || tab === "flags" || tab === "earnings"
    || tab === "obligations" || tab === "procedures" || tab === "summary" || tab === "valuation" || tab === "risk" || tab === "planfact";
  const analysis = useQuery({
    queryKey: ["audit-analysis", id],
    queryFn: () => analyzeAuditSubject(id),
    enabled: isAnalysisTab,
  });

  if (isLoading || !model || !data) {
    return <div className="page-sub" style={{ padding: 24 }}>Загрузка…</div>;
  }
  const m = model;
  const n = m.periods.length;

  const patch = (p: Partial<AuditModel>) => { setModel({ ...m, ...p }); setDirty(true); };
  const setPeriod = (i: number, up: Partial<AuditPeriod>) =>
    patch({ periods: m.periods.map((p, k) => (k === i ? { ...p, ...up } : p)) });
  const addPeriod = () =>
    patch({ periods: [...m.periods, { label: "", kind: "year" }] });
  const removePeriod = (i: number) =>
    patch({ periods: m.periods.filter((_, k) => k !== i) });

  // Установить значение ячейки таблицы (balance|income) строки code в периоде t.
  const setCell = (which: "balance" | "income", code: string, t: number, v: string) => {
    const table = { ...m[which] };
    const row = [...(table[code] ?? [])];
    while (row.length < n) row.push("");
    row[t] = v;
    table[code] = row;
    patch({ [which]: table } as Partial<AuditModel>);
  };

  // Пользовательские методики (фаза G): свои показатели-формулы.
  const metrics: UserMetric[] = m.user_metrics ?? [];
  const setMetrics = (next: UserMetric[]) => patch({ user_metrics: next });
  const addMetric = () => setMetrics([...metrics, { name: "Новый показатель", formula: "" }]);
  const updMetric = (i: number, up: Partial<UserMetric>) =>
    setMetrics(metrics.map((x, k) => (k === i ? { ...x, ...up } : x)));
  const rmMetric = (i: number) => setMetrics(metrics.filter((_, k) => k !== i));

  // Переоценка статей (v2): поправки с корреспонденцией в капитале.
  const revals: Revaluation[] = m.revaluations ?? [];
  const setRevals = (next: Revaluation[]) => patch({ revaluations: next });
  const addReval = () =>
    setRevals([...revals, { code: REVALUABLE_LINES[0][0], label: "", amounts: [] }]);
  const updReval = (i: number, up: Partial<Revaluation>) =>
    setRevals(revals.map((x, k) => (k === i ? { ...x, ...up } : x)));
  const rmReval = (i: number) => setRevals(revals.filter((_, k) => k !== i));
  const setRevalAmount = (i: number, t: number, v: string) => {
    const row = [...(revals[i].amounts ?? [])];
    while (row.length < n) row.push("");
    row[t] = v;
    updReval(i, { amounts: row });
  };

  // Свои нормативы (v2): переопределяют универсальные пороги диагностики.
  const thresholds: RatioThreshold[] = m.thresholds ?? [];
  const setThresholds = (next: RatioThreshold[]) => patch({ thresholds: next });
  const addThreshold = () => setThresholds([...thresholds,
    { ratio: "", direction: "higher", risk_edge: "0", good_edge: "0" }]);
  const updThreshold = (i: number, up: Partial<RatioThreshold>) =>
    setThresholds(thresholds.map((x, k) => (k === i ? { ...x, ...up } : x)));
  const rmThreshold = (i: number) => setThresholds(thresholds.filter((_, k) => k !== i));

  // Названия показателей, которым можно задать норматив (из посчитанного анализа).
  const ratioNames: string[] = analysis.data
    ? RATIO_GROUPS.flatMap(([key]) => Object.keys(analysis.data!.ratios[key] ?? {}))
    : [];

  // Импорт отчётности из XLSX (фаза F): round-trip через шаблон приложения.
  const onImportFile = async (file: File) => {
    try {
      const res = await parseAuditXlsx(file, m);
      if (res.matched > 0) { setModel(res.model); setDirty(true); }
      const extra: string[] = [];
      if (res.skipped.length) extra.push(`не распознаны: ${res.skipped.join(", ")}`);
      if (res.ignored) extra.push(`служебных строк: ${res.ignored}`);
      const sub = extra.length ? extra.join(" · ") : undefined;
      if (res.matched > 0) {
        toast(`Импорт: обновлено строк — ${res.matched}. Проверьте и сохраните.`,
              { kind: "success", sub });
      } else {
        toast("Импорт: подходящих строк не найдено", { kind: "warn", sub });
      }
    } catch {
      toast("Не удалось прочитать файл — нужен XLSX по шаблону", { kind: "error" });
    }
  };

  // Сходимость баланса: пока правки не сохранены — предварительная оценка по форме,
  // после сохранения — вердикт сервера (он считает в Decimal и требует ровно нуля).
  const draftGaps = balanceGaps(m.balance, n);
  const gapsKop = dirty ? draftGaps : serverGaps(data.balance_gap);
  const balanced = dirty ? allBalanced(draftGaps) : data.balanced;
  const gapRub = (t: number) => (gapsKop[t] ?? 0) / 100;

  const grid = (which: "balance" | "income", lines: [string, string][], title: string,
                note?: string) => (
    <div className="audit-block">
      <div className="audit-block__title">{title}</div>
      {note && <div className="field-note" style={{ marginBottom: 10 }}>{note}</div>}
      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Статья</th>
              {m.periods.map((p, t) => (
                <th key={t}>{p.label || `Период ${t + 1}`}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map(([code, label]) => (
              <tr key={code}>
                <td className="audit-grid__rowhead">{label}</td>
                {m.periods.map((_, t) => (
                  <td key={t}>
                    <input
                      className="audit-cell"
                      inputMode="decimal"
                      value={m[which][code]?.[t] ?? ""}
                      placeholder="0"
                      onChange={(e) => setCell(which, code, t, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  // Печатный бланк — отдельный экран, а не модалка: он занимает лист целиком, и его
  // печатают как есть. Тулбар помечен screen-only и на бумагу не попадает.
  if (printMode && analysis.data) {
    return (
      <div className="print-mode">
        <div className="print-toolbar">
          <div style={{ minWidth: 0 }}>
            <div className="print-toolbar__title">Печатный бланк · PDF (A4, книжная)</div>
            <div className="print-toolbar__sub">
              Два листа: заключение и показатели. Бумага не зависит от темы интерфейса,
              отрицательные значения — в скобках.
            </div>
          </div>
          <div className="print-toolbar__actions">
            <Button variant="ghost" onClick={() => setPrintMode(false)}>← К заключению</Button>
            <Button onClick={() => window.print()}>
              <IconPrint size={15} />
              <span style={{ marginLeft: 7 }}>Печать</span>
            </Button>
          </div>
        </div>
        <AuditPrintReport analysis={analysis.data} name={name}
                          industry={m.industry ?? ""}
                          standard={m.reporting_standard ?? "rsbu"} />
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <button type="button" className="link-back" onClick={() => navigate("/audit")}>← К субъектам</button>
          <input
            className="subject-name"
            value={name}
            placeholder="Название субъекта"
            onChange={(e) => { setName(e.target.value); setDirty(true); }}
          />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {/* Выгрузка всего анализа одним файлом — доступна там, где анализ уже посчитан. */}
          {isAnalysisTab && analysis.data && analysis.data.n > 0 && (
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await downloadAuditXlsx(`${name || "Анализ"}.xlsx`, analysis.data!);
                  toast("Выгрузка XLSX скачана", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать выгрузку", { kind: "error" });
                }
              }}
            >
              <IconDownload size={15} />
              <span style={{ marginLeft: 6 }}>Выгрузка XLSX</span>
            </Button>
          )}
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>
            Сохранить
          </Button>
        </div>
      </div>

      <div className="seg" style={{ marginBottom: 10, flexWrap: "wrap" }}>
        {SECTIONS.map(([key, label, tabs]) => (
          <button
            key={key}
            className={"seg__btn" + (sectionOf(tab) === key ? " seg__btn--active" : "")}
            onClick={() => setTab(tabs[0])}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Вторая полоса — только там, где в разделе больше одной вкладки. Полоса из
          одной кнопки не выбор, а лишний шум. */}
      {(() => {
        const tabs = SECTIONS.find(([key]) => key === sectionOf(tab))?.[2] ?? [];
        if (tabs.length < 2) return null;
        return (
          <div className="subseg" role="tablist" aria-label="Разделы вкладки">
            {tabs.map((key) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={"subseg__btn" + (tab === key ? " subseg__btn--active" : "")}
                onClick={() => setTab(key)}
              >
                {TAB_LABEL[key]}
              </button>
            ))}
          </div>
        );
      })()}

      {isAnalysisTab && dirty && (
        <div className="field-note field-note--warn" style={{ marginBottom: 12 }}>
          Есть несохранённые правки — анализ считается по сохранённым данным. Нажмите «Сохранить».
        </div>
      )}

      {/* Индикатор сходимости баланса (актив = пассив) */}
      <div className={"balance-banner " + (balanced ? "balance-banner--ok" : "balance-banner--bad")}>
        {balanced
          ? "Баланс сходится во всех периодах (актив = пассив)."
          : "Баланс не сходится — проверьте ввод:"}
        {dirty && " Предварительно: правки не сохранены."}
        {!balanced && (
          <span className="balance-banner__gaps">
            {m.periods.map((p, t) => (gapsKop[t] ?? 0) !== 0 && (
              <span key={t}>{p.label || `П${t + 1}`}: разрыв {fmtMoney(gapRub(t))}</span>
            ))}
          </span>
        )}
      </div>

      {tab === "subject" ? (
        <div className="audit-block">
          <div className="audit-block__title">Реквизиты и периоды</div>
          <div className="afields-grid" style={{ marginBottom: 16 }}>
            <label className="efield">
              <span className="efield__label">Валюта</span>
              <input className="efield__input" value={m.currency ?? ""} placeholder="RUB"
                     onChange={(e) => patch({ currency: e.target.value })} />
            </label>
            <label className="efield">
              <span className="efield__label">Отрасль</span>
              <input className="efield__input" value={m.industry ?? ""} placeholder="напр. Торговля"
                     onChange={(e) => patch({ industry: e.target.value })} />
            </label>
            <label className="efield">
              <span className="efield__label">Основа отчётности</span>
              <select className="efield__input" value={m.reporting_standard ?? "rsbu"}
                      onChange={(e) => patch({
                        reporting_standard: e.target.value as ReportingStandard,
                      })}>
                {REPORTING_STANDARDS.map(([key, label]) => (
                  <option value={key} key={key}>{label}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="field-note" style={{ marginBottom: 16 }}>
            Основа фиксируется как признак и попадает в заключение — платформа
            <b> не пересчитывает</b> отчётность из одной основы в другую. Форма ввода —
            агрегаты, одинаковые для любого стандарта; при своде группы участники с разными
            основами не смешиваются молча, а получают оговорку о несопоставимости.
          </div>

          <div className="audit-block__title" style={{ fontSize: 13 }}>Отчётные периоды</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {m.periods.map((p, i) => (
              <div className="ft-row" key={i}>
                <input className="efield__input" value={p.label} placeholder={`Период ${i + 1} (напр. 2024)`}
                       onChange={(e) => setPeriod(i, { label: e.target.value })} />
                <select className="efield__input" value={p.kind}
                        onChange={(e) => setPeriod(i, { kind: e.target.value as AuditPeriod["kind"] })}>
                  <option value="year">Год</option>
                  <option value="quarter">Квартал</option>
                  <option value="month">Месяц</option>
                </select>
                <button type="button" className="line-card__del" title="Удалить период"
                        disabled={n <= 1} onClick={() => removePeriod(i)}>
                  <IconTrash size={15} />
                </button>
              </div>
            ))}
            <button type="button" className="add-row add-row--sm" onClick={addPeriod}>
              ＋&nbsp;&nbsp;Добавить период
            </button>
          </div>
          <div className="field-note" style={{ marginTop: 10 }}>
            Тип периода задаёт его длину: показатели «в днях» считаются по ней, а потоковые
            (рентабельность, оборачиваемость) приводятся к году — квартал ×4, месяц ×12.
            Иначе периоды разной длины несопоставимы между собой.
          </div>
        </div>
      ) : tab === "input" ? (
        <>
          <div className="audit-block" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await downloadAuditTemplate(`${name || "Отчётность"}-шаблон.xlsx`, m);
                  toast("Шаблон XLSX скачан", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать шаблон", { kind: "error" });
                }
              }}
            >
              <IconDownload size={15} />
              <span style={{ marginLeft: 6 }}>Шаблон XLSX</span>
            </Button>
            <Button variant="ghost" onClick={() => fileRef.current?.click()}>
              <IconUpload size={15} />
              <span style={{ marginLeft: 6 }}>Импорт XLSX</span>
            </Button>
            <span className="page-sub" style={{ fontSize: 12 }}>
              Скачайте шаблон, заполните в Excel и загрузите обратно — периоды задаются здесь.
            </span>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onImportFile(f);
                e.target.value = "";
              }}
            />
          </div>
          {grid("balance", ASSET_LINES, "Баланс — актив")}
          {grid("balance", EQLIAB_LINES, "Баланс — пассив (капитал и обязательства)")}
          {grid("balance", MEMO_LINES, "Расшифровка (в итоги баланса не входит)",
                "Нераспределённая прибыль нужна моделям Альтмана. Рыночная капитализация "
                + "заполняется только для публичной компании: по ней считается классическая "
                + "модель Альтмана, а без неё эта модель не показывается — балансовый "
                + "капитал вместо рыночного дал бы другую модель под её именем.")}
          {grid("income", INCOME_LINES, "Отчёт о финансовых результатах")}
          {grid("income", INCOME_MEMO_LINES, "Расшифровка ОФР (в подытоги не входит)",
                "Амортизация нужна, чтобы EBITDA вообще существовала: в аналитической "
                + "форме её нет, и без этой строки нормализуется EBIT — показатель, "
                + "который меньше EBITDA ровно на амортизацию. Мультипликатор сделки, "
                + "применённый не к тому показателю, ошибётся на ту же величину.")}

          <div className="audit-block">
            <div className="tab-head" style={{ marginBottom: 10 }}>
              <div className="audit-block__title" style={{ marginBottom: 0 }}>
                Переоценка статей
              </div>
              <Button variant="ghost" onClick={addReval}>＋&nbsp;&nbsp;Поправка</Button>
            </div>
            <div className="field-note" style={{ marginBottom: 12 }}>
              Экспертные поправки к балансу: дооценка основных средств, безнадёжная
              дебиторка, неликвидные запасы. У каждой поправки есть корреспонденция в
              капитале (актив «+» увеличивает капитал, обязательство «+» уменьшает),
              поэтому баланс остаётся сходящимся. Весь анализ считается по
              скорректированной форме, а сами поправки перечисляются в оговорках —
              переоценённые числа не выдаются за учётные.
            </div>
            {revals.length === 0 ? (
              <p className="page-sub" style={{ margin: 0, fontSize: 12.5 }}>
                Поправок нет — анализ идёт по учётным данным.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {revals.map((rv, i) => (
                  <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div className="ft-row">
                      <select className="efield__input" value={rv.code}
                              onChange={(e) => updReval(i, { code: e.target.value })}>
                        {REVALUABLE_LINES.map(([code, label]) => (
                          <option value={code} key={code}>{label}</option>
                        ))}
                      </select>
                      <input className="efield__input" value={rv.label}
                             placeholder="Причина (напр. безнадёжная дебиторка)"
                             onChange={(e) => updReval(i, { label: e.target.value })} />
                      <button type="button" className="line-card__del" title="Удалить поправку"
                              onClick={() => rmReval(i)}>
                        <IconTrash size={15} />
                      </button>
                    </div>
                    <div style={{ overflowX: "auto" }}>
                      <table className="audit-grid">
                        <thead>
                          <tr>
                            {m.periods.map((p, t) => (
                              <th key={t}>{p.label || `Период ${t + 1}`}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            {m.periods.map((_, t) => (
                              <td key={t}>
                                <input className="audit-cell" inputMode="decimal"
                                       value={rv.amounts?.[t] ?? ""} placeholder="0"
                                       onChange={(e) => setRevalAmount(i, t, e.target.value)} />
                              </td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : analysis.isLoading ? (
        <div className="page-sub" style={{ padding: 24 }}>Считаем анализ…</div>
      ) : analysis.isError || !analysis.data ? (
        <div className="error-state" style={{ padding: "40px 24px" }}>
          <div className="error-state__ico">!</div>
          <div className="error-state__title">Не удалось выполнить анализ</div>
          <Button variant="ghost" onClick={() => analysis.refetch()}>Повторить</Button>
        </div>
      ) : analysis.data.n === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Нет периодов</div>
          <div className="tab-empty__sub">
            Добавьте отчётные периоды и введите отчётность — появятся отчёты, коэффициенты и тренды.
          </div>
        </div>
      ) : tab === "reports" ? (
        <>
          <StatementTable title="Баланс (аналитическая форма)"
                          periods={analysis.data.periods} lines={analysis.data.balance} />
          <StatementTable title="Отчёт о финансовых результатах"
                          periods={analysis.data.periods} lines={analysis.data.income} />
        </>
      ) : tab === "ratios" ? (
        <>
          {RATIO_GROUPS.map(([key, title]) => {
            const group = analysis.data.ratios[key] ?? {};
            const names = Object.keys(group);
            if (names.length === 0) return null;
            return (
              <div className="audit-block" key={key}>
                <div className="audit-block__title">{title}</div>
                <div style={{ overflowX: "auto" }}>
                  <table className="audit-grid">
                    <thead>
                      <tr>
                        <th className="audit-grid__rowhead">Показатель</th>
                        {analysis.data!.periods.map((p) => <th key={p}>{p}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {names.map((nm) => (
                        <tr key={nm}>
                          <td className="audit-grid__rowhead">{nm}</td>
                          {group[nm].map((v, t) => (
                            <td key={t} className="audit-val">
                              {MONEY_RATIOS.test(nm) ? fmtNum(v, 0)
                                : PCT_RATIOS.test(nm) ? fmtPct(v)
                                : fmtNum(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </>
      ) : tab === "methods" ? (
        <>
          <div className="audit-block">
            <div className="tab-head" style={{ marginBottom: 10 }}>
              <div className="audit-block__title" style={{ marginBottom: 0 }}>Свои показатели</div>
              <Button variant="ghost" onClick={addMetric}>＋&nbsp;&nbsp;Показатель</Button>
            </div>
            <div className="field-note" style={{ marginBottom: 12 }}>
              Формула считается по периодам над строками аналитической формы. Доступны коды:
              A_FIXED, A_INVENTORY, A_RECEIVABLE, A_CASH, A_CURRENT, A_TOTAL, P_EQUITY, P_LONG,
              P_SHORT, P_TOTAL, M_RETAINED, I_REVENUE, I_COGS, I_GROSS, I_OPEX, I_EBIT,
              I_INTEREST, I_OTHER, I_EBT, I_TAX, I_NET, а также N — число периодов.
              Например: <code>I_NET / I_REVENUE</code>.
            </div>
            {metrics.length === 0 ? (
              <p className="page-sub" style={{ margin: 0, fontSize: 12.5 }}>
                Методик пока нет. Добавьте свой показатель — он появится в анализе и в документе.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {metrics.map((mt, i) => (
                  <div className="ft-row" key={i}>
                    <input className="efield__input" value={mt.name} placeholder="Название показателя"
                           onChange={(e) => updMetric(i, { name: e.target.value })} />
                    <input className="efield__input" style={{ fontFamily: "var(--font-mono)" }}
                           value={mt.formula} placeholder="напр. I_NET / I_REVENUE"
                           onChange={(e) => updMetric(i, { formula: e.target.value })} />
                    <button type="button" className="line-card__del" title="Удалить показатель"
                            onClick={() => rmMetric(i)}>
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="audit-block">
            <div className="tab-head" style={{ marginBottom: 10 }}>
              <div className="audit-block__title" style={{ marginBottom: 0 }}>Свои нормативы</div>
              <Button variant="ghost" onClick={addThreshold}>＋&nbsp;&nbsp;Норматив</Button>
            </div>
            <div className="field-note" style={{ marginBottom: 12 }}>
              Переопределяют универсальные пороги диагностики. «Больше — лучше»: ниже границы
              риска — «вне норматива», выше границы нормы — «норма», между ними — «внимание»
              (для «меньше — лучше» наоборот). Несогласованный порог не применяется —
              останется универсальный, и об этом будет предупреждение.
            </div>
            {thresholds.length === 0 ? (
              <p className="page-sub" style={{ margin: 0, fontSize: 12.5 }}>
                Нормативов нет — применяются универсальные пороги.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {thresholds.map((th, i) => (
                  <div className="ft-row" key={i}>
                    <select className="efield__input" value={th.ratio}
                            onChange={(e) => updThreshold(i, { ratio: e.target.value })}>
                      <option value="">— выберите показатель —</option>
                      {ratioNames.map((nm) => <option key={nm} value={nm}>{nm}</option>)}
                    </select>
                    <select className="efield__input" value={th.direction}
                            onChange={(e) => updThreshold(i, { direction: e.target.value as RatioThreshold["direction"] })}>
                      <option value="higher">Больше — лучше</option>
                      <option value="lower">Меньше — лучше</option>
                    </select>
                    <input className="efield__input" inputMode="decimal" value={th.risk_edge}
                           placeholder="граница риска"
                           onChange={(e) => updThreshold(i, { risk_edge: e.target.value })} />
                    <input className="efield__input" inputMode="decimal" value={th.good_edge}
                           placeholder="граница нормы"
                           onChange={(e) => updThreshold(i, { good_edge: e.target.value })} />
                    <button type="button" className="line-card__del" title="Удалить норматив"
                            onClick={() => rmThreshold(i)}>
                      <IconTrash size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {analysis.data.revalued && (
            <div className="field-note field-note--warn" style={{ marginBottom: 12 }}>
              Показатели рассчитаны по отчётности <b>с учётом переоценки статей</b> — они
              отличаются от учётных данных. Перечень поправок — в оговорках ниже.
            </div>
          )}
          {analysis.data.warnings.length > 0 && (
            <div className="audit-block">
              {analysis.data.warnings.map((w, i) => (
                <div className="field-note field-note--warn" key={i}>{w}</div>
              ))}
            </div>
          )}

          {/* Находки о самих данных — отдельно от оговорок о результате: одно надо
              исправить, другое просто иметь в виду. */}
          <AuditInputIssues issues={analysis.data.input_issues ?? []}
                            periods={analysis.data.periods} />

          {analysis.data.user_metrics.length > 0 && (
            <div className="audit-block">
              <div className="audit-block__title">Результат (по сохранённым данным)</div>
              <div style={{ overflowX: "auto" }}>
                <table className="audit-grid">
                  <thead>
                    <tr>
                      <th className="audit-grid__rowhead">Показатель</th>
                      {analysis.data.periods.map((p) => <th key={p}>{p}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.data.user_metrics.map((u, i) => (
                      <tr key={i}>
                        <td className="audit-grid__rowhead">
                          {u.name}
                          {u.error && <span className="zone-chip tone--risk">ошибка</span>}
                        </td>
                        {u.values.map((v, k) => (
                          <td key={k} className="audit-val">{u.error ? "—" : fmtNum(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {analysis.data.user_metrics.filter((u) => u.error).map((u, i) => (
                <div className="field-note field-note--warn" key={i} style={{ marginTop: 8 }}>
                  {u.name}: {u.error}
                </div>
              ))}
            </div>
          )}
        </>
      ) : tab === "earnings" ? (
        <AuditEarnings
          quality={analysis.data.earnings}
          periods={analysis.data.periods}
          adjustments={m.earnings_adjustments ?? []}
          hasDepreciation={Boolean(m.income["M_DEPRECIATION"]?.some((v) => v !== ""))}
          onChange={(next) => patch({ earnings_adjustments: next })}
        />
      ) : tab === "flags" ? (
        <AuditFlags registry={analysis.data.flags} periods={analysis.data.periods} />
      ) : tab === "obligations" ? (
        <AuditObligations
          register={analysis.data.obligations}
          obligations={m.obligations ?? []}
          onChange={(next) => patch({ obligations: next })}
        />
      ) : tab === "summary" ? (
        <AuditSummary
          summary={analysis.data.summary}
          onInput={() => setTab("input")}
          onFlags={() => setTab("flags")}
          onProcedures={() => setTab("procedures")}
          onOpinion={() => setTab("opinion")}
        />
      ) : tab === "valuation" ? (
        <AuditValuation
          result={analysis.data.valuation}
          assumptions={m.valuation}
          onChange={(next) => patch({ valuation: next })}
        />
      ) : tab === "risk" ? (
        <AuditRisk
          result={analysis.data.risk}
          settings={m.risk}
          onChange={(next) => patch({ risk: next })}
        />
      ) : tab === "planfact" ? (
        <AuditPlanFact
          result={analysis.data.plan_fact}
          periods={m.periods.map((p, i) => p.label || `Период ${i + 1}`)}
          plan={m.seller_plan ?? {}}
          marks={m.realized_flags ?? []}
          onPlan={(next) => patch({ seller_plan: next })}
          onMarks={(next) => patch({ realized_flags: next })}
        />
      ) : tab === "procedures" ? (
        <AuditProcedures
          report={analysis.data.procedures}
          marks={m.procedure_marks ?? []}
          custom={m.custom_procedures ?? []}
          onMarks={(next) => patch({ procedure_marks: next })}
          onCustom={(next) => patch({ custom_procedures: next })}
        />
      ) : tab === "opinion" ? (
        <div className="audit-block">
          <div className="tab-head" style={{ marginBottom: 12 }}>
            <div className="audit-block__title" style={{ marginBottom: 0 }}>Экспертное заключение</div>
            <Button variant="ghost" onClick={() => setPrintMode(true)}>
              <IconPrint size={15} />
              <span style={{ marginLeft: 6 }}>Печатный бланк</span>
            </Button>
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await downloadAuditReport(id, `${name || "Заключение"}.docx`);
                  toast("Документ скачан", { kind: "success" });
                } catch {
                  toast("Не удалось сформировать документ", { kind: "error" });
                }
              }}
            >
              <IconDownload size={15} />
              <span style={{ marginLeft: 6 }}>Скачать DOCX</span>
            </Button>
          </div>
          {analysis.data.opinion.split("\n\n").map((block, i) => (
            <p key={i} className="opinion-block">
              {block.split("\n").map((line, j) => (
                <React.Fragment key={j}>{j > 0 && <br />}{line}</React.Fragment>
              ))}
            </p>
          ))}
          <div className="field-note" style={{ marginTop: 10 }}>
            Текст формируется автоматически по результатам анализа (без ИИ) и приводится
            целиком в документе DOCX.
          </div>
        </div>
      ) : tab === "diagnostics" ? (
        !analysis.data.diagnostics ? (
          <div className="tab-empty"><div className="tab-empty__title">Нет данных для диагностики</div></div>
        ) : (
          <>
            <div className={"diag-light diag-light--" + analysis.data.diagnostics.light}>
              <div className="diag-light__title">
                {LIGHT_LABEL[analysis.data.diagnostics.light] ?? analysis.data.diagnostics.light}
              </div>
              <div className="diag-light__sub">{analysis.data.diagnostics.summary}</div>
              <div className="diag-light__note">
                Оценка — по последнему периоду ({analysis.data.periods[analysis.data.periods.length - 1]}).
              </div>
            </div>

            <div className="audit-block">
              <div className="audit-block__title">Модели диагностики банкротства</div>
              <div style={{ overflowX: "auto" }}>
                <table className="audit-grid">
                  <thead>
                    <tr>
                      <th className="audit-grid__rowhead">Модель</th>
                      {analysis.data.periods.map((p) => <th key={p}>{p}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.data.diagnostics.scores.map((s) => (
                      <tr key={s.id}>
                        <td className="audit-grid__rowhead" title={s.note}>{s.name}</td>
                        {s.values.map((v, t) => (
                          <td key={t} className="audit-val">
                            {v === null ? "—" : fmtNum(v)}
                            {s.zones[t] && (
                              <span className={"zone-chip " + toneOf(s.zones[t])}>
                                {ZONE_LABEL[s.zones[t]!] ?? s.zones[t]}
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {analysis.data.diagnostics.scores.map((s) => (
                <div className="field-note" key={s.id} style={{ marginTop: 8 }}>{s.name}: {s.note}</div>
              ))}
            </div>

            <div className="audit-block">
              <div className="audit-block__title">Оценка показателей по нормативам</div>
              <div style={{ overflowX: "auto" }}>
                <table className="audit-grid">
                  <thead>
                    <tr>
                      <th className="audit-grid__rowhead">Показатель</th>
                      {analysis.data.periods.map((p) => <th key={p}>{p}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.data.diagnostics.assessments.map((a) => (
                      <tr key={a.group + a.name}>
                        <td className="audit-grid__rowhead">{a.name}</td>
                        {a.status.map((st, t) => (
                          <td key={t} className="audit-val">
                            {st ? (
                              <span className={"zone-chip " + toneOf(st)}>{STATUS_LABEL[st] ?? st}</span>
                            ) : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )
      ) : (
        <>
          <div className="audit-block">
            <div className="audit-block__title">Горизонтальный анализ (изменение к предыдущему периоду)</div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Статья</th>
                    {analysis.data.periods.map((p) => <th key={p} colSpan={2}>{p}</th>)}
                  </tr>
                  <tr>
                    <th className="audit-grid__rowhead"> </th>
                    {analysis.data.periods.map((p) => (
                      <React.Fragment key={p}>
                        <th style={{ fontWeight: 500 }}>Δ</th>
                        <th style={{ fontWeight: 500 }}>темп</th>
                      </React.Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.horizontal.map((t) => (
                    <tr key={t.code}>
                      <td className="audit-grid__rowhead">{t.label}</td>
                      {t.delta.map((d, i) => (
                        <React.Fragment key={i}>
                          <td className="audit-val">{d === null ? "—" : fmtNum(d, 0)}</td>
                          <td className={"audit-val " + trendTone(t.rate[i])}>{fmtPct(t.rate[i])}</td>
                        </React.Fragment>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="audit-block">
            <div className="audit-block__title">Вертикальный анализ (структура: доля в активе / выручке)</div>
            <div style={{ overflowX: "auto" }}>
              <table className="audit-grid">
                <thead>
                  <tr>
                    <th className="audit-grid__rowhead">Статья</th>
                    {analysis.data.periods.map((p) => <th key={p}>{p}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {analysis.data.vertical.map((s) => (
                    <tr key={s.code}>
                      <td className="audit-grid__rowhead">{s.label}</td>
                      {s.share.map((v, t) => <td key={t} className="audit-val">{fmtPct(v)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Знак темпа роста: рост — акцент, падение — тревожный тон. */
function trendTone(rate: string | null): string {
  const x = dec(rate);
  if (x === null || x === 0) return "";
  return x > 0 ? "audit-val--up" : "audit-val--down";
}

/** Таблица аналитической формы: строки-подытоги выделены. */
function StatementTable({ title, periods, lines }: {
  title: string;
  periods: string[];
  lines: AuditLineOut[];
}) {
  return (
    <div className="audit-block">
      <div className="audit-block__title">{title}</div>
      <div style={{ overflowX: "auto" }}>
        <table className="audit-grid">
          <thead>
            <tr>
              <th className="audit-grid__rowhead">Статья</th>
              {periods.map((p) => <th key={p}>{p}</th>)}
            </tr>
          </thead>
          <tbody>
            {lines.map((ln) => (
              <tr key={ln.code} className={ln.subtotal ? "audit-row--subtotal" : undefined}>
                <td className="audit-grid__rowhead">{ln.label}</td>
                {ln.values.map((v, t) => <td key={t} className="audit-val">{fmtNum(v, 0)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
