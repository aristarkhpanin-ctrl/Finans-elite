import type { PlanSection } from "../../api/model";
import { IconTrash } from "../../components/icons";
import { Button } from "../../components/ui";

interface Props {
  sections: PlanSection[];
  onChange: (sections: PlanSection[]) => void;
}

/** Вкладка «Документ»: текстовые разделы бизнес-плана для DOCX (пакет №5, D2). */
export function DocumentTab({ sections, onChange }: Props) {
  const add = () => onChange([...sections, { title: "", text: "" }]);
  const upd = (i: number, patch: Partial<PlanSection>) =>
    onChange(sections.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  const rm = (i: number) => onChange(sections.filter((_, k) => k !== i));
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= sections.length) return;
    const next = [...sections];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div>
      <div className="tab-head">
        <div style={{ minWidth: 0 }}>
          <div className="tab-head__title">Документ бизнес-плана</div>
          <div className="tab-head__sub">
            Текстовые разделы (резюме, рынок, команда…) войдут в DOCX-документ вместе с
            заключением, показателями и отчётами. На расчёт не влияют.
          </div>
        </div>
        <Button onClick={add}>＋&nbsp;&nbsp;Раздел</Button>
      </div>

      {sections.length === 0 ? (
        <div className="tab-empty">
          <div className="tab-empty__title">Нет разделов</div>
          <div className="tab-empty__sub">
            Добавьте текстовые разделы — документ можно скачать на странице результатов
            кнопкой «Бизнес-план (DOCX)». Заключение и отчёты попадут в него автоматически.
          </div>
          <Button onClick={add}>＋&nbsp;&nbsp;Добавить первый раздел</Button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {sections.map((s, i) => (
            <div className="line-card" key={i}>
              <div className="line-card__head">
                <div className="line-card__idx">{i + 1}</div>
                <div className="line-card__name">
                  <input value={s.title} placeholder="Заголовок раздела, напр. «Резюме проекта»"
                         onChange={(e) => upd(i, { title: e.target.value })} />
                </div>
                <button type="button" className="doc-sec__move" title="Выше" disabled={i === 0}
                        onClick={() => move(i, -1)}>↑</button>
                <button type="button" className="doc-sec__move" title="Ниже"
                        disabled={i === sections.length - 1} onClick={() => move(i, 1)}>↓</button>
                <button type="button" className="line-card__del" title="Удалить раздел"
                        onClick={() => rm(i)}>
                  <IconTrash size={16} />
                </button>
              </div>
              <textarea
                className="doc-sec__text"
                value={s.text}
                rows={6}
                placeholder="Текст раздела. Пустая строка разделяет абзацы."
                onChange={(e) => upd(i, { text: e.target.value })}
              />
            </div>
          ))}
          <button type="button" className="add-row" onClick={add}>
            ＋&nbsp;&nbsp;Добавить раздел
          </button>
        </div>
      )}
    </div>
  );
}
