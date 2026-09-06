import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createAuditSubject,
  emptyAuditModel,
  REPORTING_STANDARDS,
  type AuditPeriod,
  type AuditSubjectOut,
  type ReportingStandard,
} from "../api/audit";
import { httpStatus } from "../api/client";
import { addMember, roleLabel, ROLES, type Member } from "../api/org";
import { useAuth } from "../auth/AuthContext";
import { CubeHero } from "../components/CubeHero";
import { PRODUCTS } from "../components/product";
import { useToast } from "../components/Toast";
import { Button, Field, SelectField } from "../components/ui";

/**
 * Первый вход в «Финанс-Аудит» (макет «Экран 12 — Онбординг»): рейл с шагами слева,
 * шаг справа, в конце — заведённое дело.
 *
 * Мастер **заводит настоящее дело**, а не показывает экскурсию: три шага собирают то,
 * что действительно есть в модели (реквизиты, периоды) и в организации (участники), и
 * дело создаётся одним запросом на последнем шаге — брошенный на полпути мастер не
 * оставляет за собой полупустых дел.
 *
 * Чего в мастере нет и почему — сказано на том шаге, где этого ждут:
 *
 * • **ИНН и подтягивание форм 1 и 2 из ФНС.** Интеграции с ФНС у платформы нет,
 *   отчётность вводится или импортируется из XLSX. Поле «ИНН», которое ничего не
 *   подтягивает, обещало бы её наличие — а хранить его негде: в модели субъекта
 *   такого реквизита не существует.
 * • **Глубина проверки «экспресс · 8 / полная · 24 / для банка · 31».** Чек-лист
 *   процедур один на все дела; сокращённый набор не убрал бы работу, а спрятал бы
 *   процедуры, которые всё равно делать, и «31» в каталоге просто нет.
 * • **Роль организации, задающая набор процедур и шаблон заключения.** Ни того, ни
 *   другого от роли в продукте не зависит — сохранённая роль ни на что не влияла бы.
 * • **Доступ к делу.** Права выдаются на всю организацию: участник видит все дела,
 *   и журнал доступа тоже общий. «Доступ выдаётся к делу, а не ко всему пространству»
 *   из макета описывает другую модель прав.
 * • **Фоновый скан на шесть минут и письмо о готовности.** Анализ считается сразу и
 *   на месте, как только введена отчётность; почты платформа не отправляет вовсе.
 */

/** Шаги рейла: подпись и что на шаге происходит. Последний — результат, а не ввод. */
const STEPS: Array<[string, string]> = [
  ["Дело", "реквизиты фирмы-цели"],
  ["Периоды", "за какие периоды есть отчётность"],
  ["Команда", "кто работает в организации"],
  ["Дело заведено", "анализ считается сразу"],
];

const PERIOD_KINDS: [string, string][] = [
  ["year", "Год"],
  ["quarter", "Квартал"],
  ["month", "Месяц"],
];

const PERIOD_PLACEHOLDER: Record<AuditPeriod["kind"], string> = {
  year: "2025",
  quarter: "2025 Q1",
  month: "янв 2025",
};

/** Сколько периодов предлагает мастер. Больше — на вкладке «Ввод», там же и меньше. */
const MIN_PERIODS = 1;
const MAX_PERIODS = 12;

/** Роли, назначаемые при приглашении: владелец — только создатель организации. */
const ASSIGNABLE = ROLES.filter(([k]) => k !== "owner");

/**
 * Подписи периодов по умолчанию — последние **завершённые** годы по возрастанию:
 * отчётность за идущий год ещё не сдана, и предлагать его подписью значило бы звать
 * ввести то, чего у пользователя нет. У кварталов и месяцев подписи не угадываются:
 * какой именно квартал закрыт, знает только пользователь.
 */
export function defaultLabels(kind: AuditPeriod["kind"], count: number,
                              now: Date = new Date()): string[] {
  if (kind !== "year") return Array(count).fill("");
  const last = now.getFullYear() - 1;
  return Array.from({ length: count }, (_, i) => String(last - count + 1 + i));
}

/** Ссылка активации: писем платформа не отправляет — её передаёт пригласивший. */
export function inviteLink(token: string, origin: string): string {
  return `${origin}/activate?token=${token}`;
}

