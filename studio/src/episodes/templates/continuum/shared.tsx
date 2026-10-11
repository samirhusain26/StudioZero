// Continuum · data-poster furniture shared by HeadToHead and MissingSlot: backdrop, source line, honest scale helpers,
// count-up text that lands verbatim on the displayed value.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Question, StyleTokens, Timing} from '../../types';
import {SAFE_RECT} from '../../timing';
import {exit} from '../../kit/motion';
import {PINK_INK, GRID} from '../../styles/continuum-poster-1';

export const SAFE_W = SAFE_RECT.x1 - SAFE_RECT.x0;

/** Cream paper with a faint print grid and a pink spine bleeding off the left edge. Decoration only. */
export const Backdrop: React.FC<{s: StyleTokens}> = ({s}) => (
  <AbsoluteFill style={{background: s.bg}}>
    <AbsoluteFill style={{
      backgroundImage: `linear-gradient(to right, ${GRID} 1px, transparent 1px), linear-gradient(to bottom, ${GRID} 1px, transparent 1px)`,
      backgroundSize: '90px 90px', backgroundPosition: '0px 0px',
    }} />
    <div style={{position: 'absolute', left: 0, top: 0, width: 34, height: 1920, background: s.accent}} />
    <div style={{position: 'absolute', left: 34, top: 0, width: 4, height: 1920, background: s.fg}} />
  </AbsoluteFill>
);

/** “Total population (World Bank estimate), 2025” — visible throughout, fades under the closing card. */
export const SourceLine: React.FC<{s: StyleTokens; t: Timing; q: Question; top: number}> = ({s, t, q, top}) => {
  const frame = useCurrentFrame();
  if (!q.metric) return null;
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, width: SAFE_W, top, opacity: exit(frame, t.cta - 0.3, 0.3),
      borderTop: `2px solid ${s.fg}`, paddingTop: 12, fontFamily: s.fontBody, fontWeight: 600, fontSize: 30, lineHeight: 1.25, color: s.muted}}>
      {q.metric.definition}, {q.metric.year}
    </div>
  );
};

/** Smallest “nice” number ≥ v (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 × 10^k): the right end of the one shared scale. */
export function niceCeil(v: number): number {
  const k = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * k >= v * 0.999999) return m * k;
  return 10 * k;
}

const commas = (n: number) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

/** Axis label for a scale value, written in the metric's own units. */
export function scaleLabel(v: number, metricId: string | undefined): string {
  if (v === 0) return '0';
  const trim = (x: number) => String(Number(x.toFixed(2)));
  if (metricId === 'area') return v >= 1e6 ? `${trim(v / 1e6)} million km²` : `${commas(v)} km²`;
  return v >= 1e9 ? `${trim(v / 1e9)} billion` : v >= 1e6 ? `${trim(v / 1e6)} million` : commas(v);
}

/**
 * Count-up of a displayed value text (“51.4 million”, “378,000 km²”). The figure part scales with `p` at the same
 * precision as the final text; at p ≥ 1 the exact text is returned verbatim.
 */
export function countText(text: string, p: number): string {
  if (p >= 1) return text;
  const m = text.match(/^([\d,]+(?:\.\d+)?)(.*)$/);
  if (!m) return p > 0.5 ? text : '';
  const raw = m[1];
  const target = parseFloat(raw.replace(/,/g, ''));
  const dec = raw.includes('.') ? raw.split('.')[1].length : 0;
  const cur = target * Math.max(0, p);
  let s: string;
  if (dec > 0) s = cur.toFixed(dec);
  else {
    const zeros = (raw.replace(/,/g, '').match(/0+$/)?.[0].length ?? 0);
    const g = Math.pow(10, Math.min(zeros, 3));
    s = String(Math.round(cur / g) * g);
  }
  if (raw.includes(',')) {
    const [i, d] = s.split('.');
    s = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : '');
  }
  return s + m[2];
}

/** Pink check mark in a black disc (no glyph dependency). */
export const Check: React.FC<{size: number; s: StyleTokens; scale?: number}> = ({size, s, scale = 1}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{transform: `scale(${scale})`, display: 'block'}}>
    <circle cx="50" cy="50" r="48" fill={s.fg} />
    <path d="M27 52 L44 68 L74 34" fill="none" stroke={s.accent} strokeWidth="12" strokeLinecap="square" />
  </svg>
);

/** Small up/down arrow for the ordinal ladder. */
export const Arrow: React.FC<{dir: 'up' | 'down'; color: string; size?: number}> = ({dir, color, size = 26}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{display: 'inline-block', verticalAlign: '-3px', transform: dir === 'down' ? 'rotate(180deg)' : undefined}}>
    <path d="M50 8 L90 56 L62 56 L62 94 L38 94 L38 56 L10 56 Z" fill={color} />
  </svg>
);

export {PINK_INK};
