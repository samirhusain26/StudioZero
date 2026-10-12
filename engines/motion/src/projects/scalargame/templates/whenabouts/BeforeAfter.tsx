// Whenabouts · before-after (almanac). Hook → event card (prompt only; its year never shown before the reveal) → the anchor
// pinned on a ruler timeline with its year → a centred “?” token between ◀ BEFORE / AFTER ▶ and the A/B chips → think →
// the token glides down to its side and lands on the ruler at an honest distance, its year appears, a bracket states the gap and
// the ruler ticks settle to the true scale → explanation → closing card.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import {BrandLabel, Choices, EndCard, Explanation, ThinkBar} from '../../kit/ui';
import {SAFE_RECT, f} from '../../timing';
import {easeInOut, enter, exit, mix, pop} from '../../kit/motion';
import {CX, EventCard, Hook, Page, YELLOW, clampLabelX, formatYear, niceStep} from './almanac';
import {ALMANAC_RUST} from '../../styles/whenabouts-almanac-1';

const HOOK_TOP = 328;
const CARD_TOP = 456, CARD_H = 384, HEADLINE_BOX = 236;
const TOKEN_Y = 905, TOKEN_R = 40;
const BRACKET_Y = 976, RULER_Y = 1032;
const ANCHOR_YEAR_TOP = 1062, ANCHOR_PROMPT_TOP = 1140;
const CHIPS_TOP = 1262, THINK_TOP = 1396, EXPLAIN_TOP = 1374;
const OFFSET = 300;          // pixels between anchor and event once revealed (sets the honest scale)
const PRE_TICK = 36;         // unlabelled tick spacing before the reveal (no scale is claimed)

const gapYears = (ev: number, an: number, evidence: Record<string, unknown>) => {
  const g = evidence.gapYears;
  if (typeof g === 'number' && g > 0) return g;
  return Math.abs(ev - an) - (Math.sign(ev) !== Math.sign(an) ? 1 : 0); // no year zero
};

