// Continuum · missing slot (continuum-poster-1). An ORDINAL ladder (equal rungs, “rank order · not to scale”): the two
// anchors (low at the bottom, high at the top, values “?”) at t.items[0], the pink target card at t.items[1] in a holding
// bay above the ladder, three identical dashed insertion gaps A (below low) / B (between) / C (above high) labelled with
// the full choice text at t.choicesIn. At t.reveal the target drops into its gap, then all three values count up to their
// exact text and thin bars grow from the ladder spine, which becomes a labelled zero line on one linear scale.
import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import type {Valued} from '../../types';
import {BrandLabel, EndCard, Explanation, ThinkBar} from '../../kit/ui';
import {SAFE_RECT, f} from '../../timing';
import {easeOut, enter, exit, pop} from '../../kit/motion';
import {Arrow, Backdrop, SAFE_W, SourceLine, countText, niceCeil, scaleLabel} from './shared';

const X0 = SAFE_RECT.x0;
const QUESTION_TOP = 318;
const BAY_Y = 540;             // target holding bay
const SPINE_X = 122;           // ladder spine = later the zero line
const ROW_X = SPINE_X, ROW_W = SAFE_RECT.x1 - SPINE_X;
const ROWS_TOP = 712, ROW_H = 92, ROW_STEP = 102;
const ROWS_BOTTOM = ROWS_TOP + 4 * ROW_STEP + ROW_H;   // 1212
const NAME_X = 40;             // relative to ROW_X
const BAR_MAX = 736;
const BAR_DY = 70, BAR_H = 14;
const PIN = 54;
const LOWER_TOP = 1300;
const SOURCE_TOP = 1446;
const DROP = 0.65;             // target travel (s) from the downbeat
const COUNT_AT = 0.85, COUNT = 1.2;
const dropEase = Easing.bezier(0.55, 0, 0.15, 1);

const rowY = (i: number) => ROWS_TOP + i * ROW_STEP;   // 0 = C (top) … 4 = A (bottom)

