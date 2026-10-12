// Whenabouts almanac furniture shared by GuessTheYear and BeforeAfter: parchment page, hook line, typographic event card
// with vector fleurons, year formatting, ruler tick maths and the year odometer.
import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import type {StyleTokens, Timing} from '../../types';
import {SAFE_RECT, f} from '../../timing';
import {easeInOut, enter, exit, progress} from '../../kit/motion';
import {ALMANAC_YELLOW} from '../../styles/whenabouts-almanac-1';

export const CX = (SAFE_RECT.x0 + SAFE_RECT.x1) / 2; // 495: horizontal centre of the safe rectangle
export const SAFE_W = SAFE_RECT.x1 - SAFE_RECT.x0;
export const YELLOW = ALMANAC_YELLOW;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** Whenabouts year rule: negative → "N BCE", below 1000 → "N CE", otherwise the bare year. */
export const formatYear = (y: number) => (y < 0 ? `${-y} BCE` : y < 1000 ? `${y} CE` : `${y}`);

/** Parse a choice label like "1889", "325 CE" or "44 BCE" to a signed year (fallback when a choice has no `year`). */
export const parseYear = (label: string): number | null => {
  const m = label.match(/(\d+)/);
  if (!m) return null;
  return /BCE|BC\b/i.test(label) ? -Number(m[1]) : Number(m[1]);
};

/** A tick step from 1·2·5 × 10ⁿ whose pixel spacing is at least `minPx` at `pxPerYear`. */
export const niceStep = (pxPerYear: number, minPx: number) => {
  for (let e = 0; e < 6; e++) for (const m of [1, 2, 5]) {
    const s = m * 10 ** e;
    if (s * pxPerYear >= minPx) return s;
  }
  return 100000;
};

/** Parchment page: vignette, laid-paper lines, double-rule frame (decoration may bleed past the safe rectangle). */
// As SVG (client-side rendering has no radial or repeating CSS gradients): radial-gradient(ellipse 85% 70% at 46% 45%,
// bg 55%, bg2 100%) and repeating-linear-gradient(0deg, line 0 1px, transparent 1px 7px), whose 1 px lines repeat every
// 7 px up from the bottom edge (y = 1, 8, 15 … from the top of a 1920 px frame).
export const Page: React.FC<{s: StyleTokens}> = ({s}) => (
  <AbsoluteFill>
    <svg width={1080} height={1920} style={{position: 'absolute', left: 0, top: 0}} aria-hidden>
      <defs>
        <radialGradient id="wa-vignette" gradientUnits="userSpaceOnUse" cx={496.8} cy={864} r={918}
          gradientTransform={`translate(496.8 864) scale(1 ${1344 / 918}) translate(-496.8 -864)`}>
          <stop offset={0.55} stopColor={s.bg} />
          <stop offset={1} stopColor={s.bg2} />
        </radialGradient>
        <pattern id="wa-laid" width={1080} height={7} patternUnits="userSpaceOnUse">
          <rect x={0} y={1} width={1080} height={1} fill="rgba(43,29,14,0.035)" />
        </pattern>
      </defs>
      <rect width={1080} height={1920} fill="url(#wa-vignette)" />
      <rect width={1080} height={1920} fill="url(#wa-laid)" shapeRendering="crispEdges" />
    </svg>
    <div style={{position: 'absolute', left: 40, top: 150, right: 40, bottom: 150, border: `2px solid ${s.line}`, opacity: 0.28}} />
    <div style={{position: 'absolute', left: 50, top: 160, right: 50, bottom: 160, border: `1px solid ${s.line}`, opacity: 0.22}} />
  </AbsoluteFill>
);

