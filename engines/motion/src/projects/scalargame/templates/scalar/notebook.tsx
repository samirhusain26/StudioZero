// Shared field-notebook pieces for the Scalar templates: desk, dealt index cards, rubber stamp, tally counter,
// checkbox marks and a locator map. Deterministic: everything derives from props and the current frame.
import React from 'react';
import {AbsoluteFill, Easing, interpolate} from 'remotion';
import type {GeoCountry, StyleTokens} from '../../types';
import {orthographic, labelPoint, pixelBox, type Projector} from '../../kit/geo';
import {enter, mix} from '../../kit/motion';
import {RuledLines} from '../../kit/paint';
import {f} from '../../timing';
import {NB} from '../../styles/scalar-notebook-1';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** Graph-paper desk with a notebook margin rule; bleeds full frame (decoration only). */
export const Desk: React.FC<{s: StyleTokens}> = ({s}) => (
  <AbsoluteFill style={{background: s.bg}}>
    <svg width={1080} height={1920} style={{position: 'absolute', inset: 0}}>
      <defs>
        <pattern id="nb-grid" width={45} height={45} patternUnits="userSpaceOnUse" x={15} y={0}>
          <path d="M45 0H0V45" fill="none" stroke={NB.grid} strokeWidth={1.5} />
        </pattern>
      </defs>
      <rect width={1080} height={1920} fill="url(#nb-grid)" />
      <line x1={52} y1={0} x2={52} y2={1920} stroke={NB.margin} strokeWidth={3} />
      <line x1={60} y1={0} x2={60} y2={1920} stroke={NB.margin} strokeWidth={1.5} />
    </svg>
  </AbsoluteFill>
);

/**
 * “Deal” motion: a card slides in from off-frame (right by default), rotating from a steeper angle to its resting tilt,
 * decelerating to rest within `dur` seconds. Returns null before `at`.
 */
export function deal(frame: number, at: number, rest: number, dir: 1 | -1 = 1, dur = 0.45) {
  if (frame < f(at)) return null;
  const p = enter(frame, at, dur, Easing.bezier(0.2, 0.9, 0.25, 1));
  return {
    p,
    transform: `translate(${(1 - p) * 1000 * dir}px, ${(1 - p) * 140}px) rotate(${mix(rest + 14 * dir, rest, p)}deg)`,
    lift: 1 - p,
  };
}

export const cardStyle = (s: StyleTokens, lift = 0, shadow = s.line): React.CSSProperties => ({
  background: s.card, border: `3px solid ${s.line}`, boxSizing: 'border-box',
  boxShadow: `${NB.shadow + lift * 16}px ${NB.shadow + lift * 16}px 0 ${shadow}`,
});

/**
 * Index card body: orange header rule and faint ruling over the padding box (`width` × `height`), as an SVG layer: the
 * first child; content after it is `position: relative`.
 */
export const Ruling: React.FC<{width: number; height: number; top?: number}> = ({width, height, top = 16}) =>
  <RuledLines width={width} height={height} top={top} rule={NB.rule} ruled={NB.ruled} />;

/** Numbered clue index card (fixed slot; text vertically centred, wraps to ≤ 2 lines at 56 px). */
export const ClueCard: React.FC<{
  s: StyleTokens; n: number; text: string; x: number; y: number; w: number; h: number; transform: string; lift: number;
  focus?: number; dim?: number; fontSize?: number; textFade?: number;
}> = ({s, n, text, x, y, w, h, transform, lift, focus = 0, dim = 1, fontSize = 56, textFade = 1}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: h, transform, transformOrigin: '50% 50%', opacity: dim,
    ...cardStyle(s, lift, s.line), display: 'flex', overflow: 'hidden',
    outline: focus > 0 ? `${Math.round(6 * focus)}px solid ${s.accent}` : undefined}}>
    <div style={{width: 78, flex: '0 0 78px', background: s.accent, borderRight: `3px solid ${s.line}`, display: 'flex',
      alignItems: 'center', justifyContent: 'center', fontFamily: s.fontDisplay, fontWeight: 900, fontSize: 54, color: s.fg}}>
      <span style={{opacity: textFade}}>{n}</span>
    </div>
    <div style={{position: 'relative', flex: 1, display: 'flex', alignItems: 'center', padding: '22px 26px 18px',
      backgroundColor: focus > 0 ? `rgba(20,184,166,${0.1 * focus})` : s.card,
      fontFamily: s.fontDisplay, fontWeight: 900, fontSize, lineHeight: 1.06, color: s.fg, letterSpacing: '-0.005em'}}>
      {/* Card border 3 px each side; the number tab is 78 px including its border (Remotion pages are border-box). */}
      <Ruling width={w - 6 - 78} height={h - 6} />
      <span style={{position: 'relative', opacity: textFade}}>{text}</span>
    </div>
  </div>
);