const Timeline: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q;
  const ev = q.event!.year, an = q.anchor!.year;
  const after = q.choices.find((c) => c.key === q.answerKey)?.label.toLowerCase().startsWith('after') ?? ev > an;
  const side = after ? 1 : -1;
  const gap = gapYears(ev, an, q.evidence.checks);
  const ppy = OFFSET / Math.max(1, gap);
  const step = niceStep(ppy, 26);
  const R = t.reveal;
  const tAnchor = t.items[1] ?? 2.0;

  const out = exit(frame, t.cta - 0.3, 0.3);
  // Ruler pans in from the right at the anchor's entry; ticks later settle from the generic spacing to the true scale.
  const rulerIn = enter(frame, tAnchor, 0.5);
  const pan = (1 - rulerIn) * 380;
  const zoom = enter(frame, R + 1.0, 0.8, easeInOut);
  const spacing = mix(PRE_TICK, step * ppy, zoom);
  const ticks: React.ReactNode[] = [];
  for (let k = -Math.ceil((CX + 420) / spacing); CX + k * spacing + pan < 1100; k++) {
    const x = CX + k * spacing + pan;
    if (x < -20) continue;
    ticks.push(<line key={k} x1={x} x2={x} y1={RULER_Y} y2={RULER_Y + 14} stroke={s.line} strokeWidth={2} />);
  }
  const pin = pop(frame, tAnchor + 0.1);
  const anchorText = enter(frame, tAnchor + 0.15, 0.35);

  // Token: centred between the side labels until the reveal (identical whichever side is right).
  const tok = pop(frame, t.choicesIn + 0.05);
  const lift = enter(frame, R - 0.5, 0.45, easeInOut);
  const m = enter(frame, R, 0.7, easeInOut);
  const xEvent = CX + side * OFFSET;
  const tx = mix(CX, xEvent, m);
  // Drops toward the ruler as it travels so it clears the side labels (no upward arc).
  const ty = mix(TOKEN_Y - 12 * lift, RULER_Y, Math.min(1, m * 1.25));
  const tr = mix(TOKEN_R, 22, m);
  const qO = 1 - enter(frame, R + 0.3, 0.25);
  const landed = enter(frame, R + 0.55, 0.25);
  const yearIn = enter(frame, R + 0.6, 0.4);
  const brk = enter(frame, R + 1.0, 0.6, easeInOut);
  const sideO = enter(frame, t.choicesIn, 0.4);
  const sideLit = enter(frame, R + 0.7, 0.4);

  const evLabel = formatYear(ev);
  const evW = evLabel.length * 36 + 30;
  const evX = clampLabelX(xEvent, evW);
  const gapLabel = gap === 1 ? '1 year' : `${gap} years`;
  const midX = (CX + xEvent) / 2;
  const bx0 = Math.min(CX, xEvent), bx1 = Math.max(CX, xEvent);
  const bxA = side > 0 ? bx0 : bx1;
  const bxB = mix(bxA, side > 0 ? bx1 : bx0, brk);

  const sideLabel = (dir: -1 | 1) => {
    const right = dir > 0;
    const isAns = right === after;
    const o = sideO * (sideLit > 0 ? (isAns ? 1 : 1 - 0.6 * sideLit) : 1);
    return (
      <div style={{position: 'absolute', top: TOKEN_Y - 24, left: right ? undefined : SAFE_RECT.x0, right: right ? 1080 - SAFE_RECT.x1 : undefined,
        display: 'flex', alignItems: 'center', gap: 10, flexDirection: right ? 'row-reverse' : 'row', opacity: o,
        transform: `translateX(${(1 - sideO) * dir * 20}px)`}}>
        <svg width={30} height={36}><path d={right ? 'M4,4 L26,18 L4,32 Z' : 'M26,4 L4,18 L26,32 Z'} fill={s.line} /></svg>
        <span style={{fontFamily: s.fontNumber, fontWeight: 700, fontSize: 36, letterSpacing: '0.12em', color: s.fg,
          background: isAns && sideLit > 0 ? `rgba(234,179,8,${sideLit})` : 'transparent', padding: '0 6px'}}>
          {right ? 'AFTER' : 'BEFORE'}
        </span>
      </div>
    );
  };

  if (frame < f(tAnchor)) return null;
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: 1080, height: 1920, opacity: out}}>
      <svg width={1080} height={1920} style={{position: 'absolute', left: 0, top: 0}}>
        <g transform={`translate(${pan},0)`} opacity={rulerIn}>
          <rect x={-400} y={RULER_Y - 2} width={1900} height={30} fill={s.bg2} opacity={0.7} />
          <line x1={-400} x2={1500} y1={RULER_Y} y2={RULER_Y} stroke={s.line} strokeWidth={3} />
        </g>
        {ticks.map((tk, i) => <g key={i} opacity={rulerIn}>{tk}</g>)}
        {/* gap bracket */}
        {brk > 0 && (
          <g stroke={s.line} strokeWidth={3} fill="none">
            <path d={`M${bxA},${BRACKET_Y + 16} L${bxA},${BRACKET_Y} L${bxB},${BRACKET_Y} ${brk > 0.98 ? `L${bxB},${BRACKET_Y + 16}` : ''}`} />
          </g>
        )}
        {/* anchor pin */}
        {pin > 0 && (
          <g transform={`translate(${CX},${RULER_Y}) scale(${Math.min(1.1, pin)})`}>
            <line x1={0} x2={0} y1={-6} y2={22} stroke={s.line} strokeWidth={4} />
            <path d="M0,-4 C-7,-16 -16,-24 -16,-36 A16,16 0 1 1 16,-36 C16,-24 7,-16 0,-4 Z" fill={ALMANAC_RUST} stroke={s.line} strokeWidth={2.5} />
            <circle cx={0} cy={-36} r={6} fill={s.card} />
          </g>
        )}
        {/* the event token */}
        {tok > 0 && (
          <g transform={`translate(${tx},${ty}) scale(${Math.min(1.08, tok)})`}>
            {m === 0 && <line x1={0} x2={0} y1={TOKEN_R} y2={RULER_Y - TOKEN_Y - 44} stroke={s.line} strokeWidth={2} strokeDasharray="6 7" opacity={0.6} />}
            <circle r={tr} fill={landed > 0 ? YELLOW : s.card} stroke={lift > 0.5 && m === 0 ? s.accent : s.line} strokeWidth={4} />
          </g>
        )}
      </svg>
      {tok > 0 && qO > 0 && (
        <div style={{position: 'absolute', left: tx - 40, top: ty - 40, width: 80, height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: s.fontDisplay, fontStyle: 'italic', fontWeight: 900, fontSize: 58, color: s.fg, opacity: qO * Math.min(1, tok),
          transform: `scale(${Math.min(1.08, tok) * tr / TOKEN_R})`}}>?</div>
      )}
      {sideLabel(-1)}
      {sideLabel(1)}
      {/* event year (after the reveal only) */}
      {yearIn > 0 && (
        <div style={{position: 'absolute', left: evX - evW / 2, width: evW, top: ANCHOR_YEAR_TOP - 4 - (1 - yearIn) * 16, textAlign: 'center', opacity: yearIn}}>
          <span style={{fontFamily: s.fontNumber, fontWeight: 700, fontSize: 56, color: s.fg, background: YELLOW, padding: '0 10px'}}>{evLabel}</span>
        </div>
      )}
      {brk > 0.6 && (
        <div style={{position: 'absolute', left: midX - 160, width: 320, top: BRACKET_Y - 52, textAlign: 'center',
          fontFamily: s.fontDisplay, fontStyle: 'italic', fontWeight: 900, fontSize: 40, color: s.fg, opacity: enter(frame, R + 1.4, 0.3)}}>
          {gapLabel}
        </div>
      )}
      {/* anchor year + prompt */}
      <div style={{position: 'absolute', left: CX - 200, width: 400, top: ANCHOR_YEAR_TOP, textAlign: 'center', opacity: anchorText,
        fontFamily: s.fontNumber, fontWeight: 700, fontSize: 56, color: s.fg}}>
        {formatYear(an)}
      </div>
      <div style={{position: 'absolute', left: SAFE_RECT.x0, width: SAFE_RECT.x1 - SAFE_RECT.x0, top: ANCHOR_PROMPT_TOP, textAlign: 'center',
        opacity: anchorText, fontFamily: s.fontDisplay, fontStyle: 'italic', fontWeight: 600, fontSize: 42, lineHeight: 1.12, color: ALMANAC_RUST,
        textWrap: 'balance'}}>
        {q.anchorPrompt ?? q.anchor!.title}
      </div>
    </div>
  );
};

