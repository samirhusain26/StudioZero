// Tectonic-local geometry helpers on top of kit/geo.ts: view fitting, culled paths, visible-part label anchors,
// shared-border detection and a small deterministic label layout. Pure functions (no randomness, no time).
import type {GeoCountry} from '../../types';
import {orthographic, type Projector} from '../../kit/geo';

const RAD = Math.PI / 180;
export type Box = {x: number; y: number; w: number; h: number};
export type View = {center: [number, number]; span: number; box: Box};
export type Pt = [number, number];

export const projector = (v: View): Projector => orthographic(v.center, v.span, v.box.w, v.box.h, [v.box.x, v.box.y]);
export const radiusOf = (v: View) => v.box.h / (2 * Math.sin((v.span / 2) * RAD));

/** Inverse orthographic: pixel → [lon, lat] (null off the globe). */
export function invert(v: View, px: number, py: number): Pt | null {
  const R = radiusOf(v);
  const x = (px - v.box.x - v.box.w / 2) / R, y = -(py - v.box.y - v.box.h / 2) / R;
  const rho = Math.hypot(x, y);
  if (rho > 1) return null;
  if (rho === 0) return v.center;
  const c = Math.asin(rho), lon0 = v.center[0] * RAD, lat0 = v.center[1] * RAD;
  const lat = Math.asin(Math.cos(c) * Math.sin(lat0) + (y * Math.sin(c) * Math.cos(lat0)) / rho);
  const lon = lon0 + Math.atan2(x * Math.sin(c), rho * Math.cos(c) * Math.cos(lat0) - y * Math.sin(c) * Math.sin(lat0));
  return [lon / RAD, lat / RAD];
}

function borderSamples(b: Box, n = 10): Pt[] {
  const out: Pt[] = [];
  for (let i = 0; i <= n; i++) {
    const u = i / n;
    out.push([b.x + u * b.w, b.y], [b.x + u * b.w, b.y + b.h], [b.x, b.y + u * b.h], [b.x + b.w, b.y + u * b.h]);
  }
  return out;
}

/** lon/lat bounds of what a view shows (sampled along the box edge; regional views only). */
export function viewBounds(v: View, scale = 1): number[] {
  const cx = v.box.x + v.box.w / 2, cy = v.box.y + v.box.h / 2;
  const b = {x: cx - (v.box.w * scale) / 2, y: cy - (v.box.h * scale) / 2, w: v.box.w * scale, h: v.box.h * scale};
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [px, py] of borderSamples(b, 12)) {
    const g = invert(v, px, py);
    if (!g) continue;
    x0 = Math.min(x0, g[0]); y0 = Math.min(y0, g[1]); x1 = Math.max(x1, g[0]); y1 = Math.max(y1, g[1]);
  }
  return [x0, y0, x1, y1];
}

const insideWin = (p: Pt | null, w: number[]) => !!p && p[0] >= w[0] && p[0] <= w[2] && p[1] >= w[1] && p[1] <= w[3];

/** Largest span (deg of latitude) at which the whole box stays inside a lon/lat window. */
export function maxSpanInside(center: Pt, box: Box, win: number[]): number {
  let lo = 0.2, hi = 120;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    const v = {center, span: mid, box};
    if (borderSamples(box, 12).every(([x, y]) => insideWin(invert(v, x, y), win))) lo = mid; else hi = mid;
  }
  return lo;
}

export function ringBox(r: number[][]) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of r) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}
export const largestRing = (c: GeoCountry) => c.rings.reduce((a, b) => (b.length > a.length ? b : a), c.rings[0]);
/** Box of the main landmass (avoids overseas territories stretching a country's bbox). */
export const mainBox = (c: GeoCountry) => ringBox(largestRing(c));
export const boxCenter = (b: number[]): Pt => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

