// Scalar · candidate elimination (field notebook). Three candidate cards (the A/B/C choices) each carry a three-box
// checklist; three clue index cards are dealt below. From the reveal the clues are applied one per second: failing
// candidates are crossed and struck through, passing ones ticked. The survivor gets the green stamp; then a note card
// with the explanation is dealt onto the pile.
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Template, TemplateProps} from '../types';
import {BrandLabel, EndCard, ThinkBar} from '../../kit/ui';
import {easeInOut, enter, exit, mix} from '../../kit/motion';
import {SAFE_RECT, f} from '../../timing';
import {NB} from '../../styles/scalar-notebook-1';
import {ClueCard, Cross, Desk, Stamp, Tick, cardStyle, deal, Ruling} from './notebook';

const X0 = SAFE_RECT.x0, W = SAFE_RECT.x1 - SAFE_RECT.x0;
const ROW_TOP = 616, ROW_H = 92, ROW_GAP = 14;
const CLUE_TOP = 952, CLUE_H = 156, CLUE_GAP = 16;          // 952–1108, 1124–1280, 1296–1452
const THINK_TOP = 1466;
const ROW_TILTS = [-0.5, 0.4, -0.3], CLUE_TILTS = [0.8, -0.9, 0.5];
const BOX = 54;

type Mark = {at: number; kind: 'tick' | 'cross'};

/** Per candidate: the mark in each clue box (or null) and when it was eliminated. Clue i is applied at reveal + i. */
function applyClues(ids: string[], answerId: string | undefined, elim: string[][], n: number, reveal: number) {
  const out = new Map<string, {marks: (Mark | null)[]; outAt: number | null; outBy: number | null}>();
  ids.forEach((id) => out.set(id, {marks: Array(n).fill(null), outAt: null, outBy: null}));
  for (let i = 0; i < n; i++) {
    const at = reveal + i;
    const hit = elim[i] ?? [];
    for (const id of ids) {
      const st = out.get(id)!;
      if (st.outAt !== null) continue;
      if (hit.includes(id)) { st.marks[i] = {at, kind: 'cross'}; st.outAt = at; st.outBy = i; }
      else st.marks[i] = {at: at + (hit.length ? 0.15 : 0), kind: 'tick'};
    }
  }
  void answerId;
  return out;
}