export function AuditOnboardingPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { organizations, currentOrgId } = useAuth();
  const myRole = organizations.find((o) => o.id === currentOrgId)?.role ?? "";
  const canInvite = myRole === "owner" || myRole === "admin";

  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [standard, setStandard] = useState<ReportingStandard>("rsbu");
  const [kind, setKind] = useState<AuditPeriod["kind"]>("year");
  const [labels, setLabels] = useState<string[]>(() => defaultLabels("year", 3));
  const [invited, setInvited] = useState<Member[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("analyst");
  const [inviteErr, setInviteErr] = useState("");
  const [created, setCreated] = useState<AuditSubjectOut | null>(null);

  /** Смена периодичности переписывает подписи: угаданные годы у кварталов — мусор. */
  function pickKind(next: AuditPeriod["kind"]) {
    setKind(next);
    setLabels(defaultLabels(next, labels.length));
  }

  function setCount(next: number) {
    const n = Math.max(MIN_PERIODS, Math.min(MAX_PERIODS, next));
    setLabels(defaultLabels(kind, n));
  }

  const create = useMutation({
    mutationFn: () =>
      createAuditSubject(name.trim(), {
        ...emptyAuditModel(),
        name: name.trim(),
        industry: industry.trim(),
        reporting_standard: standard,
        periods: labels.map((label) => ({ label: label.trim(), kind })),
      }),
    onSuccess: (s) => { setCreated(s); setStep(4); },
    onError: () => toast("Не удалось завести дело", { kind: "error" }),
  });

  const invite = useMutation({
    mutationFn: () =>
      addMember(currentOrgId!, { email: inviteEmail.trim(), full_name: inviteName.trim(),
                                 role: inviteRole }),
    onSuccess: (m) => {
      setInvited((list) => [...list, m]);
      setInviteEmail("");
      setInviteName("");
      setInviteErr("");
    },
    onError: (e: unknown) => {
      const s = httpStatus(e);
      setInviteErr(
        s === 403
          ? "Недостаточно прав (нужен владелец или администратор)"
          : s === 402
            ? "Достигнут лимит участников тарифа"
            : "Не удалось добавить участника",
      );
    },
  });

  const railTitle = step === 4
    ? "Дело заведено — осталась отчётность"
    : "Три шага до первого анализа";

  return (
    <div className="onb">
      <aside className="onb__rail">
        <div className="onb__brand">
          <div className="onb__cube">
            <CubeHero accent={PRODUCTS.audit.cubeAccent} backdrop="transparent"
                      showEnvironment={false} showOrbit={false} pointerTilt={false} />
          </div>
          <span className="onb__brandword">Финанс&nbsp;Аудит</span>
        </div>

        <div>
          <div className="onb__eyebrow">Настройка пространства</div>
          <div className="onb__railtitle">{railTitle}</div>
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
            {step === 4 ? "настройка завершена" : `шаг ${step} из 3`}
          </div>
        </div>
      </aside>

      <section className="onb__content">
        {step === 1 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 1 из 3</div>
            <h1 className="onb__title">Дело о фирме-цели</h1>
            <p className="onb__lead">
              Дело — это одна проверяемая фирма: её отчётность, находки, оценка и
              заключение. Реквизиты потом правятся на вкладке «Субъект».
            </p>

            <Field label="Название фирмы-цели" placeholder="ООО «Пример»" value={name}
                   autoFocus onChange={(e) => setName(e.target.value)} />
            <Field label="Отрасль" placeholder="напр. Перевозки" value={industry}
                   note="Подставляется в заключение и помогает искать дело в списке."
                   onChange={(e) => setIndustry(e.target.value)} />
            <SelectField label="Основа отчётности" value={standard}
                         options={REPORTING_STANDARDS}
                         onChange={(v) => setStandard(v as ReportingStandard)} />

            {/* Обещание макета — «введите ИНН, формы 1 и 2 подтянутся из ФНС» —
                не перенесено: такой интеграции у платформы нет. Поле, которое ничего
                не подтягивает, обещало бы её наличие. */}
            <div className="onb__note">
              По ИНН отчётность не подтягивается: интеграции с ФНС у платформы нет.
              Числа вводятся на вкладке «Ввод» или импортируются из XLSX.
            </div>

            <div className="onb__foot">
              <Button onClick={() => setStep(2)} disabled={!name.trim()}>Дальше</Button>
              <Button variant="link" onClick={() => navigate("/audit")}>
                Пропустить настройку
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 2 из 3</div>
            <h1 className="onb__title">Периоды отчётности</h1>
            <p className="onb__lead">
              Периоды задают ширину всех таблиц дела. Периодичность нужна расчёту:
              по ней считаются показатели «в днях», а потоковые величины приводятся
              к году.
            </p>

            <div className="onb__row">
              <SelectField label="Периодичность" value={kind} options={PERIOD_KINDS}
                           onChange={(v) => pickKind(v as AuditPeriod["kind"])} />
              <Field label="Сколько периодов" type="number" min={MIN_PERIODS}
                     max={MAX_PERIODS} value={String(labels.length)}
                     onChange={(e) => setCount(Number(e.target.value))} />
            </div>

            <div className="onb__periods">
              {labels.map((label, i) => (
                <input
                  key={i}
                  className="input onb__period"
                  aria-label={`Подпись периода ${i + 1}`}
                  placeholder={PERIOD_PLACEHOLDER[kind]}
                  value={label}
                  onChange={(e) => setLabels(
                    (ls) => ls.map((v, j) => (j === i ? e.target.value : v)))}
                />
              ))}
            </div>
            <div className="onb__note">
              Подписи годов предложены по последним завершённым: отчётность за идущий
              год ещё не сдана. Порядок — от раннего к позднему, его же ждут тренды.
            </div>

            <div className="onb__foot">
              <Button onClick={() => setStep(3)}>Дальше</Button>
              <Button variant="link" onClick={() => setStep(1)}>Назад</Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="onb__pane">
            <div className="onb__eyebrow">Шаг 3 из 3</div>
            <h1 className="onb__title">Кто работает в организации</h1>
            {/* Макет обещает доступ к отдельной сделке и журнал по ней. Права в
                продукте организационные, и журнал общий — сказано прямо, иначе
                приглашение читалось бы как выдача доступа к одному делу. */}
            <p className="onb__lead">
              Права выдаются на всю организацию: участник видит все дела, а журнал
              доступа — общий. Отдельного доступа к делу в продукте нет.
            </p>

            {canInvite ? (
              <>
                <div className="onb__row">
                  <Field label="Почта коллеги" placeholder="name@company.ru"
                         value={inviteEmail} error={inviteErr}
                         onChange={(e) => setInviteEmail(e.target.value)} />
                  <Field label="Имя" placeholder="Иван Петров" value={inviteName}
                         onChange={(e) => setInviteName(e.target.value)} />
                  <SelectField label="Роль" value={inviteRole} options={ASSIGNABLE}
                               onChange={setInviteRole} />
                </div>
                <Button variant="ghost" loading={invite.isPending}
                        disabled={!inviteEmail.trim() || !currentOrgId}
                        onClick={() => invite.mutate()}>
                  Добавить участника
                </Button>
              </>
            ) : (
              <div className="onb__note">
                Приглашать участников может владелец или администратор организации.
                Свою роль видно на странице «Участники и тариф».
              </div>
            )}

            {invited.length > 0 && (
              <div className="onb__invited">
                <div className="onb__invitedhead">Добавлены</div>
                {invited.map((m) => (
                  <div className="onb__invite" key={m.user_id}>
                    <div>
                      <div className="onb__invitemail">{m.email}</div>
                      <div className="onb__invitenote">{roleLabel(m.role)}</div>
                    </div>
                    {m.invite_token ? (
                      <textarea
                        className="input onb__link"
                        readOnly
                        rows={2}
                        aria-label={`Ссылка приглашения для ${m.email}`}
                        value={inviteLink(m.invite_token, window.location.origin)}
                        onFocus={(e) => e.currentTarget.select()}
                      />
                    ) : (
                      <div className="onb__invitenote">
                        Пароль у участника уже есть — ссылка не нужна.
                      </div>
                    )}
                  </div>
                ))}
                {/* То же, что и на странице участников: письма платформа не шлёт,
                    и «приглашение отправлено» было бы неправдой. */}
                <div className="onb__note">
                  Писем платформа не отправляет — передайте ссылку сами. Она действует
                  неделю и срабатывает один раз.
                </div>
              </div>
            )}

            <div className="onb__foot">
              <Button onClick={() => create.mutate()} loading={create.isPending}>
                Завести дело
              </Button>
              <Button variant="link" onClick={() => setStep(2)}>Назад</Button>
            </div>
          </div>
        )}

        {step === 4 && created && (
          <div className="onb__pane onb__pane--done">
            <div className="onb__donecube">
              <CubeHero accent={PRODUCTS.audit.cubeAccent} backdrop="transparent"
                        showEnvironment={false} />
            </div>
            <div className="onb__check">✓</div>
            {/* Имя дела — заголовок, а не вставка в предложение: «Дело «ООО «Пример»»
                заведено» даёт кавычки в кавычках у любого русского названия. */}
            <div className="onb__eyebrow">Дело заведено</div>
            <h1 className="onb__title">{created.name}</h1>
            {/* Макет обещает скан на шесть минут и письмо о готовности. Анализ
                считается сразу и на месте, почты у платформы нет вовсе. */}
            <p className="onb__lead">
              Фонового скана нет и письма не будет: анализ, диагностика и заключение
              считаются сразу, как только введена отчётность.
            </p>

            <div className="onb__next">
              <div className="onb__nexthead">Что дальше</div>
              <div className="onb__nextrow">
                Введите баланс и отчёт о финрезультатах на вкладке «Ввод» — или
                импортируйте их из XLSX по шаблону оттуда же.
              </div>
              <div className="onb__nextrow">
                Проверьте, что актив сходится с пассивом: пока не сходится, дело
                помечено «Баланс не сходится», а часть находок не считается.
              </div>
              <div className="onb__nextrow">
                Дальше — реестр флагов, качество прибыли и обязательства; оценка и
                риски включаются на своих вкладках вводом допущений.
              </div>
            </div>

            <div className="onb__foot">
              <Button onClick={() => navigate(`/audit/${created.id}`)}>Открыть дело</Button>
              <Button variant="link" onClick={() => navigate("/audit")}>Ко всем делам</Button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
