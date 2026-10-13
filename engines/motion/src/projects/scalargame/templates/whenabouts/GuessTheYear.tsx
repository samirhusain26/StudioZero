// Whenabouts · guess-the-year (almanac). Hook → event card (prompt only, never the title or a date) with a “?” year
// odometer → A/B/C years as chips and as identical marks on an honestly scaled ruler → think → odometer rolls to the
// answer → ruler pans/zooms to the correct mark, which lights → explanation → closing card.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import {BrandLabel, Choices, EndCard, Explanation, ThinkBar} from '../../kit/ui';
import {SAFE_RECT} from '../../timing';
import {easeInOut, enter, exit, mix, pop} from '../../kit/motion';
import {CX, EventCard, Hook, Odometer, Page, YELLOW, niceStep, odometerLandTimes, parseYear} from './almanac';

const HOOK_TOP = 328;
const CARD_TOP = 456, CARD_H = 600, HEADLINE_BOX = 236;
const RULER_Y = 1172, FLAG_Y = RULER_Y - 54, LABEL_Y = RULER_Y + 28;
const CHIPS_TOP = 1262, THINK_TOP = 1396, EXPLAIN_TOP = 1374;
const ZOOM = 1.2;
const EDGE = 64; // about half a year label: after the reveal every choice stays inside the safe rectangle

