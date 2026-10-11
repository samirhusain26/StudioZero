// Shared Tectonic drawing parts: faceted ocean, map card, header (hook/question → explanation), map labels.
import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {StyleTokens, Timing} from '../../types';
import {SAFE_RECT} from '../../timing';
import {enter, exit} from '../../kit/motion';
import {Explanation} from '../../kit/ui';
import {OCEAN} from '../../styles/tectonic-ocean-1';
import {hash, rectEdgeToward, type Box, type LabelOut} from './geoKit';

/** Static low-poly triangle mesh: jittered grid, two triangles per cell, each a slightly different shade. */
export function facetMesh(b: Box, cell: number, seed: number) {
  const cols = Math.ceil(b.w / cell), rows = Math.ceil(b.h / cell);
  const P: [number, number][][] = [];
  for (let i = 0; i <= cols; i++) {
    P.push([]);
    for (let j = 0; j <= rows; j++) {
      const edgeX = i === 0 || i === cols, edgeY = j === 0 || j === rows;
      const jx = edgeX ? 0 : (hash(seed, i, j, 1) - 0.5) * cell * 0.7;
      const jy = edgeY ? 0 : (hash(seed, i, j, 2) - 0.5) * cell * 0.7;
      P[i].push([b.x + (i * b.w) / cols + jx, b.y + (j * b.h) / rows + jy]);
    }
  }
  const tris: {d: string; v: number}[] = [];
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
    const a = P[i][j], c = P[i + 1][j], d = P[i + 1][j + 1], e = P[i][j + 1];
    const flip = hash(seed, i, j, 3) > 0.5;
    const t1 = flip ? [a, c, d] : [a, c, e], t2 = flip ? [a, d, e] : [c, d, e];
    for (const [k, t] of [t1, t2].entries()) {
      tris.push({d: 'M' + t.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z', v: hash(seed, i, j, 4 + k)});
    }
  }
  return tris;
}

/** Full-frame deep ocean: vertical depth gradient + faint static facets. */
export const OceanBackground: React.FC = () => {
  const tris = useMemo(() => facetMesh({x: 0, y: 0, w: 1080, h: 1920}, 150, 7), []);
  return (
    <AbsoluteFill>
      <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}}>
        <defs>
          <linearGradient id="tk-depth" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={OCEAN.top} />
            <stop offset="0.55" stopColor={OCEAN.mid} />
            <stop offset="1" stopColor={OCEAN.deep} />
          </linearGradient>
        </defs>
        <rect width={1080} height={1920} fill="url(#tk-depth)" />
        {tris.map((t, i) => <path key={i} d={t.d} fill={t.v > 0.5 ? '#FFFFFF' : '#000000'} opacity={0.012 + Math.abs(t.v - 0.5) * 0.06} />)}
      </svg>
    </AbsoluteFill>
  );
};

/** Ocean inside a map card (lighter, shallow-water centre) with finer static facets. Render inside an <svg>. */
export const MapOcean: React.FC<{box: Box; id: string}> = ({box, id}) => {
  const tris = useMemo(() => facetMesh(box, 64, 11), [box]);
  return (
    <g>
      <defs>
        <radialGradient id={`${id}-sea`} cx="50%" cy="45%" r="75%">
          <stop offset="0" stopColor={OCEAN.shallow} />
          <stop offset="1" stopColor={OCEAN.mapEdge} />
        </radialGradient>
      </defs>
      <rect x={box.x} y={box.y} width={box.w} height={box.h} fill={`url(#${id}-sea)`} />
      {tris.map((t, i) => <path key={i} d={t.d} fill={t.v > 0.5 ? '#FFFFFF' : '#000000'} opacity={0.015 + Math.abs(t.v - 0.5) * 0.07} />)}
    </g>
  );
};

/** Low-poly overlay pattern for land pieces (subtle light/dark facets). */
export const FacetPatternDef: React.FC<{id: string; size?: number}> = ({id, size = 90}) => {
  const tris = useMemo(() => facetMesh({x: 0, y: 0, w: size, h: size}, size / 2, 23), [size]);
  return (
    <pattern id={id} width={size} height={size} patternUnits="userSpaceOnUse">
      {tris.map((t, i) => <path key={i} d={t.d} fill={t.v > 0.5 ? '#FFFFFF' : '#000000'} opacity={Math.abs(t.v - 0.5) * 0.22} />)}
    </pattern>
  );
};

/** Hook + question from frame 0; they give way to the explanation at t.explain (same slot). */
export const Header: React.FC<{s: StyleTokens; t: Timing; hook: string; question: string; explanation: string}> = ({s, t, hook, question, explanation}) => {
  const frame = useCurrentFrame();
  const o = exit(frame, t.explain - 0.4, 0.35);
  const rise = enter(frame, 0, 0.35);
  return (
    <>
      <div style={{position: 'absolute', left: SAFE_RECT.x0, width: SAFE_RECT.x1 - SAFE_RECT.x0, top: 316, opacity: o,
        transform: `translateY(${(1 - rise) * 10}px)`}}>
        <div style={{fontFamily: s.fontBody, fontWeight: 800, fontSize: 42, color: s.accent, lineHeight: 1.15}}>{hook}</div>
        <div style={{fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 64, color: s.fg, lineHeight: 1.06, marginTop: 8}}>{question}</div>
      </div>
      <Explanation s={s} t={t} text={explanation} top={322} fontSize={42} style={{fontWeight: 700, lineHeight: 1.25}} />
    </>
  );
};

/** Map label: white Nunito with an ocean-coloured halo; optional leader line to its anchor. Render inside an <svg>. */
export const MapLabel: React.FC<{s: StyleTokens; l: LabelOut; opacity: number; dy?: number; weight?: number; color?: string}> = ({s, l, opacity, dy = 0, weight = 800, color}) => {
  if (opacity <= 0.001) return null;
  const e = rectEdgeToward(l);
  return (
    <g opacity={opacity} transform={`translate(0 ${dy})`}>
      {l.leader && <>
        <line x1={l.ax} y1={l.ay} x2={e[0]} y2={e[1]} stroke={OCEAN.halo} strokeWidth={6} strokeLinecap="round" />
        <line x1={l.ax} y1={l.ay} x2={e[0]} y2={e[1]} stroke={s.fg} strokeWidth={2.5} strokeLinecap="round" />
        <circle cx={l.ax} cy={l.ay} r={6} fill={s.fg} stroke={OCEAN.halo} strokeWidth={3} />
      </>}
      <text x={l.x} y={l.y} textAnchor="middle" dominantBaseline="central" fontFamily={s.fontBody} fontWeight={weight} fontSize={l.size}
        fill={color ?? s.fg} stroke={OCEAN.halo} strokeWidth={l.size * 0.26} strokeLinejoin="round" paintOrder="stroke">{l.text}</text>
    </g>
  );
};
