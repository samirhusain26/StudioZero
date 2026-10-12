// Continuum · head-to-head (continuum-poster-1). Hook + question from frame 0; two stacked A/B cards at t.choicesIn with
// identical hatched empty tracks (no lengths, no order cues). At t.reveal both bars grow together from ONE labelled zero
// line on ONE linear scale (0 → nice round max), values count up to their exact text, then the winner turns pink.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import {BrandLabel, EndCard, Explanation, ThinkBar} from '../../kit/ui';
import {SAFE_RECT, f} from '../../timing';
import {easeOut, enter, exit, pop} from '../../kit/motion';
import {HATCH} from '../../styles/continuum-poster-1';
import {Hatch, InsetRing} from '../../kit/paint';
import {Backdrop, Check, SAFE_W, SourceLine, countText, niceCeil, scaleLabel} from './shared';

const X0 = SAFE_RECT.x0;
const HEADER_BOTTOM = 584;      // hook / rule / question block ends here (≤ 3 hook+question lines start ≥ y 318)
const PANEL_TOP = [616, 892];
const PANEL_H = 252;
const KEY = 76;
const ZERO_X = 212;           // shared zero line (between the key box and the names)
const TRACK_W = 660;          // pixels for the scale maximum
const BAR_DY = 118, BAR_H = 54, VALUE_DY = 182;
const AXIS_Y = 1160;
const LOWER_TOP = 1246;       // think bar, then explanation
const SOURCE_TOP = 1440;
const GROW = 1.3;             // bar growth (s)
const MARK = 1.45;            // winner marked this long after the reveal

