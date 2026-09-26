/* Демо риск-скана для лендинга — 30 секунд, золотая бренд-палитра.
   Одно дерево элементов, вся хореография от T. */

const { CompositionStage, useComposition, Shot, Captions, Easing, interpolate, animate, clamp } = window;

const GOLD = '#FFCE3A';
const GOLD_DEEP = '#E2A41A';
const INK = '#F5F0E4';
const MUTED = '#A79E8B';
const SUBTLE = '#77705F';
const LINE = '#2C2719';
const SURFACE = '#100E09';
const SURFACE2 = '#191610';
const CORAL = '#F0796E';
const AMBER = '#E8792B';
const MONO = "'JetBrains Mono', ui-monospace, monospace";
const DISP = "'Satoshi', 'Inter', sans-serif";
const SANS = "'Inter', sans-serif";

// Три помощника движения — всё остальное через них
const MOTION = {
  enter: (start, dur = 0.6) => animate({ from: 0, to: 1, start, end: start + dur, ease: Easing.easeOutCubic }),
  draw: (start, dur = 1.0) => animate({ from: 0, to: 1, start, end: start + dur, ease: Easing.easeInOutCubic }),
  pop: (start, dur = 0.45) => animate({ from: 0, to: 1, start, end: start + dur, ease: Easing.easeOutBack })
};

const rise = (p, px = 22) => ({ opacity: p, transform: `translateY(${(1 - p) * px}px)` });
const fmt = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00A0');

/* ——— Шапка окна: живёт всю дорогу, меняется только подпись ——— */
function AppChrome({ T, CUES }) {
  const p = MOTION.enter(0.15, 0.7)(T);
  const label =
    T < CUES.Scan ? 'НОВОЕ ДЕЛО' :
    T < CUES.Flags ? 'СКАН · ИДЁТ' :
    T < CUES.Verdict ? 'СКАН · ГОТОВО' : 'ЗАКЛЮЧЕНИЕ';
  return (
    <div style={{
      position: 'absolute', left: 0, right: 0, top: 0, height: 64,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 36px', borderBottom: `1px solid ${LINE}`, background: SURFACE,
      ...rise(p, 14)
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ width: 20, height: 20, borderRadius: 6, background: GOLD, boxShadow: `0 0 14px rgba(255,206,58,.5)` }} />
        <span style={{ font: `600 15px/1 ${SANS}`, letterSpacing: '-.01em', color: INK }}>Финанс&nbsp;Аудит</span>
      </div>
      <span style={{ font: `500 11px/1 ${MONO}`, letterSpacing: '.14em', color: SUBTLE }}>{label}</span>
    </div>
  );
}

