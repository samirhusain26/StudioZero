// Shared episode furniture: brand label, choices, thinking bar, explanation, closing card, safe-area overlay.
// Every element takes the style tokens; layout positions stay inside SAFE_RECT.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Choice, Game, StyleTokens, Timing} from '../types';
import {SAFE_RECT, f} from '../timing';
import {enter, exit, pop, progress} from './motion';

export const GAME_NAME: Record<Game, string> = {scalar: 'Scalar', continuum: 'Continuum', whenabouts: 'Whenabouts', tectonic: 'Tectonic'};
const W = SAFE_RECT.x1 - SAFE_RECT.x0;

/** Small, quiet “SCALARGAME · GAME” label at the top of the safe area. Hidden under the closing card. */
export const BrandLabel: React.FC<{s: StyleTokens; t: Timing; top?: number; color?: string}> = ({s, t, top = SAFE_RECT.y0, color}) => {
  const frame = useCurrentFrame();
  const o = exit(frame, t.cta - 0.2, 0.3);
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, top, opacity: o, fontFamily: s.fontBody, fontSize: 26, fontWeight: 700,
      letterSpacing: '0.14em', color: color ?? s.muted, textTransform: 'uppercase'}}>
      Scalargame <span style={{color: s.accent}}>·</span> {GAME_NAME[s.game]}
    </div>
  );
};

/**
 * A/B/C (or A/B) choice chips. They enter at t.choicesIn; at t.reveal the answer gets the `good` border and the others dim
 * (no scaling, so chips never leave the safe area). Row chips always have equal widths: a chip's size must never hint at
 * the answer, so long labels wrap instead of widening their chip.
 * `layout`: 'row' for short labels, 'column' for long ones. Callers choose position via `top`.
 */
export const Choices: React.FC<{
  s: StyleTokens; t: Timing; choices: Choice[]; answerKey: string; top: number; layout?: 'row' | 'column'; fontSize?: number;
  revealAt?: number; chipStyle?: React.CSSProperties; answerStyle?: React.CSSProperties;
}> = ({s, t, choices, answerKey, top, layout = 'row', fontSize = 40, revealAt, chipStyle, answerStyle}) => {
  const frame = useCurrentFrame();
  const r = enter(frame, revealAt ?? t.reveal, 0.4);
  const out = exit(frame, t.cta - 0.3, 0.3);
  // Row chips share one width and one font size. The size is the largest (≤ fontSize, ≥ 34 px) at which the longest
  // single word of any label fits its chip, estimated at 0.62 em per character; labels wrap only between words.
  let fs = fontSize;
  if (layout === 'row') {
    const chipW = (W - 18 * (choices.length - 1)) / choices.length;
    const stacked = chipStyle?.flexDirection === 'column';
    const avail = chipW - 50 - (stacked ? 0 : fontSize * 0.9 * 0.62 + 16);
    const longestWord = Math.max(...choices.flatMap((c) => c.label.split(/\s+/).map((w) => w.length)));
    fs = Math.max(34, Math.min(fontSize, Math.floor(avail / (longestWord * 0.62))));
  }
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, width: W, top, display: 'flex', flexDirection: layout === 'row' ? 'row' : 'column',
      gap: layout === 'row' ? 18 : 14, opacity: out}}>
      {choices.map((c, i) => {
        const p = pop(frame, t.choicesIn + i * 0.12);
        const isAns = c.key === answerKey;
        return (
          <div key={c.key} style={{flex: layout === 'row' ? '1 1 0' : undefined, minWidth: 0, display: 'flex', alignItems: 'center', gap: 16,
            padding: '18px 22px', background: s.card, color: s.fg, border: `3px solid ${isAns && r > 0 ? s.good : s.line}`, fontFamily: s.fontBody,
            fontSize: fs, fontWeight: 700, lineHeight: 1.1, opacity: p * (isAns ? 1 : 1 - 0.65 * r),
            transform: `translateY(${(1 - p) * 40}px)`, ...chipStyle, ...(isAns && r > 0 ? answerStyle : {})}}>
            <span style={{fontFamily: s.fontNumber, color: isAns && r > 0 ? s.good : s.accent, fontSize: fs * 0.9}}>{c.key}</span>
            <span style={{minWidth: 0, overflowWrap: 'normal', textDecoration: !isAns && r > 0.5 ? 'line-through' : undefined}}>{c.label}</span>
          </div>
        );
      })}
    </div>
  );
};