const Component: React.FC<TemplateProps> = (props) => {
  const {ep, s, t} = props;
  const q = ep.q;
  return (
    <AbsoluteFill style={{color: s.fg}}>
      <Page s={s} />
      <BrandLabel s={s} t={t} />
      <Hook s={s} t={t} text={q.hook} top={HOOK_TOP} />
      <EventCard s={s} t={t} at={t.items[0] ?? 0.6} top={CARD_TOP} height={CARD_H} kicker="The event" headline={q.prompt ?? q.question}
        headlineBox={HEADLINE_BOX} />
      <Timeline {...props} />
      <Choices s={s} t={t} choices={q.choices} answerKey={q.answerKey} top={CHIPS_TOP} fontSize={48} revealAt={t.reveal + 0.7}
        chipStyle={{justifyContent: 'center', boxShadow: `5px 5px 0 ${s.bg2}`}} answerStyle={{background: YELLOW, transform: 'none'}} />
      <ThinkBar s={s} t={t} top={THINK_TOP} />
      <Explanation s={s} t={t} text={q.explanation} top={EXPLAIN_TOP} fontSize={38} style={{fontWeight: 600}} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const BeforeAfter: Template = {
  Component,
  extraCues: ({t}) => [
    {at: t.reveal + 0.55, name: 'thock' as const, volume: 0.5},
    {at: t.reveal + 1.0, name: 'whip' as const, volume: 0.3},
  ],
};