/* ——— Сцена 1: ввод ИНН ——— */
function InnScene({ T, CUES }) {
  const card = MOTION.enter(0.5, 0.7)(T);
  const typed = clamp(Math.floor(interpolate([1.3, 2.6], [0, 10], Easing.linear)(T)), 0, 10);
  const inn = '5406231908'.slice(0, typed);
  const caret = T > 1.3 && T < 2.7 && Math.floor(T * 2.6) % 2 === 0;
  const found = MOTION.enter(3.0, 0.5)(T);
  const btn = MOTION.pop(3.6, 0.5)(T);
  const press = T > 4.5 ? interpolate([4.5, 4.7], [1, 0.96], Easing.easeOutQuad)(T) : 1;

  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 64, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 620, padding: 44, border: `1px solid ${LINE}`, borderRadius: 22, background: SURFACE, ...rise(card, 26) }}>
        <div style={{ font: `500 11px/1 ${SANS}`, letterSpacing: '.16em', textTransform: 'uppercase', color: SUBTLE }}>ПРОВЕРКА КОМПАНИИ</div>
        <div style={{ marginTop: 18, font: `500 32px/1.12 ${DISP}`, letterSpacing: '-.03em', color: INK }}>Введите ИНН цели</div>
        <div style={{
          marginTop: 30, height: 60, padding: '0 20px', display: 'flex', alignItems: 'center',
          border: `1px solid ${T > 1.2 ? GOLD : LINE}`, borderRadius: 12, background: SURFACE2,
          boxShadow: T > 1.2 ? `0 0 0 4px rgba(255,206,58,.18)` : 'none'
        }}>
          <span style={{ font: `400 22px/1 ${MONO}`, letterSpacing: '.08em', color: inn ? INK : SUBTLE }}>
            {inn || '10 или 12 цифр'}
          </span>
          <span style={{ width: 2, height: 26, marginLeft: 3, background: caret ? GOLD : 'transparent' }} />
        </div>
        <div style={{ marginTop: 18, display: 'flex', alignItems: 'center', gap: 10, ...rise(found, 8) }}>
          <span style={{ font: `600 12px/1 ${MONO}`, color: GOLD }}>✓</span>
          <span style={{ font: `400 15px/1.4 ${SANS}`, color: MUTED }}>ООО «Сибтранс-Логистика» · грузоперевозки</span>
        </div>
        <div style={{
          marginTop: 30, height: 56, borderRadius: 6, background: GOLD, color: '#1F1705',
          font: `600 16px/56px ${SANS}`, textAlign: 'center',
          transform: `scale(${(0.94 + btn * 0.06) * press})`, opacity: btn,
          boxShadow: `0 0 26px rgba(255,206,58,${0.34 * btn})`
        }}>Начать проверку</div>
      </div>
    </div>
  );
}

/* ——— Сцена 2: скан. Шесть направлений заполняются по очереди ——— */
const TRACKS = [
  { name: 'Отчётность и сверка', meta: '412 строк' },
  { name: 'Качество прибыли', meta: '9 корректировок' },
  { name: 'Обязательства и залоги', meta: 'ФНП · 5 записей' },
  { name: 'Группа компаний', meta: '6 обществ' },
  { name: 'Оценка стоимости', meta: 'DCF · WACC 18,5%' },
  { name: 'Анализ рисков', meta: '10 000 прогонов' }
];