function inRing(r: number[][], [x, y]: number[]) {
  let inside = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
/** True when c's main ring lies wholly inside host's: an enclave the source data does not cut out as a hole
 *  (Lesotho in South Africa; San Marino and Vatican City in Italy). Drawn after its host or it disappears. */
export const enclosedBy = (c: GeoCountry, host: GeoCountry) => largestRing(c).every((p) => inRing(largestRing(host), p));

const overlaps = (a: number[], b: number[]) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

/** Projected rings of a country that intersect `bounds` and lie wholly on the near hemisphere. */
export function projectRings(c: GeoCountry, project: Projector, bounds: number[]): Pt[][] {
  const out: Pt[][] = [];
  for (const r of c.rings) {
    if (!overlaps(ringBox(r), bounds)) continue;
    const pts = r.map(project);
    if (pts.some((p) => !p[2])) continue;
    out.push(pts.map((p) => [p[0], p[1]] as Pt));
  }
  return out;
}

export const toD = (rings: Pt[][]) => rings.map((r) => 'M' + r.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z').join('');

/** Sutherland–Hodgman clip of a polygon against an axis-aligned box. */
export function clipToBox(poly: Pt[], b: Box): Pt[] {
  const edges: [(p: Pt) => boolean, (a: Pt, c: Pt) => Pt][] = [
    [(p) => p[0] >= b.x, (a, c) => { const t = (b.x - a[0]) / (c[0] - a[0]); return [b.x, a[1] + t * (c[1] - a[1])]; }],
    [(p) => p[0] <= b.x + b.w, (a, c) => { const t = (b.x + b.w - a[0]) / (c[0] - a[0]); return [b.x + b.w, a[1] + t * (c[1] - a[1])]; }],
    [(p) => p[1] >= b.y, (a, c) => { const t = (b.y - a[1]) / (c[1] - a[1]); return [a[0] + t * (c[0] - a[0]), b.y]; }],
    [(p) => p[1] <= b.y + b.h, (a, c) => { const t = (b.y + b.h - a[1]) / (c[1] - a[1]); return [a[0] + t * (c[0] - a[0]), b.y + b.h]; }],
  ];
  let out = poly;
  for (const [inside, cross] of edges) {
    const src = out; out = [];
    for (let i = 0; i < src.length; i++) {
      const cur = src[i], prev = src[(i + src.length - 1) % src.length];
      if (inside(cur)) { if (!inside(prev)) out.push(cross(prev, cur)); out.push(cur); }
      else if (inside(prev)) out.push(cross(prev, cur));
    }
    if (!out.length) break;
  }
  return out;
}

function pointInRings(x: number, y: number, rings: Pt[][]) {
  let inside = false;
  for (const r of rings) for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function edgeDist(x: number, y: number, rings: Pt[][]) {
  let d = Infinity;
  for (const r of rings) for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [ax, ay] = r[j], [bx, by] = r[i];
    const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L)) : 0;
    d = Math.min(d, Math.hypot(x - ax - t * dx, y - ay - t * dy));
  }
  return d;
}

/** Most interior point of the visible part of a country inside `b` (grid "pole of inaccessibility"). */
export function visibleAnchor(rings: Pt[][], b: Box): {x: number; y: number; r: number} | null {
  const clipped = rings.map((r) => clipToBox(r, b)).filter((r) => r.length >= 3);
  if (!clipped.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const r of clipped) for (const [x, y] of r) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  let best = {x: (x0 + x1) / 2, y: (y0 + y1) / 2, r: -1};
  const N = 28;
  for (let pass = 0; pass < 2; pass++) {
    const sx = pass === 0 ? x0 : best.x - (x1 - x0) / N, ex = pass === 0 ? x1 : best.x + (x1 - x0) / N;
    const sy = pass === 0 ? y0 : best.y - (y1 - y0) / N, ey = pass === 0 ? y1 : best.y + (y1 - y0) / N;
    for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
      const x = sx + ((ex - sx) * (i + 0.5)) / (N + 1), y = sy + ((ey - sy) * (j + 0.5)) / (N + 1);
      if (!pointInRings(x, y, clipped)) continue;
      const d = edgeDist(x, y, clipped);
      if (d > best.r) best = {x, y, r: d};
    }
  }
  return best.r < 0 ? {x: (x0 + x1) / 2, y: (y0 + y1) / 2, r: 0} : best;
}

/** Polylines of the target's outline that it shares (identical vertices) with any of the given neighbors. */
export function sharedBorders(target: GeoCountry, neighbors: GeoCountry[]): number[][][] {
  const key = (p: number[]) => `${p[0].toFixed(3)},${p[1].toFixed(3)}`;
  const sets = neighbors.map((n) => new Set(n.rings.flatMap((r) => r.map(key))));
  const lines: number[][][] = [];
  for (const r of target.rings) {
    const n = r.length;
    for (const set of sets) {
      let cur: number[][] = [];
      for (let i = 0; i <= n; i++) {
        const a = r[i % n], b = r[(i + 1) % n];
        if (i < n && set.has(key(a)) && set.has(key(b))) { if (!cur.length) cur.push(a); cur.push(b); }
        else if (cur.length) { lines.push(cur); cur = []; }
      }
      if (cur.length) lines.push(cur);
    }
  }
  return lines;
}

