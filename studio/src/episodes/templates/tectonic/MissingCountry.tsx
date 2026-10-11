// Tectonic · missing-country. A regional map with one country removed: neighbors drift in around a dashed gap,
// the answer piece drops into the gap with a spring at the reveal, then the camera pulls back for context.
import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, interpolateColors, useCurrentFrame} from 'remotion';
import type {GeoCountry, Question} from '../../types';
import type {Template, TemplateProps} from '../types';
import {f} from '../../timing';
import {BrandLabel, Choices, EndCard, ThinkBar} from '../../kit/ui';
import {easeInOut, enter, exit, mix, pop, progress} from '../../kit/motion';
import {pixelBox, spanFor} from '../../kit/geo';
import {LAND, OCEAN} from '../../styles/tectonic-ocean-1';
import {FacetPatternDef, Header, MapLabel, MapOcean, OceanBackground} from './parts';
import {
  boxCenter, enclosedBy, layoutLabels, radiusOf, mainBox, maxSpanInside, projectRings, projector, toD, viewBounds, visibleAnchor,
  type Box, type Pt,
} from './geoKit';

const BOX: Box = {x: 90, y: 540, w: 810, h: 570};
const PULL = 2.2;          // camera pull-back: span multiplier after the reveal
const LABEL = 36;          // neighbor label size
const ANSWER = 60;         // answer label size
const DRIFT = 90;          // px neighbors travel while drifting in
const FEATHER = 45;        // haze feather (base px); the clear hole is inset so haze is full at the window edge

type Q = Question & {geoWindow?: number[]};

function buildScene(q: Q, geo: GeoCountry[]) {
  const g = new Map(geo.map((c) => [c.id, c]));
  const geom = q.geometry!;
  const target = g.get(geom.target)!;
  const tb = mainBox(target);
  const center = boxCenter(tb) as [number, number];
  const win = q.geoWindow ?? geom.frameBbox ?? null;
  const need = spanFor(tb, BOX.w, BOX.h, 1.45);
  // As much context as the generator's window guarantees (every country in it is in ep.geo), never less than the target.
  const span = Math.max(need, win ? maxSpanInside(center, BOX, win) : need * 1.6);
  const view = {center, span, box: BOX};
  const proj = projector(view);
  const bounds = viewBounds(view, PULL * 1.08);
  const neighborIds = geom.neighbors.filter((id) => g.has(id));
  const countries = geo.map((c) => ({c, d: toD(projectRings(c, proj, bounds)),
    role: c.id === geom.target ? 'target' : neighborIds.includes(c.id) ? 'neighbor' : 'context'}));
  // Context enclaves inside a neighbor (no hole in the source rings) are redrawn above that neighbor.
  const enclaves = countries.filter((x) => x.role === 'context').flatMap((x) =>
    neighborIds.filter((id) => enclosedBy(x.c, g.get(id)!)).map((host) => ({...x, host})));
  const inner = {x: BOX.x + 14, y: BOX.y + 14, w: BOX.w - 28, h: BOX.h - 28};
  const tAnchor = visibleAnchor(projectRings(target, proj, bounds), inner) ?? {x: BOX.x + BOX.w / 2, y: BOX.y + BOX.h / 2, r: 40};
  const from: Pt = [tAnchor.x, tAnchor.y];
  const anchors = neighborIds.map((id) => {
    const a = visibleAnchor(projectRings(g.get(id)!, proj, bounds), inner) ?? {x: from[0], y: from[1] - 120, r: 0};
    const dx = a.x - from[0], dy = a.y - from[1], L = Math.hypot(dx, dy) || 1;
    return {id, a, dir: [dx / L, dy / L] as Pt, angle: (Math.atan2(dx, -dy) + 2 * Math.PI) % (2 * Math.PI)};
  });
  // Deterministic groups: clockwise from north, split into ≤ 3 contiguous groups.
  const sorted = [...anchors].sort((a, b) => a.angle - b.angle || a.id.localeCompare(b.id));
  const nGroups = Math.min(3, sorted.length);
  const groupOf: Record<string, number> = {};
  let k = 0;
  for (let gi = 0; gi < nGroups; gi++) {
    const size = Math.floor(sorted.length / nGroups) + (gi < sorted.length % nGroups ? 1 : 0);
    for (let j = 0; j < size; j++) groupOf[sorted[k++].id] = gi;
  }
  // The gap (target's on-screen box, slightly shrunk) is an obstacle: neighbor labels never sit on the question.
  const tb2 = pixelBox(target, proj);
  const gap = {x: tb2.cx, y: tb2.cy, w: Math.min(tb2.w, BOX.w) * 0.8, h: Math.min(tb2.h, BOX.h) * 0.8};
  const labels = layoutLabels(
    anchors.map(({id, a}) => ({id, text: g.get(id)!.label, ax: a.x, ay: a.y, r: a.r, size: LABEL})),
    inner, [gap], from,
  );
  // ep.geo only guarantees *all* land inside the generator window. After the pull-back, open water outside it is veiled
  // with haze (land we do have stays crisp on top), so a country absent from ep.geo never reads as sea.
  let fog = '';
  if (win) {
    const inset = (FEATHER * 1.6) / (radiusOf(view) * (Math.PI / 180));
    const k = Math.cos(center[1] * (Math.PI / 180));
    const w0 = [win[0] + inset / k, win[1] + inset, win[2] - inset / k, win[3] - inset];
    const win2 = w0[0] < w0[2] && w0[1] < w0[3] ? w0 : win;
    const pts: Pt[] = [];
    const N = 24;
    const w = win2;
    for (let i = 0; i <= N; i++) pts.push([w[0] + ((w[2] - w[0]) * i) / N, w[3]]);
    for (let i = 0; i <= N; i++) pts.push([w[2], w[3] - ((w[3] - w[1]) * i) / N]);
    for (let i = 0; i <= N; i++) pts.push([w[2] - ((w[2] - w[0]) * i) / N, w[1]]);
    for (let i = 0; i <= N; i++) pts.push([w[0], w[1] + ((w[3] - w[1]) * i) / N]);
    fog = 'M' + pts.map((p) => proj(p)).map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z';
  }
  // With fewer than 3 neighbor groups, the next item beat brings in the (unlabelled) context land.
  return {target, countries, enclaves, tAnchor, anchors, groupOf, labels, fog, contextBeat: nGroups < 3 ? nGroups : -1};
}