function ScanScene({ T, CUES }) {
  const enter = MOTION.enter(CUES.Scan + 0.1, 0.6)(T);
  // Прогресс каждой дорожки — единственный источник и для галочки, и для процента:
  // так «100%» не может обогнать последнюю ✓ при любом растяжении сцены.
  const progress = TRACKS.map((_, i) => MOTION.draw(CUES.Scan + 1.0 + i * 0.85, 0.85)(T));
  const done = progress.filter(p => p >= 1).length;
  const pct = clamp(Math.round(progress.reduce((a, p) => a + p, 0) / TRACKS.length * 100), 0, 100);

  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 64, bottom: 0, padding: '44px 90px', ...rise(enter, 18) }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div style={{ font: `500 30px/1.12 ${DISP}`, letterSpacing: '-.03em', color: INK }}>Идёт проверка</div>
        <div style={{ font: `500 30px/1 ${MONO}`, letterSpacing: '-.03em', color: GOLD }}>{pct}%</div>
      </div>
      <div style={{ marginTop: 14, height: 6, borderRadius: 999, background: SURFACE2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, borderRadius: 999, background: GOLD, boxShadow: `0 0 16px rgba(255,206,58,.5)` }} />
      </div>
      <div style={{ marginTop: 12, font: `400 13px/1.4 ${MONO}`, color: SUBTLE }}>
        {done} из 6 направлений · 24 процедуры
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 14, marginTop: 30 }}>
        {TRACKS.map((tr, i) => {
          const p = progress[i];
          const isDone = p >= 1;
          const isActive = p > 0 && p < 1;
          return (
            <div key={tr.name} style={{
              padding: '18px 20px', borderRadius: 14,
              border: `1px solid ${isDone ? 'rgba(255,206,58,.34)' : LINE}`,
              background: isDone ? 'rgba(255,206,58,.07)' : SURFACE,
              opacity: 0.35 + 0.65 * clamp(p * 3, 0, 1)
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{
                  width: 22, height: 22, flex: 'none', borderRadius: 7,
                  background: isDone ? GOLD : (isActive ? GOLD_DEEP : SURFACE2),
                  color: '#1F1705', font: `600 11px/22px ${MONO}`, textAlign: 'center'
                }}>{isDone ? '✓' : (isActive ? '·' : '')}</span>
                <span style={{ flex: 1, minWidth: 0, font: `400 15px/1.3 ${SANS}`, color: INK }}>{tr.name}</span>
                <span style={{ font: `400 11px/1.3 ${MONO}`, color: SUBTLE }}>{isDone ? tr.meta : ''}</span>
              </div>
              <div style={{ marginTop: 12, height: 3, borderRadius: 999, background: SURFACE2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${p * 100}%`, borderRadius: 999, background: isDone ? GOLD : GOLD_DEEP }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ——— Сцена 3: находки падают одна за другой ——— */
const FLAGS = [
  { name: 'Прочие доходы не подтверждены выпиской', sum: '(62)', level: 'критич.', tone: CORAL },
  { name: 'Треть выручки на одном заказчике', sum: '(84)', level: 'критич.', tone: CORAL },
  { name: 'Поручительства за связанную сторону', sum: '(41)', level: 'средний', tone: AMBER },
  { name: 'Аренда склада без индексации', sum: '(24)', level: 'средний', tone: AMBER },
  { name: 'Смена аудитора дважды за три года', sum: '(9)', level: 'низкий', tone: MUTED }
];

function FlagsScene({ T, CUES }) {
  const enter = MOTION.enter(CUES.Flags, 0.5)(T);
  const shown = FLAGS.filter((_, i) => T > CUES.Flags + 0.6 + i * 0.62).length;
  const sum = clamp(Math.round(interpolate([CUES.Flags + 0.8, CUES.Flags + 3.9], [0, 220], Easing.easeOutCubic)(T)), 0, 220);

  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 64, bottom: 0, padding: '40px 90px', display: 'flex', gap: 36, ...rise(enter, 18) }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: `500 11px/1 ${MONO}`, letterSpacing: '.16em', color: GOLD }}>НАЙДЕНО</div>
        <div style={{ marginTop: 14, font: `500 30px/1.12 ${DISP}`, letterSpacing: '-.03em', color: INK }}>Семь красных флагов</div>
        <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {FLAGS.map((f, i) => {
            const start = CUES.Flags + 0.6 + i * 0.62;
            const p = MOTION.pop(start, 0.5)(T);
            if (p <= 0) return <div key={f.name} style={{ height: 58 }} />;
            return (
              <div key={f.name} style={{
                display: 'flex', alignItems: 'center', gap: 16, height: 58, padding: '0 20px',
                border: `1px solid ${LINE}`, borderLeft: `3px solid ${f.tone}`, borderRadius: 12,
                background: SURFACE, opacity: clamp(p, 0, 1),
                transform: `translateX(${(1 - clamp(p, 0, 1)) * -18}px)`
              }}>
                <span style={{ flex: 1, minWidth: 0, font: `400 15px/1.3 ${SANS}`, color: INK }}>{f.name}</span>
                <span style={{ flex: 'none', width: 88, font: `500 11px/1.3 ${MONO}`, color: f.tone }}>{f.level}</span>
                <span style={{ flex: 'none', font: `500 16px/1 ${MONO}`, color: f.tone }}>{f.sum}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{
        flex: 'none', width: 300, alignSelf: 'flex-start', marginTop: 68, padding: 32,
        border: `1px solid rgba(255,206,58,.32)`, borderRadius: 20, background: 'rgba(255,206,58,.08)'
      }}>
        <div style={{ font: `500 10px/1 ${SANS}`, letterSpacing: '.14em', textTransform: 'uppercase', color: SUBTLE }}>ЦЕНА РИСКОВ</div>
        <div style={{ marginTop: 18, font: `500 58px/1 ${MONO}`, letterSpacing: '-.04em', color: GOLD }}>{sum}</div>
        <div style={{ marginTop: 12, font: `400 14px/1.5 ${SANS}`, color: MUTED }}>млн ₽ · сумма влияния всех находок</div>
        <div style={{ marginTop: 20, paddingTop: 18, borderTop: `1px solid rgba(255,206,58,.22)`, font: `400 12px/1.5 ${MONO}`, color: SUBTLE }}>
          {shown} из 7 показано
        </div>
      </div>
    </div>
  );
}

/* ——— Сцена 4: вердикт и мостик до цены ——— */
function VerdictScene({ T, CUES }) {
  const enter = MOTION.enter(CUES.Verdict, 0.6)(T);
  const ask = MOTION.enter(CUES.Verdict + 0.5, 0.5)(T);
  const fair = MOTION.enter(CUES.Verdict + 1.2, 0.5)(T);
  const line = MOTION.draw(CUES.Verdict + 1.9, 0.7)(T);
  const badge = MOTION.pop(CUES.Verdict + 2.5, 0.6)(T);
  const fairNum = clamp(Math.round(interpolate([CUES.Verdict + 1.2, CUES.Verdict + 2.4], [1240, 1020], Easing.easeOutCubic)(T)), 1020, 1240);

  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 64, bottom: 0, padding: '52px 90px', ...rise(enter, 20) }}>
      <div style={{ font: `500 11px/1 ${MONO}`, letterSpacing: '.16em', color: GOLD }}>ВЕРДИКТ · ШЕСТЬ ДНЕЙ РАБОТЫ</div>
      <div style={{ marginTop: 18, font: `500 44px/1.08 ${DISP}`, letterSpacing: '-.034em', color: INK, maxWidth: '20ch' }}>
        Покупать с дисконтом 18%
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 40, marginTop: 44 }}>
        <div style={{ ...rise(ask, 12) }}>
          <div style={{ font: `400 12px/1 ${SANS}`, color: SUBTLE }}>Просит продавец</div>
          <div style={{ marginTop: 12, font: `400 36px/1 ${MONO}`, letterSpacing: '-.03em', color: MUTED, textDecoration: 'line-through', textDecorationColor: CORAL }}>1 240</div>
        </div>
        <div style={{ flex: 'none', width: 120, height: 2, background: LINE, position: 'relative', opacity: line }}>
          <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${line * 100}%`, background: GOLD }} />
        </div>
        <div style={{ ...rise(fair, 12) }}>
          <div style={{ font: `400 12px/1 ${SANS}`, color: SUBTLE }}>Справедливая цена</div>
          <div style={{ marginTop: 12, font: `500 56px/1 ${MONO}`, letterSpacing: '-.04em', color: GOLD }}>{fmt(fairNum)}</div>
        </div>
        <div style={{
          flex: 'none', marginLeft: 20, padding: '16px 24px', borderRadius: 14,
          border: `1px solid rgba(255,206,58,.32)`, background: 'rgba(255,206,58,.08)',
          transform: `scale(${0.9 + clamp(badge, 0, 1) * 0.1})`, opacity: clamp(badge, 0, 1)
        }}>
          <div style={{ font: `400 11px/1 ${SANS}`, color: SUBTLE }}>Разница</div>
          <div style={{ marginTop: 8, font: `600 28px/1 ${MONO}`, letterSpacing: '-.03em', color: GOLD }}>220 млн ₽</div>
        </div>
      </div>

      <div style={{ marginTop: 40, paddingTop: 24, borderTop: `1px solid ${LINE}`, display: 'flex', gap: 52, opacity: clamp(badge, 0, 1) }}>
        <div>
          <div style={{ font: `400 11px/1 ${SANS}`, color: SUBTLE }}>Процедур пройдено</div>
          <div style={{ marginTop: 10, font: `400 20px/1 ${MONO}`, color: INK }}>18 / 24</div>
        </div>
        <div>
          <div style={{ font: `400 11px/1 ${SANS}`, color: SUBTLE }}>Стоимость проверки</div>
          <div style={{ marginTop: 10, font: `400 20px/1 ${MONO}`, color: INK }}>45 000 ₽</div>
        </div>
        <div>
          <div style={{ font: `400 11px/1 ${SANS}`, color: SUBTLE }}>Срок</div>
          <div style={{ marginTop: 10, font: `400 20px/1 ${MONO}`, color: INK }}>6 дней</div>
        </div>
      </div>
    </div>
  );
}

/* ——— Финал ——— */
function CloseScene({ T, CUES }) {
  const p = MOTION.enter(CUES.Close + 0.1, 0.7)(T);
  const cta = MOTION.pop(CUES.Close + 0.9, 0.6)(T);
  return (
    <div style={{
      position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      background: 'radial-gradient(ellipse 60% 80% at 50% 46%, rgba(255,206,58,.14) 0%, transparent 74%), #000'
    }}>
      <div style={{ ...rise(p, 22) }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14 }}>
          <span style={{ width: 26, height: 26, borderRadius: 8, background: GOLD, boxShadow: `0 0 20px rgba(255,206,58,.6)` }} />
          <span style={{ font: `600 20px/1 ${SANS}`, letterSpacing: '.02em', color: INK }}>Финанс&nbsp;Аудит</span>
        </div>
        <div style={{ marginTop: 30, font: `500 40px/1.14 ${DISP}`, letterSpacing: '-.032em', color: INK, maxWidth: '22ch' }}>
          Проверенная цифра стоит дешевле, чем ошибка
        </div>
      </div>
      <div style={{
        marginTop: 36, height: 56, padding: '0 32px', borderRadius: 6, background: GOLD, color: '#1F1705',
        font: `600 17px/56px ${SANS}`, transform: `scale(${0.92 + clamp(cta, 0, 1) * 0.08})`, opacity: clamp(cta, 0, 1),
        boxShadow: `0 0 30px rgba(255,206,58,${0.36 * clamp(cta, 0, 1)})`
      }}>Открыть демо-дело</div>
    </div>
  );
}

function RiskScanDemo() {
  const { T, CUES } = useComposition();

  return (
    <div data-screen-label={`${T.toFixed(0)}s`} style={{ position: 'absolute', inset: 0, background: '#000', overflow: 'hidden' }}>
      <Shot from={0} to={CUES.Close}>
        <AppChrome T={T} CUES={CUES} />
      </Shot>

      <Shot from={0} to={CUES.Scan}>
        <InnScene T={T} CUES={CUES} />
      </Shot>
      <Shot from={CUES.Scan} to={CUES.Flags}>
        <ScanScene T={T} CUES={CUES} />
      </Shot>
      <Shot from={CUES.Flags} to={CUES.Verdict}>
        <FlagsScene T={T} CUES={CUES} />
      </Shot>
      <Shot from={CUES.Verdict} to={CUES.Close}>
        <VerdictScene T={T} CUES={CUES} />
      </Shot>
      <Shot from={CUES.Close} to={999}>
        <CloseScene T={T} CUES={CUES} />
      </Shot>

      <Captions items={[
        { at: 0.6, until: 5.0, text: 'Вводите ИНН — отчётность подтянется сама' },
        { at: 5.4, until: 11.4, text: 'Шесть направлений, двадцать четыре процедуры' },
        { at: 11.8, until: 18.6, text: 'Каждая находка — сумма, а не формулировка' },
        { at: 19.0, until: 25.4, text: 'Справедливая цена вместо цены продавца' }
      ]} />
    </div>
  );
}

function RiskScanDemoStage() {
  return (
    <CompositionStage width={1600} height={900} scenes={window.OM_SCENES} playback={window.OM_PLAYBACK} bg="#000">
      <RiskScanDemo />
    </CompositionStage>
  );
}

window.RiskScanDemo = RiskScanDemoStage;
