// Tectonic · neighbor-clues. Clue cards (name + silhouette) for every land neighbor in a neutral stack; at the
// reveal the cards fly to their true places on a real map, the target drops in orange and its shared borders light up.
import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import type {GeoCountry, Question} from '../../types';
import type {Template, TemplateProps} from '../types';
import {SAFE_RECT, f} from '../../timing';
import {BrandLabel, Choices, EndCard, ThinkBar} from '../../kit/ui';
import {easeInOut, enter, exit, mix, pop, progress} from '../../kit/motion';
import {orthographic, pixelBox, spanFor} from '../../kit/geo';
import {LAND, OCEAN} from '../../styles/tectonic-ocean-1';
import {FacetPatternDef, Header, MapLabel, MapOcean, OceanBackground} from './parts';
import {
  boxCenter, enclosedBy, largestRing, layoutLabels, mainBox, maxSpanInside, projectRings, projector, ringBox, sharedBorders, textWidth,
  toD, viewBounds, visibleAnchor, type Box, type Pt,
} from './geoKit';

const BOX: Box = {x: 90, y: 492, w: 810, h: 600};   // card stack area before the reveal, map card after it
const GAP = 18;
const SIL = {w: 230, h: 136};                          // silhouette slot inside a card
const NAME = 50;
const LABEL = 36;
const ANSWER = 60;
const RAD = Math.PI / 180;

type Q = Question & {geoWindow?: number[]};

/** Great-circle distance in degrees. */
function arc(a: number[], b: number[]) {
  const s = Math.sin(a[1] * RAD) * Math.sin(b[1] * RAD) + Math.cos(a[1] * RAD) * Math.cos(b[1] * RAD) * Math.cos((a[0] - b[0]) * RAD);
  return Math.acos(Math.max(-1, Math.min(1, s))) / RAD;
}

/** A country's own rings near its main landmass, projected alone (orthographic centred on itself), as a fitted path.
 *  `holes` are enclaves it surrounds (cut out with evenodd; the source rings have no hole for them). */
function silhouette(c: GeoCountry, holes: GeoCountry[] = []) {
  const center = boxCenter(mainBox(c)) as [number, number];
  const rings = [...c.rings, ...holes.map(largestRing)].filter((r) => arc(boxCenter([...r.reduce((m, p) => [Math.min(m[0], p[0]), Math.min(m[1], p[1]), Math.max(m[2], p[0]), Math.max(m[3], p[1])], [Infinity, Infinity, -Infinity, -Infinity])]), center) < 30);
  const proj = orthographic(center, 10, 1000, 1000);
  const pr = rings.map((r) => r.map(proj).map((p) => [p[0], p[1]] as Pt));
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const r of pr) for (const [x, y] of r) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const k = Math.min(SIL.w / (x1 - x0), SIL.h / (y1 - y0));
  const ox = (SIL.w - (x1 - x0) * k) / 2, oy = (SIL.h - (y1 - y0) * k) / 2;
  return toD(pr.map((r) => r.map(([x, y]) => [ox + (x - x0) * k, oy + (y - y0) * k] as Pt)));
}

/** Words → lines that fit `width` at `size` (estimated widths; Nunito 900). */
function wrap(text: string, size: number, width: number) {
  const lines: string[] = [];
  for (const w of text.split(' ')) {
    const last = lines[lines.length - 1];
    if (last && textWidth(`${last} ${w}`, size, 0.6) <= width) lines[lines.length - 1] = `${last} ${w}`; else lines.push(w);
  }
  return lines;
}

