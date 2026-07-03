import { useState } from "react";
import { CubeHero } from "../components/CubeHero";
import {
  IconBox,
  IconChart,
  IconCheck,
  IconDownload,
  IconPlus,
  IconPrint,
  IconSearch,
  IconTrash,
  IconUser,
  IconWarning,
} from "../components/icons";
import { useToast } from "../components/Toast";
import { getTheme, toggleTheme } from "../components/theme";
import {
  Button,
  Chip,
  CountChip,
  EmptyState,
  ErrorState,
  Field,
  MetricCard,
  Modal,
  NumberField,
  SectionCard,
  SegmentControl,
  Skeleton,
  Switch,
} from "../components/ui";
import { fmtMillions, fmtMoney, fmtRatio, fmtTable, fracToPct, pctToFrac } from "../format";

/**
 * Dev-песочница UI-кита (`/dev/ui`, только DEV-сборка): визуальная сверка
 * компонентов с макетами в обеих темах. В прод-бандл не попадает.
 */
export function DevUiPage() {
  const toast = useToast();
  const [theme, setTheme] = useState(getTheme());
  const [on, setOn] = useState(true);
  const [seg, setSeg] = useState<"table" | "spark">("table");
  const [modal, setModal] = useState(false);
  const [err, setErr] = useState("");

  return (
    <div className="content" style={{ maxWidth: 960 }}>
      <div className="section-head">
        <h1>UI-кит (dev)</h1>
        <Button variant="ghost" onClick={() => setTheme(toggleTheme())}>
          Тема: {theme}
        </Button>
      </div>

      <SectionCard num="01" title="Кнопки" sub="btn 4px">
        <div className="toolbar" style={{ flexWrap: "wrap" }}>
          <Button>Рассчитать</Button>
          <Button variant="ghost">Отмена</Button>
          <Button variant="danger">Удалить</Button>
          <Button variant="link">Подробнее</Button>
          <Button loading>Сохранение…</Button>
          <Button disabled>Недоступно</Button>
          <Button variant="ghost">
            <IconPlus size={15} /> Добавить
          </Button>
        </div>
      </SectionCard>

      <SectionCard num="02" title="Поля" sub="input 8px, бордер 1.5">
        <div className="form-grid">
          <Field label="Название проекта" placeholder="Например, «Пекарня»" note="До 80 символов" />
          <NumberField label="Ставка дисконтирования" value="18" onChange={() => undefined} suffix="%" hint="Годовая ставка" />
          <NumberField label="Стартовый капитал" value="1200000" onChange={() => undefined} prefix="₽" />
          <Field
            label="Поле с ошибкой"
            value={err}
            onChange={(e) => setErr(e.target.value)}
            error={err ? undefined : "Обязательное поле"}
          />
        </div>
        <div className="toolbar" style={{ marginTop: 8, flexWrap: "wrap", gap: 18 }}>
          <Switch label="НДС включён" checked={on} onChange={setOn} />
          <Switch label="Недоступно" checked disabled onChange={() => undefined} />
          <SegmentControl
            value={seg}
            onChange={setSeg}
            options={[
              { value: "table", label: "Таблицы" },
              { value: "spark", label: "Спарклайны" },
            ]}
          />
        </div>
      </SectionCard>

      <SectionCard num="03" title="Статусы" sub={<CountChip>6</CountChip>}>
        <div className="toolbar" style={{ flexWrap: "wrap" }}>
          <Chip kind="active">Рассчитан</Chip>
          <Chip kind="warn">Черновик</Chip>
          <Chip kind="problem">Кассовый разрыв</Chip>
          <Chip kind="info">Дочерний</Chip>
          <Chip>Наблюдатель</Chip>
          <Chip kind="active" dot={false}>
            Без точки
          </Chip>
        </div>
      </SectionCard>

      <SectionCard num="04" title="Метрики и форматтеры">
        <div className="metrics">
          <MetricCard label="NPV" value={fmtMillions("18400000", { sign: true })} tone="good" sub="Создаёт стоимость" />
          <MetricCard label="NPV (убыток)" value={fmtMillions(-4200000)} tone="bad" sub="Разрушает стоимость" />
          <MetricCard label="Выручка М12" value={fmtMoney(12480000)} />
          <MetricCard label="PI" value={fmtRatio("0.82")} tone="bad" />
        </div>
        <p className="muted" style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>
          fmtTable(−1234567) → {fmtTable(-1234567).text} · fmtTable(0) → {fmtTable(0).text} ·
          fracToPct("0.205") → {fracToPct("0.205")} · pctToFrac("20,5") → {pctToFrac("20,5")}
        </p>
      </SectionCard>

      <SectionCard num="05" title="Состояния данных">
        <div className="form-grid">
          <div>
            <Skeleton width="80%" />
            <Skeleton width="60%" style={{ marginTop: 8 }} />
            <Skeleton width="70%" height={28} style={{ marginTop: 8 }} />
          </div>
          <EmptyState
            title="Пока нет проектов"
            sub="Создайте первый проект или начните с шаблона."
            action={<Button>Создать проект</Button>}
          />
          <ErrorState onRetry={() => toast("Повторный запрос", { kind: "info" })} />
        </div>
      </SectionCard>

      <SectionCard num="06" title="Тосты и модалка">
        <div className="toolbar" style={{ flexWrap: "wrap" }}>
          <Button variant="ghost" onClick={() => toast("Проект сохранён", { kind: "success", sub: "Все изменения записаны" })}>
            Success
          </Button>
          <Button variant="ghost" onClick={() => toast("Идёт пересчёт модели", { kind: "info" })}>
            Info
          </Button>
          <Button variant="ghost" onClick={() => toast("Близко к лимиту участников", { kind: "warn", sub: "8 из 10 мест" })}>
            Warn
          </Button>
          <Button variant="ghost" onClick={() => toast("Не удалось сохранить", { kind: "error", sub: "Повторите попытку" })}>
            Error
          </Button>
          <Button onClick={() => setModal(true)}>Открыть модалку</Button>
        </div>
        <Modal
          open={modal}
          onClose={() => setModal(false)}
          title="Удалить проект?"
          sub="Действие необратимо: расчёты и факт будут удалены."
          actions={
            <>
              <Button variant="ghost" onClick={() => setModal(false)}>
                Отмена
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  setModal(false);
                  toast("Проект удалён", { kind: "success" });
                }}
              >
                Удалить
              </Button>
            </>
          }
        />
      </SectionCard>

      <SectionCard num="07" title="Иконки" sub="stroke 1.7">
        <div className="toolbar" style={{ flexWrap: "wrap", color: "var(--muted)" }}>
          <IconUser />
          <IconSearch />
          <IconTrash />
          <IconPlus />
          <IconDownload />
          <IconPrint />
          <IconChart />
          <IconBox />
          <IconWarning />
          <IconCheck />
        </div>
      </SectionCard>

      <SectionCard num="08" title="CubeHero" sub="scene / transparent">
        <div className="toolbar" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ width: 230, height: 230, borderRadius: 16, overflow: "hidden" }}>
            <CubeHero />
          </div>
          <div style={{ width: 120, height: 120, borderRadius: 14, overflow: "hidden", background: "var(--page-bg)", border: "1px solid var(--border)" }}>
            <CubeHero backdrop="transparent" showEnvironment={false} showOrbit={false} pointerTilt={false} motionSpeed="calm" />
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