const Component: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q;
  const area = q.metric?.id === 'area';
  const more = area ? 'Larger area' : 'More people';
  const fewer = area ? 'Smaller area' : 'Fewer people';
  const anchors = [...(q.anchors ?? [])].sort((a, b) => a.value - b.value);
  const [low, high] = anchors;
  const target = q.target as Valued;
  const textOf = (v: Valued) => q.values?.find((x) => x.id === v.id)?.text ?? v.text;
  const scaleMax = niceCeil(Math.max(low.value, high.value, target.value));
  const barPx = (v: number) => (BAR_MAX * v) / scaleMax;

  const choices = q.choices.slice(0, 3);                     // A below low, B between, C above high
  const gapRow = (k: number) => 4 - 2 * k;
  const ansIdx = Math.max(0, choices.findIndex((c) => c.key === q.answerKey));
  const slotY = rowY(gapRow(ansIdx));

  const out = exit(frame, t.cta - 0.3, 0.3);
  const ladderIn = enter(frame, t.items[0], 0.45);
  const lift = enter(frame, t.reveal - 0.4, 0.4) * (1 - enter(frame, t.reveal + DROP - 0.1, 0.2));
  const drop = interpolate(frame, [f(t.reveal), f(t.reveal + DROP)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: dropEase});
  const settled = enter(frame, t.reveal + 0.45, 0.35);       // other gaps dim, answer gap label hides
  const count = enter(frame, t.reveal + COUNT_AT, COUNT, easeOut);
  const axis = enter(frame, t.reveal + COUNT_AT - 0.15, 0.35);
  const valuesOn = frame >= f(t.reveal + COUNT_AT);
  const qHide = 1 - enter(frame, t.reveal + COUNT_AT - 0.25, 0.2);

  const ValueText: React.FC<{v: Valued}> = ({v}) => (
    <div style={{position: 'absolute', right: 18, top: 14, fontFamily: s.fontNumber, fontWeight: 700, fontSize: 40, lineHeight: '50px',
      color: s.fg, whiteSpace: 'nowrap'}}>
      {valuesOn ? countText(textOf(v), count) : <span style={{opacity: qHide}}>?</span>}
    </div>
  );
  const Bar: React.FC<{v: Valued; color: string}> = ({v, color}) => (
    <div style={{position: 'absolute', left: 0, top: BAR_DY, width: barPx(v.value) * count, height: BAR_H, background: color}} />
  );

  const Anchor: React.FC<{v: Valued; i: number; at: number}> = ({v, i, at}) => {
    const p = enter(frame, at, 0.45);
    return (
      <div style={{position: 'absolute', left: ROW_X, top: rowY(i), width: ROW_W, height: ROW_H, opacity: p,
        transform: `translateX(${(1 - p) * 60}px)`}}>
        <div style={{position: 'absolute', inset: 0, background: s.card, border: `3px solid ${s.fg}`}} />
        <div style={{position: 'absolute', left: NAME_X, top: 12, fontFamily: s.fontDisplay, fontWeight: 800, fontSize: 46,
          lineHeight: '50px', color: s.fg, whiteSpace: 'nowrap'}}>{v.label}</div>
        <ValueText v={v} />
        <Bar v={v} color={s.fg} />
      </div>
    );
  };

  return (
    <AbsoluteFill>
      <Backdrop s={s} />
      <BrandLabel s={s} t={t} />

      <div style={{opacity: out}}>
        {/* Question: on screen from frame 0 */}
        <div style={{position: 'absolute', left: X0, top: QUESTION_TOP, width: SAFE_W, fontFamily: s.fontDisplay, fontWeight: 900,
          fontSize: 62, lineHeight: 1.06, letterSpacing: '-0.015em', color: s.fg}}>
          {q.question}
        </div>

        {/* Ordinal ladder: spine with arrow, direction labels, “not to scale” */}
        <div style={{opacity: ladderIn}}>
          <div style={{position: 'absolute', left: SPINE_X - 2, top: ROWS_TOP - 36, width: 5, height: ROWS_BOTTOM - ROWS_TOP + 36 + 10 * (1 - axis), background: s.fg}} />
          <div style={{position: 'absolute', left: SPINE_X - 17, top: ROWS_TOP - 66}}><Arrow dir="up" color={s.fg} size={36} /></div>
          <div style={{position: 'absolute', left: SPINE_X + 32, top: ROWS_TOP - 60, fontFamily: s.fontBody, fontWeight: 800, fontSize: 30,
            letterSpacing: '0.1em', textTransform: 'uppercase', color: s.fg}}>{more}</div>
          <div style={{position: 'absolute', left: SPINE_X + 32, top: ROWS_BOTTOM + 12, width: SAFE_RECT.x1 - SPINE_X - 32, opacity: 1 - axis,
            display: 'flex', justifyContent: 'space-between', fontFamily: s.fontBody, fontSize: 30, color: s.fg}}>
            <span style={{fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase'}}>
              <Arrow dir="down" color={s.fg} size={24} /> {fewer}
            </span>
            <span style={{fontWeight: 600, color: s.muted}}>Rank order · not to scale</span>
          </div>
        </div>

        {/* Insertion gaps A/B/C — identical until the reveal */}
        {choices.map((c, k) => {
          const p = pop(frame, t.choicesIn + k * 0.12);
          const isAns = k === ansIdx;
          const dim = isAns ? 1 : 1 - 0.7 * settled;
          return (
            <div key={c.key} style={{position: 'absolute', left: ROW_X, top: rowY(gapRow(k)), width: ROW_W, height: ROW_H,
              opacity: Math.min(1, p) * dim, transform: `translateY(${(1 - Math.min(1, p)) * 30}px)`}}>
              <div style={{position: 'absolute', inset: 0, border: `3px dashed ${s.muted}`, background: 'rgba(255,255,255,0.35)'}} />
              <div style={{position: 'absolute', left: NAME_X, top: 0, height: ROW_H, display: 'flex', alignItems: 'center', fontFamily: s.fontBody,
                fontWeight: 700, fontSize: 34, color: s.muted, whiteSpace: 'nowrap',
                textDecoration: !isAns && settled > 0.5 ? 'line-through' : undefined}}>{c.label}</div>
              <div style={{position: 'absolute', left: -PIN / 2, top: (ROW_H - PIN) / 2, width: PIN, height: PIN, background: s.fg, color: s.bg,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: s.fontNumber, fontWeight: 700, fontSize: 38}}>{c.key}</div>
            </div>
          );
        })}

        {/* Anchors: low at the bottom, high at the top */}
        <Anchor v={low} i={3} at={t.items[0]} />
        <Anchor v={high} i={1} at={t.items[0] + 0.15} />

        {/* rungs: small nodes where anchors meet the spine */}
        {[1, 3].map((i) => (
          <div key={i} style={{position: 'absolute', left: SPINE_X - 11, top: rowY(i) + ROW_H / 2 - 11, width: 22, height: 22, background: s.fg,
            opacity: enter(frame, t.items[0], 0.45)}} />
        ))}

        {/* Target card: holding bay → its gap */}
        {(() => {
          const p = enter(frame, t.items[1], 0.5);
          const y = BAY_Y + (slotY - BAY_Y) * drop;
          const pinPop = pop(frame, t.reveal + DROP - 0.1);
          return (
            <div style={{position: 'absolute', left: ROW_X, top: y, width: ROW_W, height: ROW_H, opacity: p,
              transform: `translateX(${(1 - p) * 120}px) translate(${-6 * lift}px, ${-6 * lift}px) rotate(${-1.4 * (1 - drop)}deg)`}}>
              <div style={{position: 'absolute', inset: 0, background: s.accent, border: `3px solid ${s.fg}`,
                boxShadow: `${6 + 6 * lift - 6 * drop}px ${6 + 6 * lift - 6 * drop}px 0 ${s.fg}`}} />
              <div style={{position: 'absolute', left: NAME_X, top: 12, fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 46,
                lineHeight: '50px', color: s.fg, whiteSpace: 'nowrap'}}>{target.label}</div>
              <ValueText v={target} />
              <Bar v={target} color={s.fg} />
              {pinPop > 0 && <div style={{position: 'absolute', left: -PIN / 2, top: (ROW_H - PIN) / 2, width: PIN, height: PIN, background: s.fg,
                color: s.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: s.fontNumber, fontWeight: 700,
                fontSize: 38, transform: `scale(${pinPop})`}}>{choices[ansIdx]?.key}</div>}
            </div>
          );
        })()}

        {/* One linear scale from the spine (zero) — appears with the values */}
        <div style={{opacity: axis}}>
          <div style={{position: 'absolute', left: SPINE_X, top: ROWS_BOTTOM + 10, width: BAR_MAX, height: 3, background: s.fg}} />
          <div style={{position: 'absolute', left: SPINE_X - 2, top: ROWS_BOTTOM, width: 5, height: 24, background: s.fg}} />
          <div style={{position: 'absolute', left: SPINE_X + BAR_MAX - 2, top: ROWS_BOTTOM + 10, width: 3, height: 14, background: s.fg}} />
          <div style={{position: 'absolute', left: SPINE_X - 40, width: 80, top: ROWS_BOTTOM + 28, textAlign: 'center', fontFamily: s.fontNumber,
            fontWeight: 700, fontSize: 32, color: s.fg}}>0</div>
          <div style={{position: 'absolute', right: 1080 - (SPINE_X + BAR_MAX) - 2, top: ROWS_BOTTOM + 28, fontFamily: s.fontNumber,
            fontWeight: 700, fontSize: 32, color: s.fg, whiteSpace: 'nowrap'}}>{scaleLabel(scaleMax, q.metric?.id)}</div>
        </div>
      </div>

      <ThinkBar s={s} t={t} top={LOWER_TOP} />
      <Explanation s={s} t={t} text={q.explanation} top={LOWER_TOP - 6} fontSize={38}
        style={{fontWeight: 600, borderLeft: `8px solid ${s.accent}`, paddingLeft: 22, width: SAFE_W - 30}} />
      <SourceLine s={s} t={t} q={q} top={SOURCE_TOP} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const MissingSlot: Template = {
  Component,
  extraCues: ({t}) => [{at: t.reveal + DROP, name: 'thock', volume: 0.55}],
};