const Component: React.FC<TemplateProps> = ({ep, s, t}) => {
  const frame = useCurrentFrame();
  const q = ep.q as Q;
  const sc = useMemo(() => buildScene(q, ep.geo), [q, ep.geo]);
  const R = t.reveal;
  const cx = BOX.x + BOX.w / 2, cy = BOX.y + BOX.h / 2;

  const mapIn = enter(frame, 0, 0.4) * exit(frame, t.cta - 0.3, 0.3);
  const contextIn = sc.contextBeat < 0 ? 1 : enter(frame, t.items[sc.contextBeat] ?? 0, 0.5);
  const groupIn = (gi: number) => enter(frame, t.items[gi] ?? 0, 0.5);

  // Camera pull-back (same centre): projection span × PULL, eased.
  const pb = interpolate(frame, [f(R + 1.5), f(R + 3.0)], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeInOut});
  const zoom = 1 / mix(1, PULL, pb);
  const cam = `translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`;
  const camPt = (x: number, y: number): Pt => [cx + (x - cx) * zoom, cy + (y - cy) * zoom];

  // Gap: dashed outline pulsing softly until the piece lands.
  const sec = frame / 30;
  const pulse = 0.5 + 0.5 * Math.cos((2 * Math.PI * sec) / 1.6);
  const gapOutline = exit(frame, R + 0.12, 0.25);
  const antic = progress(frame, R - 0.6, R); // gap brightens just before the drop
  const pulseNow = mix(pulse, 1, antic);
  // Anticipation: the piece's shadow gathers over the gap, then the piece drops with a spring.
  const shadowPre = progress(frame, R - 0.6, R);
  const p = pop(frame, R, {damping: 11, stiffness: 150, mass: 0.9});
  const pieceO = Math.min(1, p * 3);
  const piece = `translate(${sc.tAnchor.x} ${sc.tAnchor.y - 190 * (1 - p)}) scale(${1.16 - 0.16 * p}) translate(${-sc.tAnchor.x} ${-sc.tAnchor.y})`;
  const answerIn = pop(frame, R + 0.3, {damping: 13, stiffness: 170, mass: 0.8});
  const neighborLabelsOut = 1 - progress(frame, R + 1.5, R + 2.1);
  const [ax, ay] = camPt(sc.tAnchor.x, sc.tAnchor.y);
  const ansW = q.answer.length * ANSWER * 0.6;
  const ansX = Math.max(BOX.x + ansW / 2 + 16, Math.min(BOX.x + BOX.w - ansW / 2 - 16, ax));
  const fogIn = enter(frame, R + 1.5, 0.9);

  return (
    <AbsoluteFill>
      <OceanBackground />
      <BrandLabel s={s} t={t} />
      <Header s={s} t={t} hook={q.hook} question={q.question} explanation={q.explanation} />
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}}>
        <defs>
          <clipPath id="mc-clip"><rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={30} /></clipPath>
          <FacetPatternDef id="mc-facets" />
          <filter id="mc-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation={14} /></filter>
          <filter id="mc-fogedge" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation={FEATHER} /></filter>
          <mask id="mc-hazemask" maskUnits="userSpaceOnUse" x={-3000} y={-3000} width={8000} height={8000}>
            <rect x={-3000} y={-3000} width={8000} height={8000} fill="white" />
            {sc.fog && <path d={sc.fog} fill="black" filter="url(#mc-fogedge)" />}
          </mask>
        </defs>
        <g opacity={mapIn}>
          <g clipPath="url(#mc-clip)">
            <MapOcean box={BOX} id="mc" />
            <g transform={cam}>
              {sc.fog && <rect x={-3000} y={-3000} width={8000} height={8000} fill={OCEAN.haze} opacity={fogIn} mask="url(#mc-hazemask)" />}
              {sc.countries.filter((c) => c.role === 'context').map(({c, d}) => (
                <path key={c.id} d={d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} vectorEffect="non-scaling-stroke"
                  fillRule="evenodd" strokeLinejoin="round" opacity={contextIn} />
              ))}
              {sc.countries.filter((c) => c.role === 'target').map(({c, d}) => (
                <g key={c.id}>
                  <path d={d} fill={interpolateColors(antic, [0, 1], [OCEAN.gap, OCEAN.gapLit])} fillRule="evenodd" opacity={0.9} />
                  <path d={d} fill="none" stroke={s.fg} strokeWidth={5 + 1.5 * pulseNow + 1.5 * antic} strokeDasharray="16 12" strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke" opacity={gapOutline * (0.7 + 0.3 * pulseNow)} />
                </g>
              ))}
              {sc.anchors.map(({id, dir}) => {
                const gi = sc.groupOf[id], e = groupIn(gi);
                const c = sc.countries.find((x) => x.c.id === id)!;
                return (
                  <g key={id} opacity={e} transform={`translate(${dir[0] * DRIFT * (1 - e)} ${dir[1] * DRIFT * (1 - e)})`}>
                    <path d={c.d} fill={interpolateColors(pb, [0, 1], [LAND.neighbor, LAND.pulled])} stroke={LAND.neighborEdge} strokeWidth={2.5} vectorEffect="non-scaling-stroke"
                      fillRule="evenodd" strokeLinejoin="round" />
                    <path d={c.d} fill="url(#mc-facets)" fillRule="evenodd" opacity={0.4 * (1 - pb)} />
                    {sc.enclaves.filter((x) => x.host === id).map((x) => (
                      <path key={x.c.id} d={x.d} fill={LAND.context} stroke={LAND.contextEdge} strokeWidth={2} vectorEffect="non-scaling-stroke"
                        fillRule="evenodd" strokeLinejoin="round" opacity={contextIn} />
                    ))}
                  </g>
                );
              })}
              {sc.countries.filter((c) => c.role === 'target').map(({c, d}) => (
                <g key={`piece-${c.id}`}>
                  <path d={d} fill="#000" fillRule="evenodd" filter="url(#mc-soft)"
                    opacity={0.55 * (frame < f(R) ? shadowPre : Math.max(0, 1 - (p - 0.0) * 0.5))}
                    transform={`translate(0 ${frame < f(R) ? 10 : 10 + 6 * (1 - p)})`} />
                  {frame >= f(R) && <g transform={piece} opacity={pieceO}>
                    <path d={d} fill={LAND.answer} stroke={LAND.answerEdge} strokeWidth={2.5} vectorEffect="non-scaling-stroke"
                      fillRule="evenodd" strokeLinejoin="round" />
                    <path d={d} fill="url(#mc-facets)" fillRule="evenodd" opacity={0.7} />
                  </g>}
                </g>
              ))}
            </g>
          </g>
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={30} fill="none" stroke={OCEAN.cardBorder} strokeWidth={2} />
          {sc.labels.map((l) => {
            const e = groupIn(sc.groupOf[l.id]);
            const a = sc.anchors.find((x) => x.id === l.id)!;
            const off = DRIFT * (1 - e);
            const [lx, ly] = camPt(l.x + a.dir[0] * off, l.y + a.dir[1] * off);
            const [lax, lay] = camPt(l.ax + a.dir[0] * off, l.ay + a.dir[1] * off);
            const hit = Math.abs(l.x - ansX) < (l.w + ansW) / 2 && Math.abs(l.y - sc.tAnchor.y) < (l.h + ANSWER * 1.2) / 2;
            const yield_ = hit ? 1 - Math.min(1, answerIn) : 1;
            return <MapLabel key={l.id} s={s} l={{...l, x: lx, y: ly, ax: lax, ay: lay}} opacity={e * neighborLabelsOut * yield_} />;
          })}
          {answerIn > 0 && (
            <g transform={`translate(${ansX} ${ay}) scale(${0.6 + 0.4 * answerIn}) translate(${-ansX} ${-ay})`}>
              <MapLabel s={s} weight={900} opacity={Math.min(1, answerIn * 1.5)}
                l={{id: 'answer', text: q.answer, ax: ansX, ay, x: ansX, y: ay, r: 0, size: ANSWER, w: ansW, h: ANSWER, leader: false}} />
            </g>
          )}
        </g>
      </svg>
      <Choices s={s} t={t} choices={q.choices} answerKey={q.answerKey} top={1136} layout="column" fontSize={40}
        answerStyle={{borderColor: s.accent, background: '#3A2914'}} />
      <ThinkBar s={s} t={t} top={1452} />
      <EndCard s={s} t={t} />
    </AbsoluteFill>
  );
};

export const MissingCountry: Template = {
  Component,
  extraCues: ({t}) => [{at: t.reveal + 1.5, name: 'swoosh', volume: 0.25}],
};