function buildScene(q: Q, geo: GeoCountry[]) {
  const g = new Map(geo.map((c) => [c.id, c]));
  const target = g.get(q.geometry!.target)!;
  const shown = (q.shown ?? []).filter((x) => g.has(x.id));
  const tb = mainBox(target);
  const center = boxCenter(tb) as [number, number];
  const need = spanFor(tb, BOX.w, BOX.h, 1.8);
  const win = q.geoWindow;
  // Stay inside the generator window (all its land is in ep.geo) unless that would crop the target itself.
  const span = win ? Math.max(spanFor(tb, BOX.w, BOX.h, 1.25), Math.min(need, maxSpanInside(center, BOX, win))) : need;
  const view = {center, span, box: BOX};
  const proj = projector(view);
  const bounds = viewBounds(view, 1.05);
  const shownIds = shown.map((x) => x.id);
  const countries = geo.map((c) => ({c, d: toD(projectRings(c, proj, bounds)),
    role: c.id === target.id ? 'target' : shownIds.includes(c.id) ? 'neighbor' : 'context'})).filter((x) => x.d);
  // Enclaves (Lesotho in South Africa; San Marino and Vatican City in Italy) have no hole in their host's rings, so a host
  // drawn later would hide them: each visible enclave is redrawn right after its host (target, neighbor or context).
  const inside = (a: number[], b: number[]) => a[0] >= b[0] && a[1] >= b[1] && a[2] <= b[2] && a[3] <= b[3];
  const within = (c: GeoCountry, host: GeoCountry) => c !== host && inside(ringBox(largestRing(c)), ringBox(largestRing(host))) && enclosedBy(c, host);
  const enclaves = countries.filter((x) => x.role !== 'target').flatMap((x) => {
    const host = countries.find((h) => within(x.c, h.c));
    return host ? [{...x, host: host.c.id}] : [];
  });
  const enclavesOf = (id: string) => enclaves.filter((x) => x.host === id);
  // Label anchors and silhouettes treat a host's enclaves as holes (evenodd), so a label never lands on an enclave.
  const anchorRings = (c: GeoCountry) => [...projectRings(c, proj, bounds), ...enclavesOf(c.id).flatMap((x) => projectRings(x.c, proj, bounds))];
  const inner = {x: BOX.x + 14, y: BOX.y + 14, w: BOX.w - 28, h: BOX.h - 28};
  const tA = visibleAnchor(anchorRings(target), inner) ?? {x: BOX.x + BOX.w / 2, y: BOX.y + BOX.h / 2, r: 40};
  const ansW = textWidth(q.answer, ANSWER, 0.6);
  const ans = {x: Math.max(BOX.x + ansW / 2 + 16, Math.min(BOX.x + BOX.w - ansW / 2 - 16, tA.x)), y: tA.y, w: ansW, h: ANSWER * 1.2};
  const anchors = shown.map((x) => {
    const a = visibleAnchor(anchorRings(g.get(x.id)!), inner) ?? {x: tA.x, y: tA.y - 150, r: 0};
    return {id: x.id, text: x.label, ax: a.x, ay: a.y, r: a.r, size: LABEL};
  });
  const tp = pixelBox(target, proj);
  const body = {x: tp.cx, y: tp.cy, w: Math.min(tp.w, BOX.w) * 0.55, h: Math.min(tp.h, BOX.h) * 0.55};
  const labels = layoutLabels(anchors, inner, [ans, body], [tA.x, tA.y]);
  // An enclave's whole outline is its border with the host (the shared-vertex test cannot see it without a hole).
  const enclaveBorders = shown.map((x) => g.get(x.id)!).flatMap((n) =>
    within(n, target) ? [largestRing(n)] : within(target, n) ? [largestRing(target)] : [])
    .map((r) => [...r, r[0]]);
  const borders = [...sharedBorders(target, shown.map((x) => g.get(x.id)!)), ...enclaveBorders]
    .map((line) => 'M' + line.map((p) => proj(p)).map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L')).join('');
  const n = Math.max(1, shown.length);
  const cardH = (BOX.h - 36 - GAP * (n - 1)) / n;   // leaves room for the "not to scale" note
  const cards = shown.map((x, i) => ({
    id: x.id, label: x.label, sil: silhouette(g.get(x.id)!, geo.filter((e) => within(e, g.get(x.id)!))), y: BOX.y + i * (cardH + GAP), h: cardH,
    lines: wrap(x.label, NAME, BOX.w - SIL.w - 90),
  }));
  return {target, countries, enclavesOf, tA, ans, labels, borders, cards};
}

const Component: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q as Q;
  const sc = useMemo(() => buildScene(q, ep.geo), [q, ep.geo]);
  const R = t.reveal;
  const out = exit(frame, t.cta - 0.3, 0.3);

  const mapIn = enter(frame, R, 0.4);
  const fly = interpolate(frame, [f(R), f(R + 0.6)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeInOut});
  const gather = progress(frame, R - 0.5, R) * (1 - fly);     // anticipation: cards draw in slightly
  const neighborsIn = enter(frame, R + 0.3, 0.35);
  const labelsIn = enter(frame, R + 0.45, 0.3);
  const p = pop(frame, R + 0.6, {damping: 11, stiffness: 150, mass: 0.9});
  const piece = `translate(${sc.tA.x} ${sc.tA.y - 170 * (1 - p)}) scale(${1.16 - 0.16 * p}) translate(${-sc.tA.x} ${-sc.tA.y})`;
  const borderDraw = enter(frame, R + 1.05, 0.7, easeInOut);
  const answerIn = pop(frame, R + 0.85, {damping: 13, stiffness: 170, mass: 0.8});
  const noteO = enter(frame, t.items[0] ?? 0, 0.4) * (1 - fly);
  // One context or neighbor country on the map (neighbors turn sand-coloured as they land).
  const land = ({c, d, role}: {c: GeoCountry; d: string; role: string}, key: string) => role === 'neighbor' ? (
    <g key={key + c.id}>
      <path d={d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} fillRule="evenodd" strokeLinejoin="round" />
      <g opacity={neighborsIn}>
        <path d={d} fill={LAND.neighbor} stroke={LAND.neighborEdge} strokeWidth={2.5} fillRule="evenodd" strokeLinejoin="round" />
        <path d={d} fill="url(#nc-facets)" fillRule="evenodd" opacity={0.4} />
      </g>
    </g>
  ) : <path key={key + c.id} d={d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} fillRule="evenodd" strokeLinejoin="round" />;

  return (
    <AbsoluteFill>
      <OceanBackground />
      <BrandLabel s={s} t={t} />
      <Header s={s} t={t} hook={q.hook} question={q.question} explanation={q.explanation} />
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}} opacity={out}>
        <defs>
          <clipPath id="nc-clip"><rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={30} /></clipPath>
          <FacetPatternDef id="nc-facets" />
          <filter id="nc-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation={12} /></filter>
        </defs>
        {mapIn > 0 && <g opacity={mapIn}>
          <g clipPath="url(#nc-clip)">
            <MapOcean box={BOX} id="nc" />
            {sc.countries.filter((c) => c.role === 'context').map(({c, d}) => (
              <path key={c.id} d={d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} fillRule="evenodd" strokeLinejoin="round" />
            ))}
            {sc.countries.filter((c) => c.role === 'context').flatMap(({c}) => sc.enclavesOf(c.id)).map((x) => land(x, 'enc-'))}
            {sc.countries.filter((c) => c.role === 'neighbor').map(({c, d}) => (
              <g key={c.id}>
                <path d={d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} fillRule="evenodd" strokeLinejoin="round" />
                <g opacity={neighborsIn}>
                  <path d={d} fill={LAND.neighbor} stroke={LAND.neighborEdge} strokeWidth={2.5} fillRule="evenodd" strokeLinejoin="round" />
                  <path d={d} fill="url(#nc-facets)" fillRule="evenodd" opacity={0.4} />
                </g>
                {sc.enclavesOf(c.id).map((e) => land(e, 'enc-'))}
              </g>
            ))}
            {sc.countries.filter((c) => c.role === 'target').map(({c, d}) => (
              <g key={c.id}>
                <path d={d} fill={OCEAN.gap} fillRule="evenodd" opacity={0.9 * (1 - Math.min(1, p))} />
                <path d={d} fill="#000" fillRule="evenodd" filter="url(#nc-soft)" opacity={0.5 * Math.min(1, p)} transform="translate(0 10)" />
                {p > 0 && <g transform={piece} opacity={Math.min(1, p * 3)}>
                  <path d={d} fill={LAND.answer} stroke={LAND.answerEdge} strokeWidth={2.5} fillRule="evenodd" strokeLinejoin="round" />
                  <path d={d} fill="url(#nc-facets)" fillRule="evenodd" opacity={0.7} />
                </g>}
              </g>
            ))}
            {sc.enclavesOf(sc.target.id).map((e) => land(e, 'enc-'))}
            {sc.borders && borderDraw > 0 && <g>
              <path d={sc.borders} fill="none" stroke={OCEAN.halo} strokeWidth={11} strokeLinecap="round" strokeLinejoin="round"
                pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - borderDraw} />
              <path d={sc.borders} fill="none" stroke={LAND.border} strokeWidth={5.5} strokeLinecap="round" strokeLinejoin="round"
                pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - borderDraw} />
            </g>}
          </g>
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={30} fill="none" stroke={OCEAN.cardBorder} strokeWidth={2} />
          {sc.labels.map((l) => <MapLabel key={l.id} s={s} l={l} opacity={labelsIn} />)}
          {answerIn > 0 && (
            <g transform={`translate(${sc.ans.x} ${sc.ans.y}) scale(${0.6 + 0.4 * answerIn}) translate(${-sc.ans.x} ${-sc.ans.y})`}>
              <MapLabel s={s} weight={900} opacity={Math.min(1, answerIn * 1.5)}
                l={{id: 'answer', text: q.answer, ax: sc.ans.x, ay: sc.ans.y, x: sc.ans.x, y: sc.ans.y, r: 0, size: ANSWER, w: sc.ans.w, h: ANSWER, leader: false}} />
            </g>
          )}
        </g>}
        {/* clue cards: neutral stack in clue order; at the reveal each flies to its country's place on the map */}
        {sc.cards.map((c, i) => {
          const e = enter(frame, t.items[i] ?? t.items[t.items.length - 1] ?? 0, 0.5);
          if (e <= 0 || fly >= 1) return null;
          const l = sc.labels.find((x) => x.id === c.id)!;
          const cx0 = BOX.x + BOX.w / 2, cy0 = c.y + c.h / 2;
          const cx = mix(cx0, l.ax, fly), cy = mix(cy0, l.ay, fly);
          const sc_ = (1 - 0.03 * gather) * mix(1, 0.18, fly);
          const o = e * (1 - progress(frame, R + 0.25, R + 0.6));
          return (
            <g key={c.id} opacity={o} transform={`translate(${cx + (1 - e) * 80} ${cy}) scale(${sc_}) translate(${-BOX.w / 2} ${-c.h / 2})`}>
              <rect x={0} y={0} width={BOX.w} height={c.h} rx={24} fill={s.card} stroke={OCEAN.cardBorder} strokeWidth={2} />
              <g transform={`translate(${28} ${(c.h - SIL.h) / 2})`}>
                <path d={c.sil} fill={LAND.neighbor} stroke={LAND.neighborEdge} strokeWidth={1.5} fillRule="evenodd" strokeLinejoin="round" />
              </g>
              {c.lines.map((line, j) => (
                <text key={j} x={SIL.w + 62} y={c.h / 2 + (j - (c.lines.length - 1) / 2) * NAME * 1.08} dominantBaseline="central"
                  fontFamily={s.fontDisplay} fontWeight={900} fontSize={NAME} fill={s.fg}>{line}</text>
              ))}
            </g>
          );
        })}
        <text x={SAFE_RECT.x1} y={BOX.y + BOX.h - 8} textAnchor="end" fontFamily={s.fontBody} fontWeight={700} fontSize={30} fill={s.muted}
          opacity={noteO}>Shapes not to scale</text>
      </svg>
      <Choices s={s} t={t} choices={q.choices} answerKey={q.answerKey} top={1120} layout="column" fontSize={40}
        answerStyle={{borderColor: s.accent, background: '#3A2914'}} />
      <ThinkBar s={s} t={t} top={1436} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const NeighborClues: Template = {Component, extraCues: ({t}) => [{at: t.reveal + 0.6, name: 'thock', volume: 0.5}]};