/** A drawn fleuron: rules ending in curls around a central lozenge. Pure SVG, no glyph dependence. */
export const Fleuron: React.FC<{color: string; width?: number; dot?: string}> = ({color, width = 360, dot}) => {
  const w = width, h = 36, c = w / 2;
  const curl = (dir: 1 | -1) => {
    const x = c + dir * 26;
    return `M${x},18 C${x + dir * 14},6 ${x + dir * 34},6 ${x + dir * 34},16 C${x + dir * 34},24 ${x + dir * 24},26 ${x + dir * 20},20`;
  };
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{display: 'block'}}>
      <line x1={0} y1={18} x2={c - 64} y2={18} stroke={color} strokeWidth={2} />
      <line x1={c + 64} y1={18} x2={w} y2={18} stroke={color} strokeWidth={2} />
      <path d={curl(-1)} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" />
      <path d={curl(1)} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" />
      <path d={`M${c},6 L${c + 11},18 L${c},30 L${c - 11},18 Z`} fill={dot ?? color} stroke={color} strokeWidth={1.5} />
      <circle cx={c - 64} cy={18} r={3} fill={color} />
      <circle cx={c + 64} cy={18} r={3} fill={color} />
    </svg>
  );
};

/** The hook line, legible from frame 0, with a yellow swash drawing under it. */
export const Hook: React.FC<{s: StyleTokens; t: Timing; text: string; top: number}> = ({s, t, text, top}) => {
  const frame = useCurrentFrame();
  const draw = enter(frame, 0.1, 0.7);
  const o = exit(frame, t.cta - 0.3, 0.3);
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, top, width: SAFE_W, opacity: o}}>
      <div style={{fontFamily: s.fontDisplay, fontStyle: 'italic', fontWeight: 900, fontSize: 76, lineHeight: 1, color: s.fg,
        transform: `translateY(${(1 - enter(frame, 0, 0.5)) * 10}px)`}}>
        {text}
      </div>
      <svg width={430} height={22} style={{display: 'block', marginTop: 6}}>
        <path d="M4,14 C120,4 260,4 426,12" fill="none" stroke={YELLOW} strokeWidth={10} strokeLinecap="round"
          pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
      </svg>
    </div>
  );
};

/**
 * Typographic event card: double rule, kicker with fleuron, the prompt as the italic headline, optional footer slot.
 * Enters at `at` (≤ 0.5 s, laid down with a tiny settle).
 */
