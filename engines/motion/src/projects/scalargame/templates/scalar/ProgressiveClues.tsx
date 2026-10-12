// Scalar · progressive clues (field notebook). Clue index cards are dealt onto the desk one by one while a tally card
// counts how many of the 195 countries still fit. Reveal: green stamp on the pile + the correct chip, then a locator card.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import {BrandLabel, Choices, EndCard, Explanation, ThinkBar} from '../../kit/ui';
import {easeInOut, enter, exit, mix} from '../../kit/motion';
import {SAFE_RECT} from '../../timing';
import {NB} from '../../styles/scalar-notebook-1';
import {ClueCard, Desk, LocatorMap, Stamp, cardStyle, coverSpan, deal, fitSpan, Ruling} from './notebook';

const X0 = SAFE_RECT.x0, W = SAFE_RECT.x1 - SAFE_RECT.x0;
const PILE_TOP = 596, SLOT_H = 178, SLOT_GAP = 18;            // three clue slots: 596–774, 792–970, 988–1166
const CHOICES_TOP = 1196, THINK_TOP = 1388, EXPLAIN_TOP = 1374;
const MAP_TOP = 590, MAP_H = 404, MAP_HEAD = 54;
const TILTS = [-1.2, 0.9, -0.6];

const Tally: React.FC<TemplateProps & {frame: number}> = ({ep, s, t, frame}) => {
  const checks = ep.q.evidence.checks as {candidateCounts?: number[]; universe?: number};
  const universe = checks.universe ?? 195;
  const counts = checks.candidateCounts ?? [];
  let v = universe, bump = 0;
  counts.forEach((c, i) => {
    const at = (t.items[i] ?? t.items[t.items.length - 1]) + 0.2;
    v = mix(v, c, enter(frame, at, 0.6, easeInOut));
    bump = Math.max(bump, enter(frame, at + 0.45, 0.12) * exit(frame, at + 0.6, 0.3));
  });
  const n = Math.round(v);
  const out = exit(frame, t.cta - 0.3, 0.3);
  return (
    <div style={{position: 'absolute', left: 642, top: 318, width: 258, height: 246, transform: 'rotate(1.4deg)', opacity: out,
      ...cardStyle(s), backgroundColor: s.card, padding: '26px 22px 18px'}}>
      <Ruling width={258 - 6} height={246 - 6} />
      <div style={{position: 'relative', fontFamily: s.fontBody, fontWeight: 700, fontSize: 30, lineHeight: 1.12, color: s.muted, letterSpacing: '0.03em'}}>
        COUNTRIES<br />LEFT OF {universe}
      </div>
      <div style={{position: 'relative', fontFamily: s.fontNumber, fontWeight: 700, fontSize: 104, lineHeight: 1, color: s.fg, marginTop: 6,
        transform: `scale(${1 + 0.06 * bump})`, transformOrigin: '0% 70%'}}>{n}</div>
      {/* Zero-based bar on a single scale: full width = all countries. */}
      <div style={{position: 'relative', marginTop: 12, height: 20, border: `3px solid ${s.line}`, background: s.bg}}>
        <div style={{height: '100%', width: `${(v / universe) * 100}%`, background: s.accent}} />
      </div>
    </div>
  );
};

