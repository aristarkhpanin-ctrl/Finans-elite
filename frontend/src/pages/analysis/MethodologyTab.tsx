import { useQuery } from "@tanstack/react-query";
import { getMethodology, type MethodologyChoice } from "../../api/review";

/**
 * Методические трактовки расчёта (SPEC §22, фаза D2).
 *
 * Восемь мест, где методика допускает несколько прочтений, до сих пор жили **только в
 * спецификации движка** — до неё не добирается ни владелец проекта, ни бухгалтер,
 * которого просят трактовку подтвердить. Экран отвечает на их вопрос по конкретной
 * модели: что выбрано, чем переключается и **задействовано ли здесь вообще**.
 *
 * Незадействованные развилки не прячутся: спрятанный пункт читается как несуществующий,
 * а он существует — просто в этой модели не возникает. Поэтому они показаны отдельным
 * блоком и каждый называет причину своего молчания.
 */
export function MethodologyTab({ projectId }: { projectId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["methodology", projectId],
    queryFn: () => getMethodology(projectId),
  });

  if (isLoading) return <div className="mnote">Считаем модель…</div>;
  if (isError || !data) {
    return (
      <div className="mnote">
        Не удалось разобрать методику: проект не считается. Откройте результаты — там
        будет названа причина.
      </div>
    );
  }

  const engaged = data.choices.filter((c) => c.engaged);
  const silent = data.choices.filter((c) => !c.engaged);

  return (
    <div className="mth">
      <div className="mth-head">
        <div>
          <div className="mth-head__title">Методические допущения расчёта</div>
          <div className="mth-head__sub">
            Задействовано развилок: <b>{engaged.length}</b> из {data.choices.length}.
            Движок расчёта v{data.engine_version}.
          </div>
        </div>
        {/* Версия предварительная — и это не техническая мелочь, а утверждение о
            состоянии работы: трактовки реализованы, но никем не подтверждены. */}
        <span className="status-chip status-chip--info">
          {data.confirmed ? "трактовки подтверждены" : "предварительная версия"}
        </span>
      </div>

      <p className="mth-note">{data.note}</p>

      {engaged.map((c) => <ChoiceCard key={c.id} c={c} />)}

      {silent.length > 0 && (
        <>
          <div className="mth-sep">
            В этой модели не возникают ({silent.length})
          </div>
          {silent.map((c) => <ChoiceCard key={c.id} c={c} />)}
        </>
      )}
    </div>
  );
}

function ChoiceCard({ c }: { c: MethodologyChoice }) {
  const evidence = Object.entries(c.evidence ?? {}).filter(
    ([, v]) => !Array.isArray(v) || v.length > 0);
  return (
    <div className={"mth-card" + (c.engaged ? "" : " mth-card--silent")}>
      <div className="mth-card__head">
        <span className="mth-card__num">{c.number}</span>
        <span className="mth-card__title">{c.title}</span>
        <span className="mth-card__spec">{c.spec}</span>
      </div>
      <div className="mth-card__chosen">{c.chosen}</div>
      {/* Молчание пункта названо словами: пустая карточка читалась бы как «всё в
          порядке», а это другое утверждение. */}
      {!c.engaged && <div className="mth-card__silent">{c.silent_because}</div>}
      {c.open_question && (
        <div className="mth-card__open">
          <span className="mth-card__open-l">Открыто к сверке:</span> {c.open_question}
        </div>
      )}
      {c.controls.length > 0 && (
        <div className="mth-card__controls">
          {c.controls.map((f) => <code key={f}>{f}</code>)}
        </div>
      )}
      {evidence.length > 0 && (
        <div className="rv-finding__evi">
          {evidence.map(([k, v]) => (
            <span key={k} className="rv-evi-chip">
              {k}: <b>{Array.isArray(v) ? v.join(", ") : String(v)}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
