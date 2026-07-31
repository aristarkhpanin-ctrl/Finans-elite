import { IconBriefcase } from "../components/icons";

/**
 * Финанс-Аудит — стартовый экран продукта (список субъектов анализа).
 * Фаза A: каркас и фиолетовая тема; ввод отчётности и анализ — фазы B–C.
 */
export function AuditHomePage() {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Финанс-Аудит</h1>
          <p className="page-sub">
            Анализ финансового состояния предприятия по фактической отчётности.
          </p>
        </div>
      </div>

      <div className="tab-empty">
        <div className="tab-empty__ico">
          <IconBriefcase size={30} />
        </div>
        <div className="tab-empty__title">Раздел в разработке</div>
        <div className="tab-empty__sub">
          Здесь появится список субъектов анализа. На следующих этапах — ввод бухгалтерской
          отчётности по периодам, приведение к аналитической форме, коэффициенты и тренды,
          диагностика риска банкротства и экспертное заключение.
        </div>
      </div>
    </div>
  );
}