/**
 * Rubber stamp: invisible before `at`; scales 1.4 → 1 over 4 frames into the impact (accelerating), then holds.
 * Positioned by its centre.
 */
export const Stamp: React.FC<{
  frame: number; at: number; cx: number; cy: number; rotate?: number; color?: string; small?: string; big: string; bigSize?: number;
  fontDisplay: string; fontBody: string;
}> = ({frame, at, cx, cy, rotate = -6, color = NB.stampInk, small, big, bigSize = 80, fontDisplay, fontBody}) => {
  if (frame < f(at)) return null;
  const k = interpolate(frame, [f(at), f(at) + 4], [0, 1], {...clamp, easing: Easing.in(Easing.quad)});
  const scale = mix(1.25, 1, k);
  const o = interpolate(frame, [f(at), f(at) + 2], [0.35, 0.95], clamp);
  return (
    // No blend mode or mask: client-side rendering supports neither (the old speckle mask was opaque, so it never showed).
    <div style={{position: 'absolute', left: cx, top: cy, transform: `translate(-50%, -50%) rotate(${rotate}deg) scale(${scale})`, opacity: o}}>
      <div style={{border: `7px solid ${color}`, padding: 6}}>
        <div style={{border: `3px solid ${color}`, padding: small ? '8px 30px 14px' : '10px 30px', textAlign: 'center', color, whiteSpace: 'nowrap'}}>
          {small && <div style={{fontFamily: fontBody, fontWeight: 700, fontSize: 32, letterSpacing: '0.24em', marginBottom: 2}}>{small}</div>}
          <div style={{fontFamily: fontDisplay, fontWeight: 900, fontSize: bigSize, lineHeight: 1, textTransform: 'uppercase', letterSpacing: '0.02em'}}>{big}</div>
        </div>
      </div>
    </div>
  );
};

/** Hand-drawn style tick / cross glyphs (SVG, so they render identically in any font). */
export const Tick: React.FC<{size: number; color: string; draw?: number; width?: number}> = ({size, color, draw = 1, width = 7}) => (
  <svg width={size} height={size} viewBox="0 0 40 40" style={{overflow: 'visible'}}>
    <path d="M7 21 L16 30 L34 9" fill="none" stroke={color} strokeWidth={width} strokeLinecap="square" strokeLinejoin="miter"
      pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
  </svg>
);
export const Cross: React.FC<{size: number; color: string; draw?: number; width?: number}> = ({size, color, draw = 1, width = 7}) => (
  <svg width={size} height={size} viewBox="0 0 40 40" style={{overflow: 'visible'}}>
    <path d="M9 9 L31 31" fill="none" stroke={color} strokeWidth={width} strokeLinecap="square" pathLength={1} strokeDasharray={1}
      strokeDashoffset={1 - Math.min(1, draw * 2)} />
    <path d="M31 9 L9 31" fill="none" stroke={color} strokeWidth={width} strokeLinecap="square" pathLength={1} strokeDasharray={1}
      strokeDashoffset={1 - Math.max(0, draw * 2 - 1)} />
  </svg>
);

// ---------- Locator map ----------

const RAD = Math.PI / 180;