// ---- labels -------------------------------------------------------------------------------------------------
export const textWidth = (text: string, size: number, k = 0.56) => text.length * size * k;

export type LabelIn = {id: string; text: string; ax: number; ay: number; r: number; size: number};
export type LabelOut = LabelIn & {x: number; y: number; w: number; h: number; leader: boolean};

/**
 * Places labels near their anchors without overlaps, inside `b`, avoiding fixed obstacle rects (e.g. the gap).
 * Labels too big for their country start just outside it (away from `from`); a leader line marks moved labels.
 */
export function layoutLabels(items: LabelIn[], b: Box, obstacles: {x: number; y: number; w: number; h: number}[], from: Pt, pad = 10): LabelOut[] {
  const out: LabelOut[] = items.map((it) => {
    const w = textWidth(it.text, it.size) + 12, h = it.size * 1.2;
    let x = it.ax, y = it.ay;
    if (it.r * 2.2 < h) {
      const dx = it.ax - from[0], dy = it.ay - from[1], L = Math.hypot(dx, dy) || 1;
      x = it.ax + (dx / L) * (it.r + h * 0.9); y = it.ay + (dy / L) * (it.r + h * 0.9);
    }
    return {...it, x, y, w, h, leader: false};
  });
  const clamp = (l: LabelOut) => {
    l.x = Math.max(b.x + l.w / 2 + pad, Math.min(b.x + b.w - l.w / 2 - pad, l.x));
    l.y = Math.max(b.y + l.h / 2 + pad, Math.min(b.y + b.h - l.h / 2 - pad, l.y));
  };
  out.forEach(clamp);
  const sep = (a: {x: number; y: number; w: number; h: number}, c: {x: number; y: number; w: number; h: number}) => {
    const ox = (a.w + c.w) / 2 + 6 - Math.abs(a.x - c.x), oy = (a.h + c.h) / 2 + 4 - Math.abs(a.y - c.y);
    return ox > 0 && oy > 0 ? {ox, oy} : null;
  };
  for (let it = 0; it < 80; it++) {
    let moved = false;
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const a = out[i], c = out[j], o = sep(a, c);
        if (!o) continue;
        moved = true;
        // the label with the larger country stays put more
        const wa = a.r >= c.r ? 0.3 : 0.7, wc = 1 - wa;
        if (o.oy < o.ox) { const s = a.y <= c.y ? -1 : 1; a.y += s * o.oy * wa; c.y -= s * o.oy * wc; }
        else { const s = a.x <= c.x ? -1 : 1; a.x += s * o.ox * wa; c.x -= s * o.ox * wc; }
      }
      for (const ob of obstacles) {
        const a = out[i], o = sep(a, ob);
        if (!o) continue;
        moved = true;
        if (o.oy < o.ox) a.y += (a.y <= ob.y ? -1 : 1) * o.oy; else a.x += (a.x <= ob.x ? -1 : 1) * o.ox;
      }
      clamp(out[i]);
    }
    if (!moved) break;
  }
  for (const l of out) {
    const inside = Math.abs(l.ax - l.x) < l.w / 2 - 4 && Math.abs(l.ay - l.y) < l.h / 2 - 2;
    l.leader = !inside && Math.hypot(l.ax - l.x, l.ay - l.y) > l.h * 0.7;
  }
  return out;
}

/** Point on a label rect's boundary nearest to the anchor (for leader lines). */
export function rectEdgeToward(l: LabelOut): Pt {
  const dx = l.ax - l.x, dy = l.ay - l.y;
  const sx = dx === 0 ? Infinity : l.w / 2 / Math.abs(dx), sy = dy === 0 ? Infinity : l.h / 2 / Math.abs(dy);
  const s = Math.min(sx, sy, 1);
  return [l.x + dx * s, l.y + dy * s];
}

/** Deterministic hash → [0,1). */
export function hash(...n: number[]) {
  let h = 2166136261;
  for (const v of n) { h ^= Math.floor(v * 1000) + 0x9e3779b9; h = Math.imul(h, 16777619); h ^= h >>> 13; }
  return ((h >>> 0) % 100000) / 100000;
}