const Component: React.FC<TemplateProps> = ({ep, s, t}) => {
  const q = ep.q;
  const frame = useCurrentFrame();
  const clues = q.clues ?? [];
  const n = clues.length;
  const out = exit(frame, t.cta - 0.3, 0.3);
  const elim = ((q.evidence.checks as {eliminatedPerClue?: string[][]}).eliminatedPerClue) ?? [];
  const ids = q.choices.map((c) => c.id ?? c.key);
  const answerId = q.choices.find((c) => c.key === q.answerKey)?.id ?? q.answerKey;
  const status = applyClues(ids, answerId, elim, n, t.reveal);
  const stampAt = t.reveal + n - 1 + 0.5;

  const inhale = enter(frame, t.reveal - 0.45, 0.4, easeInOut) * (1 - enter(frame, t.reveal, 0.15));
  const ghost = 1 - 0.86 * enter(frame, stampAt - 0.1, 0.3);         // clue text steps back for the stamp
  const under = 1 - enter(frame, stampAt - 0.1, 0.3);                // the stamped clue (1) clears fully: a two-line clue would show around the stamp
  const note = deal(frame, t.explain, -0.7, -1, 0.5);

  const rowY = (i: number) => ROW_TOP + i * (ROW_H + ROW_GAP);
  const clueY = (i: number) => CLUE_TOP + i * (CLUE_H + CLUE_GAP);

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Desk s={s} />
      <BrandLabel s={s} t={t} />

      <div style={{position: 'absolute', left: X0, top: 318, width: W, opacity: out}}>
        <div style={{fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 66, lineHeight: 1.0, color: s.fg, letterSpacing: '-0.01em'}}>{q.hook}</div>
        <div style={{marginTop: 20, fontFamily: s.fontDisplay, fontWeight: 600, fontStyle: 'italic', fontSize: 56, lineHeight: 1.04, color: NB.tealInk}}>
          {q.question}
        </div>
      </div>

      {/* Candidate cards = the A/B/C choices. Identical styling until the reveal. */}
      {q.choices.map((c, i) => {
        const d = deal(frame, t.choicesIn + i * 0.12, ROW_TILTS[i % 3], 1, 0.42);
        if (!d) return null;
        const st = status.get(ids[i])!;
        const struck = st.outAt !== null ? enter(frame, st.outAt + 0.05, 0.3) : 0;
        const isAns = c.key === q.answerKey;
        const win = isAns ? enter(frame, stampAt, 0.25) : 0;
        return (
          <div key={c.key} style={{position: 'absolute', left: X0, top: rowY(i), width: W, height: ROW_H, transform: d.transform, opacity: out,
            ...cardStyle(s, d.lift, win > 0.5 ? NB.stampInk : s.line), borderColor: win > 0.5 ? NB.stampInk : s.line,
            backgroundColor: win > 0 ? NB.goodWash : s.card, display: 'flex', alignItems: 'stretch'}}>
            <div style={{width: 76, flex: '0 0 76px', borderRight: `3px solid ${s.line}`, background: s.accent, display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontFamily: s.fontNumber, fontWeight: 700, fontSize: 46, color: s.fg, opacity: mix(1, 0.4, struck)}}>{c.key}</div>
            <div style={{flex: 1, position: 'relative', display: 'flex', alignItems: 'center', padding: '0 22px', minWidth: 0}}>
              <span style={{position: 'relative', fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 56, lineHeight: 1, whiteSpace: 'nowrap',
                color: struck > 0 ? `rgba(24,24,27,${mix(1, 0.4, struck)})` : s.fg}}>
                {c.label}
                <span style={{position: 'absolute', left: -8, top: '52%', height: 7, width: `calc(${struck * 100}% + 16px)`, background: NB.crossInk,
                  transform: 'rotate(-2deg)', display: struck > 0 ? 'block' : 'none'}} />
              </span>
            </div>
            {/* Checklist: one box per clue. */}
            <div style={{display: 'flex', alignItems: 'center', gap: 8, paddingRight: 16}}>
              {st.marks.map((m, k) => {
                const draw = m ? enter(frame, m.at, 0.3) : 0;
                return (
                  <div key={k} style={{position: 'relative', width: BOX, height: BOX, border: `3px solid ${s.line}`, background: s.card, boxSizing: 'border-box',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: s.fontBody, fontWeight: 700, fontSize: 30,
                    color: s.muted, opacity: m || st.outAt === null || frame < f(st.outAt) ? 1 : mix(1, 0.4, struck)}}>
                    <span style={{opacity: 1 - Math.min(1, draw * 3)}}>{k + 1}</span>
                    {m && draw > 0 && <div style={{position: 'absolute', inset: 2}}>
                      {m.kind === 'tick' ? <Tick size={44} color={NB.stampInk} draw={draw} /> : <Cross size={44} color={NB.crossInk} draw={draw} />}
                    </div>}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Clue pile; the clue being applied gets a teal frame, the others step back. */}
      <div style={{position: 'absolute', inset: 0, opacity: out, transform: `scale(${1 - 0.018 * inhale})`,
        transformOrigin: `${X0 + W / 2}px ${clueY(1) + CLUE_H / 2}px`}}>
        {clues.map((text, i) => {
          const d = deal(frame, t.items[i], CLUE_TILTS[i % 3], 1);
          if (!d) return null;
          const on = enter(frame, t.reveal + i, 0.2) * exit(frame, Math.min(t.reveal + i + 0.85, stampAt - 0.25), 0.2);
          const anyOn = frame >= f(t.reveal) && frame < f(t.reveal + n - 0.1);
          const dim = anyOn ? mix(0.45, 1, on) : 1;
          return <ClueCard key={i} s={s} n={i + 1} text={text} x={X0} y={clueY(i)} w={W} h={CLUE_H} transform={d.transform} lift={d.lift}
            focus={on} dim={dim} textFade={i === 0 ? under : ghost} />;
        })}
        <Stamp frame={frame} at={stampAt} cx={X0 + W / 2} cy={clueY(0) + CLUE_H / 2 + 6} rotate={-5} small={`FITS ALL ${n}`} big={q.answer}
          bigSize={q.answer.length > 12 ? 64 : 76} fontDisplay={s.fontDisplay} fontBody={s.fontBody} />
      </div>

      {/* Explanation note card, dealt onto the lower clues. */}
      {note && (
        <div style={{position: 'absolute', left: X0, top: clueY(1) - 6, width: W, height: clueY(2) + CLUE_H - clueY(1) + 12, transform: note.transform,
          opacity: out, ...cardStyle(s, note.lift), backgroundColor: s.card, padding: '40px 32px 24px',
          fontFamily: s.fontDisplay, fontWeight: 600, fontSize: 40, lineHeight: 1.22, color: s.fg, display: 'flex', alignItems: 'center'}}>
          <Ruling width={W - 6} height={clueY(2) + CLUE_H - clueY(1) + 12 - 6} top={18} />
          <span style={{position: 'relative'}}>{q.explanation}</span>
        </div>
      )}

      <ThinkBar s={s} t={t} top={THINK_TOP} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const CandidateElimination: Template = {
  Component,
  // The strike-outs after the first (which lands with the standard reveal stamp), and the survivor's stamp.
  extraCues: ({ep, t}) => {
    const n = ep.q.clues?.length ?? 3;
    return [
      ...Array.from({length: n - 1}, (_, i) => ({at: t.reveal + i + 1, name: 'thock' as const, volume: 0.6})),
      {at: t.reveal + n - 1 + 0.5, name: 'stamp' as const, volume: 0.8},
    ];
  },
};