const Ruler: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q;
  const years = q.choices.map((c, i) => c.year ?? parseYear(c.label) ?? i);
  const lo = Math.min(...years), hi = Math.max(...years);
  const spacing = Math.max(1, (hi - lo) / Math.max(1, years.length - 1));
  const mid = (lo + hi) / 2;
  const k0 = (SAFE_RECT.x1 - SAFE_RECT.x0) / (hi - lo + 1.2 * spacing); // choice span plus 0.6 spacing each side
  const step = niceStep(k0, 18);
  const ansIdx = Math.max(0, q.choices.findIndex((c) => c.key === q.answerKey));
  const ansYear = years[ansIdx];

  // Camera: an unlabelled pan in from earlier years during the hook, still from t.choicesIn, then at reveal+1.0 a single
  // pan/zoom toward the correct year, only as far as keeps all three choices on screen.
  const pan = enter(frame, 0.15, Math.max(0.5, t.choicesIn - 0.15), easeInOut);
  const z = enter(frame, t.reveal + 1.0, 0.8, easeInOut);
  const k = k0 * mix(1, ZOOM, z);
  const target = Math.min(lo + (CX - SAFE_RECT.x0 - EDGE) / k, Math.max(hi - (SAFE_RECT.x1 - EDGE - CX) / k, ansYear));
  const centre = mix(mid - 2.2 * spacing, mid, pan) + (target - mid) * z;
  const x = (y: number) => CX + (y - centre) * k;

  const shown = enter(frame, 0.0, 0.6) * exit(frame, t.cta - 0.3, 0.3);
  const lit = enter(frame, t.reveal + 1.0, 0.45);

  // Ticks aligned to the first choice year, every `step` years; ticks at the choice years are long.
  const yMin = centre - (CX + 60) / k, yMax = centre + (1080 - CX + 60) / k;
  const ticks: React.ReactNode[] = [];
  for (let n = Math.ceil((yMin - lo) / step); lo + n * step <= yMax; n++) {
    const yr = lo + n * step;
    const long = years.some((y) => Math.abs(y - yr) < 1e-6);
    ticks.push(<line key={n} x1={x(yr)} x2={x(yr)} y1={RULER_Y} y2={RULER_Y + (long ? 24 : 13)} stroke={s.line} strokeWidth={long ? 3 : 2} />);
  }

  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: 1080, height: 1920, opacity: shown}}>
      <svg width={1080} height={1920} style={{position: 'absolute', left: 0, top: 0}}>
        <rect x={-10} y={RULER_Y - 2} width={1100} height={34} fill={s.bg2} opacity={0.7} />
        <line x1={-10} x2={1090} y1={RULER_Y} y2={RULER_Y} stroke={s.line} strokeWidth={3} />
        {ticks}
        {q.choices.map((c, i) => {
          const p = pop(frame, t.choicesIn + i * 0.12);
          if (p <= 0) return null;
          const isAns = i === ansIdx;
          const dim = isAns ? 0 : lit;
          const xx = x(years[i]);
          return (
            <g key={c.key} opacity={Math.min(1, p) * (1 - 0.6 * dim)}>
              {isAns && lit > 0 && <rect x={xx - 9} y={FLAG_Y + 20} width={18} height={RULER_Y - FLAG_Y - 8} fill={YELLOW} opacity={lit} />}
              <line x1={xx} x2={xx} y1={FLAG_Y + 26} y2={RULER_Y + 14} stroke={s.line} strokeWidth={4} />
              <circle cx={xx} cy={FLAG_Y - (1 - Math.min(1, p)) * 30} r={27 + 4 * (isAns ? lit : 0)}
                fill={isAns ? (lit > 0 ? YELLOW : s.card) : s.card} stroke={s.line} strokeWidth={3} />
            </g>
          );
        })}
      </svg>
      {q.choices.map((c, i) => {
        const p = pop(frame, t.choicesIn + i * 0.12);
        if (p <= 0) return null;
        const isAns = i === ansIdx;
        const dim = isAns ? 0 : lit;
        const xx = x(years[i]);
        return (
          <React.Fragment key={c.key}>
            <div style={{position: 'absolute', left: xx - 30, width: 60, top: FLAG_Y - 20 - (1 - Math.min(1, p)) * 30, textAlign: 'center',
              fontFamily: s.fontNumber, fontWeight: 700, fontSize: 32, lineHeight: '40px', color: s.fg, opacity: Math.min(1, p) * (1 - 0.6 * dim)}}>
              {c.key}
            </div>
            <div style={{position: 'absolute', left: xx - 150, width: 300, top: LABEL_Y, textAlign: 'center', opacity: Math.min(1, p) * (1 - 0.6 * dim)}}>
              <span style={{fontFamily: s.fontNumber, fontWeight: 700, fontSize: 40, color: s.fg, padding: '0 8px',
                background: isAns && lit > 0 ? `rgba(234,179,8,${lit})` : 'transparent'}}>{c.label}</span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
};

const Component: React.FC<TemplateProps> = (props) => {
  const {ep, s, t} = props;
  const q = ep.q;
  const frame = useCurrentFrame();
  const placeholder = Math.max(...q.choices.map((c) => c.label.replace(/\D/g, '').length), 1);
  const labelO = enter(frame, t.reveal + 1.0, 0.4);
  return (
    <AbsoluteFill style={{color: s.fg}}>
      <Page s={s} />
      <BrandLabel s={s} t={t} />
      <Hook s={s} t={t} text={q.hook} top={HOOK_TOP} />
      <EventCard s={s} t={t} at={t.items[0] ?? 0.6} top={CARD_TOP} height={CARD_H} kicker="The event" headline={q.prompt ?? q.question}
        headlineBox={HEADLINE_BOX}>
        <div style={{marginTop: 16, fontFamily: s.fontNumber, fontWeight: 700, fontSize: 30, letterSpacing: '0.22em', color: s.muted,
          textTransform: 'uppercase', position: 'relative'}}>
          <span style={{opacity: 1 - labelO}}>In the year</span>
          <span style={{position: 'absolute', left: 0, right: 0, textAlign: 'center', opacity: labelO, color: s.fg}}>The year</span>
        </div>
        <div style={{marginTop: 14}}><Odometer s={s} t={t} answer={q.answer} placeholder={placeholder} /></div>
      </EventCard>
      <Ruler {...props} />
      <Choices s={s} t={t} choices={q.choices} answerKey={q.answerKey} top={CHIPS_TOP} fontSize={46} revealAt={t.reveal + 1.0}
        chipStyle={{justifyContent: 'center', fontFamily: s.fontNumber, boxShadow: `5px 5px 0 ${s.bg2}`}}
        answerStyle={{background: YELLOW, transform: 'none'}} />
      <ThinkBar s={s} t={t} top={THINK_TOP} />
      <Explanation s={s} t={t} text={q.explanation} top={EXPLAIN_TOP} fontSize={38} style={{fontWeight: 600}} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const GuessTheYear: Template = {
  Component,
  extraCues: ({ep, t}) => [
    ...odometerLandTimes(t, ep.q.answer).map((at) => ({at, name: 'tick' as const, volume: 0.45})),
    {at: t.reveal + 1.0, name: 'whip' as const, volume: 0.35},
  ],
};
