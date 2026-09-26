import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createProject,
  createProjectFromTemplate,
  listTemplates,
  type TemplateInfo,
} from "../api/projects";
import type { ProjectDetail } from "../api/model";
import { CubeHero } from "../components/CubeHero";
import { PRODUCTS } from "../components/product";
import { useToast } from "../components/Toast";
import { Button, Field } from "../components/ui";

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
 * • **Третьей цели («из дела „Аудита“») пока нет** — мост между продуктами строится
 *   отдельным шагом (G14); кнопка без него обещала бы то, чего продукт не умеет.
 */

type Goal = "new" | "existing";

/** Цель проекта: что человек планирует. От неё — порядок шаблонов и «что дальше». */
const GOALS: Array<[Goal, string, string]> = [
  ["new", "Новый бизнес",
   "Запуск с нуля: вложения, выход на объём, окупаемость. Стартовый баланс пустой."],
  ["existing", "Действующий бизнес",
   "Развитие того, что уже работает: остатки на дату старта — стартовый баланс, " +
   "купленное раньше оборудование — с датой приобретения до старта."],
];

/** Шаги рейла: подпись и что на шаге происходит. Последний — результат, а не ввод. */
const STEPS: Array<[string, string]> = [
  ["Цель", "новый бизнес или действующий"],
  ["Основа", "шаблон или пустая модель, старт"],
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
  const navigate = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState(1);
  const [goal, setGoal] = useState<Goal>("new");
  const [basis, setBasis] = useState<string>(EMPTY);
  const [months, setMonths] = useState(String(DEFAULT_MONTHS));
  const [start, setStart] = useState(() => nextMonthStart());
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ProjectDetail | null>(null);

  const { data: templates, isError: templatesFailed } = useQuery({
    queryKey: ["templates"], queryFn: listTemplates,
  });
  const template = (templates ?? []).find((t) => t.id === basis) ?? null;
  const [fitting, others] = splitByGoal(templates ?? [], goal);

  const monthsNum = Number(months);
  const monthsErr = template || (Number.isInteger(monthsNum) && monthsNum >= MIN_MONTHS
    && monthsNum <= MAX_MONTHS) ? "" : `Целое число от ${MIN_MONTHS} до ${MAX_MONTHS}`;
  const startErr = /^\d{4}-\d{2}-\d{2}$/.test(start) ? "" : "Укажите дату старта";

  const create = useMutation({
    mutationFn: () => {
      const title = name.trim() || template?.name || "Новый проект";
      return template
        ? createProjectFromTemplate(template.id, title, start)
        : createProject(title, monthsNum, start);
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
              остатки на дату старта, у нового — нет. Потом всё правится в редакторе.
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
                  <Field label="Дата старта" type="date" value={start} error={startErr}
                         onChange={(e) => setStart(e.target.value)} />
                </div>
              </>
            ) : (
              <div className="onb__row">
                <Field label="Горизонт, месяцев" type="number" min={MIN_MONTHS}
                       max={MAX_MONTHS} value={months} error={monthsErr}
                       onChange={(e) => setMonths(e.target.value)} />
                <Field label="Дата старта" type="date" value={start} error={startErr}
                       onChange={(e) => setStart(e.target.value)} />
              </div>
            )}

            <div className="onb__foot">
              <Button onClick={() => setStep(3)} disabled={!!monthsErr || !!startErr}>
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
                   placeholder={template?.name ?? "Напр. «Завод полимерной упаковки»"}
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