/** kit/geo `path()` with far-hemisphere points pushed onto the horizon circle (the kit leaves them un-clamped). */
function horizonPath(c: GeoCountry, project: Projector, cx: number, cy: number, R: number): string {
  return c.rings.map((ring) => {
    const pts = ring.map(project);
    if (pts.every((q) => !q[2])) return '';
    return 'M' + pts.map(([x, y, v]) => {
      if (!v) { const dx = x - cx, dy = y - cy, d = Math.hypot(dx, dy) || 1; x = cx + (dx / d) * R; y = cy + (dy / d) * R; }
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join('L') + 'Z';
  }).join('');
}

function graticule(project: Projector, step = 10): string {
  const segs: string[] = [];
  const line = (pts: number[][]) => {
    let cur: string[] = [];
    for (const p of pts) {
      const [x, y, v] = project(p);
      if (v) cur.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      else { if (cur.length > 1) segs.push('M' + cur.join('L')); cur = []; }
    }
    if (cur.length > 1) segs.push('M' + cur.join('L'));
  };
  for (let lon = -180; lon < 180; lon += step) line(Array.from({length: 81}, (_, i) => [lon, -80 + i * 2]));
  for (let lat = -80; lat <= 80; lat += step) line(Array.from({length: 181}, (_, i) => [-180 + i * 2, lat]));
  return segs.join('');
}

/** Bounding box of a country's largest ring (mainland), lon/lat. */
export function mainBox(c: GeoCountry): number[] {
  const ring = c.rings.reduce((a, b) => (b.length > a.length ? b : a), c.rings[0]);
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}

/** Largest span (degrees) whose visible hemisphere still covers every corner of a w×h box. */
export function coverSpan(w: number, h: number) {
  return (2 * Math.asin(Math.min(1, h / Math.hypot(w, h))) / RAD);
}

/** Degrees of latitude that make a lon/lat box fill `fill` of a w×h frame. */
export function fitSpan(bbox: number[], w: number, h: number, fill: number) {
  const lat = (bbox[1] + bbox[3]) / 2;
  const bw = (bbox[2] - bbox[0]) * Math.cos(lat * RAD), bh = bbox[3] - bbox[1];
  return Math.max(bh, bw * (h / w)) / fill;
}

export type MapMark = {id: string; fill: string; stroke?: string; strokeWidth?: number; label?: string; labelColor?: string; labelBg?: string};

/** One orthographic projection, north up; every country in `geo` drawn with its real rings (evenodd). */
export const LocatorMap: React.FC<{
  s: StyleTokens; geo: GeoCountry[]; w: number; h: number; center: [number, number]; span: number; marks: MapMark[]; ringSmall?: string; globe?: boolean;
}> = ({s, geo, w, h, center, span, marks, ringSmall, globe = false}) => {
  // Regional frames fill the box; a `globe` frame shows the whole hemisphere as a disc inside the box.
  const gh = h - 24;
  const project = globe ? orthographic(center, 180, w, gh, [0, 12]) : orthographic(center, span, w, h);
  const R = globe ? gh / 2 : h / (2 * Math.sin((span / 2) * RAD));
  const markById = new Map(marks.map((m) => [m.id, m]));
  const plain = geo.filter((c) => !markById.has(c.id));
  const marked = marks.map((m) => ({m, c: geo.find((c) => c.id === m.id)})).filter((x): x is {m: MapMark; c: GeoCountry} => !!x.c);
  const small = ringSmall ? geo.find((c) => c.id === ringSmall) : undefined;
  const sb = small ? pixelBox(small, project) : null;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{display: 'block'}}>
      <defs><clipPath id="nb-map-clip"><rect width={w} height={h} /></clipPath></defs>
      <g clipPath="url(#nb-map-clip)">
        {globe ? <>
          <rect width={w} height={h} fill={s.bg2} />
          <circle cx={w / 2} cy={h / 2} r={R} fill={NB.ocean} />
        </> : <rect width={w} height={h} fill={NB.ocean} />}
        <path d={graticule(project)} fill="none" stroke="#C9DDDA" strokeWidth={1.2} />
        {plain.map((c) => <path key={c.id} d={horizonPath(c, project, w / 2, h / 2, R)} fill={NB.land} fillRule="evenodd" stroke={s.line} strokeWidth={1.4} strokeLinejoin="round" />)}
        {marked.map(({m, c}) => <path key={c.id} d={horizonPath(c, project, w / 2, h / 2, R)} fill={m.fill} fillRule="evenodd" stroke={m.stroke ?? s.line} strokeWidth={m.strokeWidth ?? 3} strokeLinejoin="round" />)}
        {globe && <circle cx={w / 2} cy={h / 2} r={R} fill="none" stroke={s.line} strokeWidth={3} />}
        {sb && Math.max(sb.w, sb.h) < 70 && <circle cx={sb.cx} cy={sb.cy} r={Math.max(sb.w, sb.h) / 2 + 26} fill="none" stroke={s.line} strokeWidth={4} />}
        {marked.filter(({m}) => m.label).map(({m, c}) => {
          const [x, y] = labelPoint(c, project);
          return (
            <g key={`l-${c.id}`} transform={`translate(${x.toFixed(1)},${y.toFixed(1)})`}>
              <rect x={-24} y={-24} width={48} height={48} fill={m.labelBg ?? s.card} stroke={s.line} strokeWidth={3} />
              <text x={0} y={13} textAnchor="middle" fontFamily={s.fontBody} fontWeight={700} fontSize={36} fill={m.labelColor ?? s.fg}>{m.label}</text>
            </g>
          );
        })}
      </g>
    </svg>
  );
};