export const EventCard: React.FC<{
  s: StyleTokens; t: Timing; at: number; top: number; height: number; kicker: string; headline: string;
  headlineBox: number; children?: React.ReactNode;
}> = ({s, t, at, top, height, kicker, headline, headlineBox, children}) => {
  const frame = useCurrentFrame();
  const e = enter(frame, at, 0.5);
  const o = exit(frame, t.cta - 0.3, 0.3);
  if (frame < f(at)) return null;
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, top, width: SAFE_W, height, opacity: e * o,
      transform: `translateY(${(1 - e) * 46}px) rotate(${(1 - e) * -1.4}deg)`, transformOrigin: '50% 100%',
      background: s.card, border: `3px solid ${s.line}`, boxShadow: `8px 8px 0 ${s.bg2}`}}>
      <div style={{position: 'absolute', inset: 10, border: `1px solid ${s.line}`, opacity: 0.55}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 30, display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
        <div style={{fontFamily: s.fontNumber, fontWeight: 700, fontSize: 30, letterSpacing: '0.22em', color: s.muted, textTransform: 'uppercase'}}>
          {kicker}
        </div>
        <div style={{marginTop: 10}}><Fleuron color={s.muted} width={300} /></div>
        <div style={{height: headlineBox, width: SAFE_W - 90, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
          fontFamily: s.fontDisplay, fontStyle: 'italic', fontWeight: 900, fontSize: 68, lineHeight: 1.1, color: s.fg, textWrap: 'balance'}}>
          {headline}
        </div>
        {children}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------------------------------------------------
// Year odometer

const DRUM_W = 104, DRUM_H = 150, DIGIT_PX = 124;

const Drum: React.FC<{s: StyleTokens; p: number; lit: number; border: string}> = ({s, p, lit, border}) => {
  // Strip index 0 is “?”, index k ≥ 1 is digit (k − 1) mod 10; negative indices are blank.
  const base = Math.floor(p);
  const cells = [];
  for (let j = base - 1; j <= base + 2; j++) {
    if (j < 0) continue;
    const ch = j === 0 ? '?' : String((j - 1) % 10);
    cells.push(
      <div key={j} style={{position: 'absolute', left: 0, width: DRUM_W, height: DRUM_H, top: (j - p) * DRUM_H,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: j === 0 ? s.fontDisplay : s.fontNumber,
        fontStyle: j === 0 ? 'italic' : 'normal', fontWeight: j === 0 ? 900 : 700, fontSize: DIGIT_PX, color: j === 0 ? s.muted : s.fg}}>
        {ch}
      </div>,
    );
  }
  return (
    <div style={{position: 'relative', width: DRUM_W, height: DRUM_H, overflow: 'hidden', border: `3px solid ${border}`,
      background: s.card}}>
      <div style={{position: 'absolute', inset: 0, background: `rgba(234,179,8,${0.55 * lit})`}} />
      {cells}
      <div style={{position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'linear-gradient(rgba(43,29,14,0.22), rgba(43,29,14,0) 26%, rgba(43,29,14,0) 74%, rgba(43,29,14,0.22))'}} />
    </div>
  );
};

/**
 * Year odometer. Before `t.reveal` it shows `placeholder` “?” drums (count independent of the answer), winds back slightly
 * in the last half-second, then from `t.reveal` the drums roll left-to-right to the exact characters of `answer`
 * (digits roll; other characters such as “ CE” are set static beside them). Returns the land time of the last drum.
 */
export const odometerLandTimes = (t: Timing, answer: string) => {
  const n = answer.replace(/\D/g, '').length;
  return Array.from({length: n}, (_, i) => t.reveal + 0.5 + 0.14 * i);
};

export const Odometer: React.FC<{s: StyleTokens; t: Timing; answer: string; placeholder: number}> = ({s, t, answer, placeholder}) => {
  const frame = useCurrentFrame();
  const revealed = frame >= f(t.reveal);
  const wind = -0.16 * enter(frame, t.reveal - 0.55, 0.45, easeInOut);
  const tension = enter(frame, t.reveal - 0.55, 0.3);
  const lands = odometerLandTimes(t, answer);
  const lit = enter(frame, t.reveal + 1.0, 0.4);
  const border = !revealed && tension > 0.5 ? s.accent : s.line;
  const gap = 12;
  if (!revealed) {
    return (
      <div style={{display: 'flex', gap}}>
        {Array.from({length: placeholder}, (_, i) => <Drum key={i} s={s} p={wind} lit={0} border={border} />)}
      </div>
    );
  }
  let d = 0;
  return (
    <div style={{display: 'flex', gap, alignItems: 'flex-end'}}>
      {[...answer].map((ch, i) => {
        if (!/\d/.test(ch)) {
          if (ch === ' ') return <div key={i} style={{width: 4}} />;
          return (
            <div key={i} style={{fontFamily: s.fontNumber, fontWeight: 700, fontSize: 64, color: s.fg, lineHeight: 1, paddingBottom: 18,
              opacity: enter(frame, lands[lands.length - 1] ?? t.reveal, 0.3)}}>{ch}</div>
          );
        }
        const k = d++;
        const target = 1 + 10 * (1 + k) + Number(ch);
        const u = interpolate(frame, [f(t.reveal), f(lands[k])], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
        return <Drum key={i} s={s} p={wind + (target - wind) * u} lit={lit} border={s.line} />;
      })}
    </div>
  );
};

/** Clamp a label's centre so a label of width `w` stays inside the safe rectangle. */
export const clampLabelX = (x: number, w: number) => Math.min(SAFE_RECT.x1 - w / 2, Math.max(SAFE_RECT.x0 + w / 2, x));

export {progress};