const Component: React.FC<TemplateProps> = (props) => {
  const {ep, s, t} = props;
  const q = ep.q;
  const frame = useCurrentFrame();
  const clues = q.clues ?? [];
  const out = exit(frame, t.cta - 0.3, 0.3);

  // Anticipation: the pile draws in slightly just before the reveal, and settles back on the impact.
  const inhale = enter(frame, t.reveal - 0.45, 0.4, easeInOut) * (1 - enter(frame, t.reveal, 0.15));
  const pileScale = 1 - 0.018 * inhale;
  // After the stamp, a locator card is dealt over the top two clues.
  const mapDeal = deal(frame, t.reveal + 1.0, -0.8, -1, 0.5);

  // Locator: centred on the question's geo window; span fits the answer with room for context, capped by the window.
  const ansId = q.choices.find((c) => c.key === q.answerKey)?.id;
  const ans = ep.geo.find((c) => c.id === ansId) ?? ep.geo.find((c) => c.label === q.answer || c.name === q.answer);
  const gw = (q as {geoWindow?: number[]}).geoWindow;
  const mapW = W - 6, mapH = MAP_H - MAP_HEAD - 6;
  let center: [number, number] = ans ? ans.centroid : [0, 0];
  let span = 40;
  if (ans) {
    const ansSpan = fitSpan(ans.bbox, mapW, mapH, 0.42);
    const winSpan = gw ? fitSpan(gw, mapW, mapH, 0.95) : ansSpan;
    span = Math.max(16, Math.min(ansSpan, winSpan));
    if (gw) center = [(gw[0] + gw[2]) / 2, (gw[1] + gw[3]) / 2];
  }

  const ghost = 1 - 0.86 * enter(frame, t.reveal, 0.3);   // clue text steps back so the stamp reads
  const slotY = (i: number) => PILE_TOP + i * (SLOT_H + SLOT_GAP);
  const stampY = slotY(2) + SLOT_H / 2;

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Desk s={s} />
      <BrandLabel s={s} t={t} />

      {/* Hook + question: on screen from frame 0. */}
      <div style={{position: 'absolute', left: X0, top: 318, width: 530, opacity: out}}>
        <div style={{fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 74, lineHeight: 1.0, color: s.fg, letterSpacing: '-0.01em'}}>{q.hook}</div>
        <div style={{marginTop: 22, fontFamily: s.fontDisplay, fontWeight: 600, fontStyle: 'italic', fontSize: 58, lineHeight: 1.05, color: NB.tealInk}}>
          {q.question}
        </div>
      </div>
      <Tally {...props} frame={frame} />

      {/* Clue pile. */}
      <div style={{position: 'absolute', inset: 0, transform: `scale(${pileScale})`, transformOrigin: `${X0 + W / 2}px ${slotY(1) + SLOT_H / 2}px`, opacity: out}}>
        {clues.map((text, i) => {
          const d = deal(frame, t.items[i], TILTS[i % TILTS.length], 1);
          if (!d) return null;
          return <ClueCard key={i} s={s} n={i + 1} text={text} x={X0} y={slotY(i)} w={W} h={SLOT_H} transform={d.transform} lift={d.lift} textFade={ghost} />;
        })}
        <Stamp frame={frame} at={t.reveal} cx={X0 + W / 2 + 10} cy={stampY} rotate={-5} small="FOUND" big={q.answer}
          bigSize={q.answer.length > 12 ? 66 : 78} fontDisplay={s.fontDisplay} fontBody={s.fontBody} />
      </div>

      {/* Locator card (never before the reveal). */}
      {mapDeal && ans && (
        <div style={{position: 'absolute', left: X0, top: MAP_TOP, width: W, height: MAP_H, transform: mapDeal.transform, opacity: out,
          ...cardStyle(s, mapDeal.lift), overflow: 'hidden'}}>
          <div style={{height: MAP_HEAD, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px',
            borderBottom: `3px solid ${s.line}`, fontFamily: s.fontBody, fontWeight: 700, fontSize: 30, letterSpacing: '0.12em', color: s.muted}}>
            <span>LOCATOR</span>
            <span style={{display: 'flex', alignItems: 'center', gap: 12, color: s.fg, letterSpacing: '0.02em'}}>
              <span style={{width: 26, height: 26, background: s.accent, border: `3px solid ${s.line}`}} />{ans.label}
            </span>
          </div>
          <LocatorMap s={s} geo={ep.geo} w={mapW} h={mapH} center={center} span={span}
            marks={[{id: ans.id, fill: s.accent, strokeWidth: 3.5}]} ringSmall={ans.id} globe={span > coverSpan(mapW, mapH)} />
        </div>
      )}

      <Choices s={s} t={t} choices={q.choices} answerKey={q.answerKey} top={CHOICES_TOP} fontSize={42}
        chipStyle={{flexDirection: 'column', alignItems: 'flex-start', gap: 4, padding: '14px 18px 18px', boxShadow: `6px 6px 0 ${s.line}`,
          fontFamily: s.fontDisplay, fontWeight: 900, minHeight: 150, boxSizing: 'border-box'}}
        answerStyle={{borderColor: NB.stampInk, boxShadow: `6px 6px 0 ${NB.stampInk}`, background: NB.goodWash}} />
      <ThinkBar s={s} t={t} top={THINK_TOP} />
      <Explanation s={s} t={t} text={q.explanation} top={EXPLAIN_TOP} fontSize={40}
        style={{fontFamily: s.fontDisplay, fontWeight: 600, lineHeight: 1.22}} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const ProgressiveClues: Template = {Component};
