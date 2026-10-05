import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { type DraftScale, getBusinessPlanDraft, listAuditSubjects } from "../api/audit";
import { httpDetail, httpStatus } from "../api/client";
import type { ProjectDetail } from "../api/model";
import {
  createProject,
  createProjectFromModel,
  createProjectFromTemplate,
  listTemplates,
  type TemplateInfo,
} from "../api/projects";
import { CubeHero } from "../components/CubeHero";
import { PRODUCTS } from "../components/product";
import { useToast } from "../components/Toast";
import { Button, Field } from "../components/ui";
import { usePageTitle } from "../pageTitle";

/**
 * Первый проект «Финанс-Элита» (пакет G, G12): цель → основа → название. Устроен как
 * онбординг «Аудита» — рейл с шагами слева, шаг справа, — и так же **создаёт настоящий
 * проект одним запросом на последнем шаге**: брошенный на полпути мастер не оставляет
 * полупустых проектов.
 *
 * Решения, которые легко потерять при следующей правке экрана:
 *
 * • **Оговорка шаблона — до создания.** Числа в шаблоне выдуманы (первый пункт его
 *   допущений), и человек читает это на шаге выбора, рядом с тем, что выбирает, а не
 *   после — в редакторе, где цифры уже выглядят как его собственные.
 * • **Горизонт шаблона не меняется.** Ряды шаблона заданы на свой срок, а движок
 *   дополняет короткие ряды нулями: продлить горизонт здесь значило бы молча обнулить
 *   продажи после срока шаблона. Горизонт выбирается у пустой модели, у шаблона — назван
 *   и меняется потом на вкладке «Проект», где видно, что ряды надо продлить.
 * • **Дата старта — подпись периодов**, и её можно выбрать и у шаблона: расчёт ведётся
 *   по месяцам от старта, числа от даты не зависят.
 * • **Из дела «Аудита»** (G14): черновик собирает сервер (`business-plan-draft`) — стартовый
 *   баланс последнего периода и дату после него, — а мастер показывает его оговорки
 *   **до** создания: что отнесено условно, что не перенесено. **Единицу сумм называет
 *   человек** («в рублях» / «в тысячах»): у дела её нет, и угадать значило бы ошибиться
 *   в тысячу раз. Пока выбора нет, черновик не запрашивается.
 */

type Goal = "new" | "existing" | "audit";

/** Цель проекта: что человек планирует. От неё — порядок шаблонов и «что дальше». */
const GOALS: Array<[Goal, string, string]> = [
  ["new", "Новый бизнес",
   "Запуск с нуля: вложения, выход на объём, окупаемость. Стартовый баланс пустой."],
  ["existing", "Действующий бизнес",
   "Развитие того, что уже работает: остатки на дату старта — стартовый баланс, " +
   "купленное раньше оборудование — с датой приобретения до старта."],
  ["audit", "Из дела «Аудита»",
   "Проверенная фирма: стартовый баланс — из последнего периода дела, старт — после " +
   "него. Что отнесено условно, мастер покажет до создания."],
];

/** В чём введены суммы дела: единицы у дела нет, отвечает человек. */
const SCALES: Array<[DraftScale, string, string]> = [
  [1, "В рублях", "Суммы переносятся как введены."],
  [1000, "В тысячах рублей", "Как в формах РСБУ: суммы умножаются на 1000."],
];

/** Шаги рейла: подпись и что на шаге происходит. Последний — результат, а не ввод. */
const STEPS: Array<[string, string]> = [
  ["Цель", "новый, действующий или из дела"],
  ["Основа", "шаблон, пустая модель или дело; старт"],
  ["Название", "и проект создаётся"],
  ["Проект создан", "дальше — цифры"],
];

/** «Пустая модель» в выборе основы — не шаблон, у неё свой горизонт. */
const EMPTY = "";

const MIN_MONTHS = 1;
const MAX_MONTHS = 600;
const DEFAULT_MONTHS = 36;