/** Calm thinking indicator: a bar that drains from infoComplete to reveal, with “Comment your letter”. No numbers. */
export const ThinkBar: React.FC<{s: StyleTokens; t: Timing; top: number; prompt?: string | null}> = ({s, t, top, prompt = 'Comment your letter'}) => {
  const frame = useCurrentFrame();
  const shown = enter(frame, t.infoComplete, 0.4) * exit(frame, t.reveal - 0.1, 0.25);
  const left = 1 - progress(frame, t.infoComplete, t.reveal);
  if (shown <= 0) return null;
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, width: W, top, opacity: shown}}>
      <div style={{height: 10, background: s.line, overflow: 'hidden'}}>
        <div style={{height: '100%', width: `${left * 100}%`, background: s.accent}} />
      </div>
      {prompt && <div style={{marginTop: 16, fontFamily: s.fontBody, fontSize: 32, fontWeight: 700, color: s.muted, letterSpacing: '0.04em'}}>
        {prompt}
      </div>}
    </div>
  );
};

/** Explanation text from t.explain until the closing card. */
export const Explanation: React.FC<{s: StyleTokens; t: Timing; text: string; top: number; fontSize?: number; style?: React.CSSProperties}> = ({s, t, text, top, fontSize = 38, style}) => {
  const frame = useCurrentFrame();
  const o = enter(frame, t.explain, 0.5) * exit(frame, t.cta - 0.3, 0.3);
  return (
    <div style={{position: 'absolute', left: SAFE_RECT.x0, width: W, top, opacity: o, transform: `translateY(${(1 - enter(frame, t.explain, 0.5)) * 24}px)`,
      fontFamily: s.fontBody, fontSize, lineHeight: 1.3, color: s.fg, fontWeight: 500, ...style}}>
      {text}
    </div>
  );
};

/** Closing invitation: game name, “Play a new puzzle”, scalargame.com. Covers the frame from t.cta. */
export const EndCard: React.FC<{s: StyleTokens; t: Timing; background?: string}> = ({s, t, background}) => {
  const frame = useCurrentFrame();
  if (frame < f(t.cta) - 1) return null;
  const a = enter(frame, t.cta, 0.45);
  const b = enter(frame, t.cta + 0.25, 0.45);
  return (
    <AbsoluteFill style={{background: background ?? s.bg, opacity: a, alignItems: 'center', justifyContent: 'center'}}>
      <div style={{textAlign: 'center', transform: `translateY(${(1 - b) * 30}px)`}}>
        <div style={{fontFamily: s.fontBody, fontSize: 30, fontWeight: 700, letterSpacing: '0.18em', color: s.muted, textTransform: 'uppercase'}}>
          Scalargame · {GAME_NAME[s.game]}
        </div>
        <div style={{fontFamily: s.fontDisplay, fontSize: 92, fontWeight: 900, color: s.fg, marginTop: 36, lineHeight: 1}}>Play a new puzzle</div>
        <div style={{fontFamily: s.fontNumber, fontSize: 56, fontWeight: 700, color: s.accent, marginTop: 34, opacity: b}}>scalargame.com</div>
      </div>
    </AbsoluteFill>
  );
};

/** Review-only overlay of the safe rectangle. */
export const SafeArea: React.FC = () => (
  <AbsoluteFill style={{pointerEvents: 'none'}}>
    <div style={{position: 'absolute', left: SAFE_RECT.x0, top: SAFE_RECT.y0, width: W, height: SAFE_RECT.y1 - SAFE_RECT.y0,
      outline: '3px dashed rgba(255,0,80,.8)'}} />
  </AbsoluteFill>
);