const Component: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q;
  const choices = q.choices.slice(0, 2);
  const values = choices.map((c) => q.values?.find((v) => v.id === c.id) ?? q.values?.find((v) => v.label === c.label));
  const max = Math.max(...values.map((v) => v?.value ?? 0));
  const scaleMax = niceCeil(max);
  const px = (v: number) => (TRACK_W * v) / scaleMax;

  const out = exit(frame, t.cta - 0.3, 0.3);
  const hidden = 1 - enter(frame, t.reveal - 0.35, 0.3);              // hatch + “?” clear just before the downbeat
  const grow = enter(frame, t.reveal, GROW, easeOut);                    // one progress for both bars → proportional at every frame
  const axis = enter(frame, t.reveal, 0.35);
  const mark = enter(frame, t.reveal + MARK, 0.35);
  const ruleIn = enter(frame, 0, 0.6);

  return (
    <AbsoluteFill>
      <Backdrop s={s} />
      <BrandLabel s={s} t={t} />

      <div style={{opacity: out}}>
        {/* Hook + question: on screen from frame 0; the block sits on the cards so a one-line hook stays tied to its question */}
        <div style={{position: 'absolute', left: X0, width: SAFE_W, bottom: 1920 - HEADER_BOTTOM, display: 'flex', flexDirection: 'column'}}>
          <div style={{fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 86, lineHeight: 0.98, letterSpacing: '-0.02em', color: s.fg}}>
            {q.hook}
          </div>
          <div style={{marginTop: 22, width: 150 * (0.35 + 0.65 * ruleIn), height: 12, background: s.accent}} />
          <div style={{marginTop: 22, fontFamily: s.fontBody, fontWeight: 700, fontSize: 44, lineHeight: 1.15, color: s.fg}}>
            {q.question}
          </div>
        </div>

        {/* A/B cards */}
        {choices.map((c, i) => {
          const v = values[i];
          const top = PANEL_TOP[i];
          const p = pop(frame, t.choicesIn + i * 0.15);
          const isWin = c.key === q.answerKey;
          const w = mark * (isWin ? 1 : 0);
          const l = mark * (isWin ? 0 : 1);
          const barW = v ? px(v.value) * grow : 0;
          return (
            <div key={c.key} style={{position: 'absolute', left: X0, top, width: SAFE_W, height: PANEL_H, opacity: Math.min(1, p),
              transform: `translateY(${(1 - Math.min(1, p)) * 50}px)`}}>
              <div style={{position: 'absolute', inset: 0, background: s.card, borderTop: `6px solid ${s.fg}`}}>
                <InsetRing width={6 * w} color={s.accent} />
              </div>
              {/* key box */}
              <div style={{position: 'absolute', left: 24, top: 28, width: KEY, height: KEY, background: s.fg, color: s.bg,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: s.fontNumber, fontWeight: 700, fontSize: 54}}>
                <div style={{position: 'absolute', inset: 0, background: s.accent, opacity: w}} />
                <div style={{position: 'absolute', inset: 0, background: s.bad, opacity: l}} />
                <span style={{position: 'relative', color: w > 0.5 || l > 0.5 ? s.fg : s.bg}}>{c.key}</span>
              </div>
              {/* name */}
              <div style={{position: 'absolute', left: ZERO_X - X0 + 16, top: 24, right: 100, fontFamily: s.fontDisplay, fontWeight: 900,
                fontSize: 80, lineHeight: '84px', letterSpacing: '-0.015em', color: s.fg, whiteSpace: 'nowrap'}}>
                {c.label}
              </div>
              {/* winner check */}
              {w > 0 && <div style={{position: 'absolute', right: 46, top: 26, opacity: Math.min(1, w * 2)}}>
                <Check size={72} s={s} scale={0.6 + 0.4 * pop(frame, t.reveal + MARK)} />
              </div>}
              {/* empty, identical track before the reveal */}
              <div style={{position: 'absolute', left: ZERO_X - X0, top: BAR_DY, width: TRACK_W, height: BAR_H, opacity: hidden,
                outline: `2px dashed ${s.muted}`, outlineOffset: -2}}>
                <Hatch id={`h2h-hatch-${c.key}`} width={TRACK_W} height={BAR_H} color={HATCH} on={10} period={22} />
              </div>
              {/* bar */}
              <div style={{position: 'absolute', left: ZERO_X - X0, top: BAR_DY, width: barW, height: BAR_H, background: s.fg}}>
                <div style={{position: 'absolute', inset: 0, background: s.accent, opacity: w}} />
                <div style={{position: 'absolute', inset: 0, background: s.bad, opacity: l}} />
              </div>
              {/* value */}
              <div style={{position: 'absolute', left: ZERO_X - X0 + 16, top: VALUE_DY, fontFamily: s.fontNumber, fontWeight: 700,
                fontSize: 52, lineHeight: '56px', color: s.fg, whiteSpace: 'nowrap'}}>
                {frame < f(t.reveal) ? <span style={{color: s.muted, opacity: hidden}}>?</span> : countText(v?.text ?? '', grow)}
              </div>
            </div>
          );
        })}

        {/* shared zero line + one labelled linear scale (appear with the reveal) */}
        <div style={{opacity: axis}}>
          <div style={{position: 'absolute', left: ZERO_X - 2, top: PANEL_TOP[0] + BAR_DY - 14, width: 4,
            height: AXIS_Y - (PANEL_TOP[0] + BAR_DY - 14) + 14, background: s.fg}} />
          <div style={{position: 'absolute', left: ZERO_X + TRACK_W - 1, top: PANEL_TOP[0] + BAR_DY - 14, width: 0,
            height: AXIS_Y - (PANEL_TOP[0] + BAR_DY - 14), borderLeft: `2px dashed ${s.muted}`}} />
          <div style={{position: 'absolute', left: ZERO_X, top: AXIS_Y, width: TRACK_W, height: 3, background: s.fg}} />
          <div style={{position: 'absolute', left: ZERO_X + TRACK_W - 2, top: AXIS_Y, width: 3, height: 14, background: s.fg}} />
          <div style={{position: 'absolute', left: ZERO_X - 40, width: 80, top: AXIS_Y + 18, textAlign: 'center', fontFamily: s.fontNumber,
            fontWeight: 700, fontSize: 32, color: s.fg}}>0</div>
          <div style={{position: 'absolute', right: 1080 - (ZERO_X + TRACK_W) - 2, top: AXIS_Y + 18, fontFamily: s.fontNumber,
            fontWeight: 700, fontSize: 32, color: s.fg, whiteSpace: 'nowrap'}}>{scaleLabel(scaleMax, q.metric?.id)}</div>
        </div>
      </div>

      <ThinkBar s={s} t={t} top={LOWER_TOP} />
      <Explanation s={s} t={t} text={q.explanation} top={LOWER_TOP - 8} fontSize={40}
        style={{fontWeight: 600, borderLeft: `8px solid ${s.accent}`, paddingLeft: 22, width: SAFE_W - 30}} />
      <SourceLine s={s} t={t} q={q} top={SOURCE_TOP} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};


export const HeadToHead: Template = {
  Component,
  extraCues: ({t}) => [{at: t.reveal + MARK, name: 'ding', volume: 0.45}],
};