/**
 * Первое число следующего месяца, `YYYY-MM-DD`. Бизнес-план начинается в будущем, и
 * предлагать идущий месяц значило бы начинать модель с уже прожитых недель. Собирается
 * из календарных частей, без часового пояса: `toISOString` западнее Гринвича дал бы
 * последнее число прошлого месяца.
 */
export function nextMonthStart(now: Date = new Date()): string {
  const year = now.getMonth() === 11 ? now.getFullYear() + 1 : now.getFullYear();
  const month = (now.getMonth() + 1) % 12 + 1;
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

/** Шаблоны под цель — первыми: «действующий бизнес» ищет шаблон с остатками на старте. */
export function splitByGoal(templates: TemplateInfo[], goal: Goal): [TemplateInfo[], TemplateInfo[]] {
  const fits = (t: TemplateInfo) => Boolean(t.existing_business) === (goal === "existing");
  return [templates.filter(fits), templates.filter((t) => !fits(t))];
}

function monthsWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "месяц";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "месяца";
  return "месяцев";
}

export function ProjectOnboardingPage() {
  usePageTitle("Новый проект");
  const navigate = useNavigate();
  const toast = useToast();
  // Пришли со страницы дела («Бизнес-план из дела»): цель и дело уже выбраны.
  const [params] = useSearchParams();
  const presetSubject = params.get("from") === "audit" ? params.get("subject") : null;
  const [step, setStep] = useState(presetSubject ? 2 : 1);
  const [goal, setGoal] = useState<Goal>(presetSubject ? "audit" : "new");
  const [basis, setBasis] = useState<string>(EMPTY);
  const [months, setMonths] = useState(String(DEFAULT_MONTHS));
  const [start, setStart] = useState(() => nextMonthStart());
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ProjectDetail | null>(null);
  const [subjectId, setSubjectId] = useState<string | null>(presetSubject);
  const [scale, setScale] = useState<DraftScale | null>(null);
  /** Дату старта из черновика дела подставляем, пока человек не выбрал свою. */
  const [startEdited, setStartEdited] = useState(false);

  const fromAudit = goal === "audit";
  const { data: templates, isError: templatesFailed } = useQuery({
    queryKey: ["templates"], queryFn: listTemplates,
  });
  const subjects = useQuery({
    queryKey: ["audit-subjects"], queryFn: listAuditSubjects, enabled: fromAudit, retry: false,
  });
  const draft = useQuery({
    queryKey: ["business-plan-draft", subjectId, scale],
    queryFn: () => getBusinessPlanDraft(subjectId!, scale!, DEFAULT_MONTHS),
    enabled: fromAudit && subjectId !== null && scale !== null,
    retry: false,
  });
  // Выбранный раньше шаблон не действует, если цель сменилась на дело.
  const template = fromAudit ? null : (templates ?? []).find((t) => t.id === basis) ?? null;
  const [fitting, others] = splitByGoal(templates ?? [], goal);
  const subject = (subjects.data ?? []).find((s) => s.id === subjectId) ?? null;
  const startValue = fromAudit && !startEdited && draft.data?.start_date
    ? draft.data.start_date : start;

  const monthsNum = Number(months);
  const monthsErr = template || (Number.isInteger(monthsNum) && monthsNum >= MIN_MONTHS
    && monthsNum <= MAX_MONTHS) ? "" : `Целое число от ${MIN_MONTHS} до ${MAX_MONTHS}`;
  const startErr = /^\d{4}-\d{2}-\d{2}$/.test(startValue) ? "" : "Укажите дату старта";
  const pickStart = (value: string) => { setStart(value); setStartEdited(true); };
  const auditNotReady = fromAudit && !draft.data;

  const create = useMutation({
    mutationFn: () => {
      const fallback = fromAudit && subject ? `${subject.name} — бизнес-план` : template?.name;
      const title = name.trim() || fallback || "Новый проект";
      if (fromAudit && draft.data) {
        const m = draft.data.model;
        return createProjectFromModel(title, {
          ...m, header: { ...m.header, start_date: startValue, duration_months: monthsNum } });
      }
      return template
        ? createProjectFromTemplate(template.id, title, startValue)
        : createProject(title, monthsNum, startValue);
    },
    onSuccess: (p) => { setCreated(p); setStep(4); },
    onError: () => toast("Не удалось создать проект", { kind: "error" }),
  });

  const choice = (id: string, title: string, note: string, chip?: string) => (
    <button key={id || "empty"} type="button" aria-pressed={basis === id}
            className={"onb__choice" + (basis === id ? " onb__choice--on" : "")}
            onClick={() => setBasis(id)}>
      <span className="onb__choicetitle">
        {title}
        {chip && <span className="onb__chip">{chip}</span>}
      </span>
      <span className="onb__choicenote">{note}</span>
    </button>
  );

  /** Основа из дела «Аудита» (G14): дело, единицы сумм, оговорки черновика. */
  const auditBasis = (
    <>
      <p className="onb__lead">
        Стартовый баланс переносится из последнего периода дела. Выручку и
        расходы мастер не переносит: отчёт дела описывает прошлое, а план — будущее.
      </p>
      <div className="onb__choices">
        {subjects.isLoading && <div className="onb__note">Загружаем дела…</div>}
        {subjects.isError && (
          <div className="onb__note">
            {httpStatus(subjects.error) === 403 || httpStatus(subjects.error) === 402
              ? "Нет доступа к делам «Аудита»: продукт не подключён организации или "
                + "не хватает прав. Начните с шаблона или пустой модели."
              : "Список дел не загрузился — начните с шаблона или пустой модели."}
          </div>
        )}
        {subjects.data?.length === 0 && (
          <div className="onb__note">
            В организации нет дел «Аудита» — начните с шаблона или пустой модели.
          </div>
        )}
        {(subjects.data ?? []).map((s) => (
          <button key={s.id} type="button" aria-pressed={subjectId === s.id}
                  className={"onb__choice" + (subjectId === s.id ? " onb__choice--on" : "")}
                  onClick={() => setSubjectId(s.id)}>
            <span className="onb__choicetitle">
              {s.name}
              {s.industry && <span className="onb__chip">{s.industry}</span>}
            </span>
            <span className="onb__choicenote">
              {s.balanced ? "баланс сходится"
                : "баланс не сходится — перенести его нельзя, пока отчётность не исправлена"}
            </span>
          </button>
        ))}
      </div>

      <div className="onb__grouphead">В чём введены суммы дела</div>
      <div className="onb__choices" role="radiogroup" aria-label="Единицы сумм дела">
        {SCALES.map(([value, title, note]) => (
          <button key={value} type="button" role="radio" aria-checked={scale === value}
                  className={"onb__choice" + (scale === value ? " onb__choice--on" : "")}
                  onClick={() => setScale(value)}>
            <span className="onb__choicetitle">{title}</span>
            <span className="onb__choicenote">{note}</span>
          </button>
        ))}
      </div>
      {/* Единицы у дела нет: угадать значило бы ошибиться в тысячу раз. */}
      {subjectId !== null && scale === null && (
        <div className="onb__note">
          Единицы у дела нет — суммы вводятся как есть. Выберите, в чём они, и
          мастер покажет, что и куда перенесётся.
        </div>
      )}
      {draft.isError && (
        <div className="onb__note">{httpDetail(draft.error) ?? "Черновик не собрался."}</div>
      )}
      {draft.data && (
        <>
          <div className="onb__grouphead">Что и куда перенесётся</div>
          <ul className="onb__assume">
            {draft.data.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </>
      )}
      <div className="onb__row">
        <Field label="Горизонт, месяцев" type="number" min={MIN_MONTHS}
               max={MAX_MONTHS} value={months} error={monthsErr}
               onChange={(e) => setMonths(e.target.value)} />
        <Field label="Дата старта" type="date" value={startValue} error={startErr}
               onChange={(e) => pickStart(e.target.value)} />
      </div>
    </>
  );

  /** Основа из шаблона или пустой модели (G12). */
  const templateBasis = (
    <>
      <p className="onb__lead">
        Шаблон заполняет структуру — продукты, издержки, штат, вложения, — и модель
        сразу считается. Пустая модель начинается с чистого листа.
      </p>

      <div className="onb__choices">
        {choice(EMPTY, "Пустая модель", "Структуру и цифры вводите сами.")}
        {fitting.length > 0 && <div className="onb__grouphead">Шаблоны под цель</div>}
        {fitting.map((t) => choice(t.id, t.name, t.description, t.industry))}
        {others.length > 0 && <div className="onb__grouphead">Другие шаблоны</div>}
        {others.map((t) => choice(t.id, t.name, t.description, t.industry))}
      </div>
      {templatesFailed && (
        <div className="onb__note">
          Список шаблонов не загрузился — можно начать с пустой модели.
        </div>
      )}

      {template ? (
        <>
          {/* Допущения — до создания: первый пункт говорит, что числа выдуманы. */}
          <div className="onb__grouphead">Допущения шаблона</div>
          <ul className="onb__assume">
            {template.assumptions.map((a) => <li key={a}>{a}</li>)}
          </ul>
          {template.shows && (
            <div className="onb__note"><b>Что показывает:</b> {template.shows}</div>
          )}
          {template.duration_months ? (
            <div className="onb__note">
              Горизонт шаблона — {template.duration_months}{" "}
              {monthsWord(template.duration_months)}: ряды заданы на этот срок.
              Меняется потом на вкладке «Проект» — ряды при этом надо продлить, иначе
              после срока шаблона продажи и издержки считаются нулевыми.
            </div>
          ) : null}
          <div className="onb__row">
            <Field label="Дата старта" type="date" value={startValue} error={startErr}
                   onChange={(e) => pickStart(e.target.value)} />
          </div>
        </>
      ) : (
        <div className="onb__row">
          <Field label="Горизонт, месяцев" type="number" min={MIN_MONTHS}
                 max={MAX_MONTHS} value={months} error={monthsErr}
                 onChange={(e) => setMonths(e.target.value)} />
          <Field label="Дата старта" type="date" value={startValue} error={startErr}
                 onChange={(e) => pickStart(e.target.value)} />
        </div>
      )}
    </>
  );

  return (
    <div className="onb">
      <aside className="onb__rail">
        <div className="onb__brand">
          <div className="onb__cube">
            <CubeHero accent={PRODUCTS.business.cubeAccent} backdrop="transparent"
                      showEnvironment={false} showOrbit={false} pointerTilt={false} />
          </div>
          <span className="onb__brandword">Финанс&nbsp;Элит</span>
        </div>

        <div>
          <div className="onb__eyebrow">Первый проект</div>
          <div className="onb__railtitle">
            {step === 4 ? "Проект создан — осталось ввести цифры" : "Три шага до модели"}
          </div>
          <ol className="onb__steps">
            {STEPS.map(([label, note], i) => {
              const n = i + 1;
              const state = step > n ? "done" : step === n ? "on" : "off";
              return (
                <li className={`onb__step onb__step--${state}`} key={label}>
                  <span className="onb__mark">{step > n ? "✓" : n}</span>
                  <span className="onb__stepbody">
                    <span className="onb__steplabel">{label}</span>
                    <span className="onb__stepnote">{note}</span>
                  </span>
                </li>
              );
            })}
          </ol>
        </div>

        <div>
          <div className="onb__progress">
            <div className="onb__progressfill" style={{ width: `${step * 25}%` }} />
          </div>
          <div className="onb__progressnote">
            {step === 4 ? "проект создан" : `шаг ${step} из 3`}
          </div>
        </div>
      </aside>

      <section className="onb__content">
        {step === 1 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 1 из 3</div>
            <h1 className="onb__title">Что вы планируете</h1>
            <p className="onb__lead">
              Цель меняет не расчёт, а то, с чего начать: у действующего бизнеса есть
              остатки на дату старта, у нового — нет, а проверенную в «Аудите» фирму можно
              начать с её баланса. Потом всё правится в редакторе.
            </p>
            <div className="onb__choices" role="radiogroup" aria-label="Цель проекта">
              {GOALS.map(([id, title, note]) => (
                <button key={id} type="button" role="radio" aria-checked={goal === id}
                        className={"onb__choice" + (goal === id ? " onb__choice--on" : "")}
                        onClick={() => setGoal(id)}>
                  <span className="onb__choicetitle">{title}</span>
                  <span className="onb__choicenote">{note}</span>
                </button>
              ))}
            </div>
            <div className="onb__foot">
              <Button onClick={() => setStep(2)}>Дальше</Button>
              <Button variant="link" onClick={() => navigate("/projects")}>
                Пропустить мастер
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 2 из 3</div>
            <h1 className="onb__title">С чего начать</h1>
            {fromAudit ? auditBasis : templateBasis}

            <div className="onb__foot">
              <Button onClick={() => setStep(3)}
                      disabled={!!monthsErr || !!startErr || auditNotReady}>
                Дальше
              </Button>
              <Button variant="link" onClick={() => setStep(1)}>Назад</Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 3 из 3</div>
            <h1 className="onb__title">Как назвать проект</h1>
            <p className="onb__lead">
              Название видно в списке проектов и на титуле бизнес-плана. Проект создаётся
              этой кнопкой — до неё ничего не сохранено.
            </p>
            <Field label="Название проекта" autoFocus
                   placeholder={fromAudit && subject ? `${subject.name} — бизнес-план`
                     : template?.name ?? "Напр. «Завод полимерной упаковки»"}
                   value={name} onChange={(e) => setName(e.target.value)} />
            <div className="onb__foot">
              <Button onClick={() => create.mutate()} loading={create.isPending}>
                Создать проект
              </Button>
              <Button variant="link" onClick={() => setStep(2)}>Назад</Button>
            </div>
          </div>
        )}

        {step === 4 && created && (
          <div className="onb__pane onb__pane--done">
            <div className="onb__donecube">
              <CubeHero accent={PRODUCTS.business.cubeAccent} backdrop="transparent"
                        showEnvironment={false} />
            </div>
            <div className="onb__check">✓</div>
            {/* Имя — заголовок, а не вставка в предложение: кавычки в кавычках. */}
            <div className="onb__eyebrow">Проект создан</div>
            <h1 className="onb__title">{created.name}</h1>
            <div className="onb__next">
              <div className="onb__nexthead">Что дальше</div>
              {template && (
                <div className="onb__nextrow">
                  Числа шаблона выдуманы — замените их своими: сбыт, издержки, штат,
                  вложения. Допущения шаблона остаются в его описании в списке шаблонов.
                </div>
              )}
              {fromAudit && (
                <div className="onb__nextrow">
                  Стартовый баланс перенесён из дела, а что отнесено условно (краткосрочные
                  обязательства — займами, запасы — одной строкой), записано в разделе
                  «Происхождение модели» на вкладке «Документ» — он уйдёт и в бизнес-план.
                  Сбыт и издержки введите сами.
                </div>
              )}
              {goal === "existing" && (
                <div className="onb__nextrow">
                  Введите остатки на дату старта на вкладке «Валюта и старт»: актив должен
                  сходиться с пассивом, иначе расчёт не пойдёт. Оборудование, купленное до
                  старта, — актив с месяцем приобретения меньше нуля.
                </div>
              )}
              <div className="onb__nextrow">
                Когда цифры введены — «Рассчитать»: отчёты, показатели и ревью плана,
                которое покажет, что стоит перепроверить.
              </div>
            </div>
            <div className="onb__foot">
              <Button onClick={() => navigate(`/projects/${created.id}`)}>Открыть редактор</Button>
              <Button variant="link" onClick={() => navigate("/projects")}>Ко всем проектам</Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
