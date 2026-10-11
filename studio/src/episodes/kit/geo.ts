// Orthographic projection of the snapshot's canonical globe rings into a pixel box. North up, no area distortion
// beyond the projection itself; the same projection is used for every country in a frame.
import type {GeoCountry} from '../types';

const RAD = Math.PI / 180;
export type Projector = (lonlat: number[]) => [number, number, boolean];

/**
 * Centre on `center` (lon, lat); `spanDeg` degrees of latitude fill `height` pixels.
 * Returns [x, y, visible]; far-hemisphere points are clamped to the horizon (fine for regional frames).
 */
export function orthographic(center: [number, number], spanDeg: number, width: number, height: number, offset: [number, number] = [0, 0]): Projector {
  const lon0 = center[0] * RAD, lat0 = center[1] * RAD;
  const R = height / (2 * Math.sin((spanDeg / 2) * RAD));
  return ([lon, lat]) => {
    const l = lon * RAD - lon0, p = lat * RAD;
    const x = Math.cos(p) * Math.sin(l);
    const y = Math.cos(lat0) * Math.sin(p) - Math.sin(lat0) * Math.cos(p) * Math.cos(l);
    const z = Math.sin(lat0) * Math.sin(p) + Math.cos(lat0) * Math.cos(p) * Math.cos(l);
    if (z >= 0) return [offset[0] + width / 2 + x * R, offset[1] + height / 2 - y * R, true];
    const n = Math.hypot(x, y) || 1; // far hemisphere: clamp to the horizon so partly visible rings stay closed
    return [offset[0] + width / 2 + (x / n) * R, offset[1] + height / 2 - (y / n) * R, false];
  };
}

export function path(c: GeoCountry, project: Projector): string {
  return c.rings.map((ring) => {
    const pts = ring.map(project);
    if (pts.every((q) => !q[2])) return '';
    return 'M' + pts.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join('L') + 'Z';
  }).join('');
}

/** Pixel bbox of a country under a projector. */
export function pixelBox(c: GeoCountry, project: Projector) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const r of c.rings) for (const p of r) {
    const [x, y] = project(p);
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  }
  return {x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, w: x1 - x0, h: y1 - y0};
}

/** Projected centroid of the largest ring (good label anchor for multi-part countries). */
export function labelPoint(c: GeoCountry, project: Projector): [number, number] {
  const largest = c.rings.reduce((a, b) => (b.length > a.length ? b : a), c.rings[0]);
  let x = 0, y = 0;
  for (const p of largest) { const q = project(p); x += q[0]; y += q[1]; }
  return [x / largest.length, y / largest.length];
}

/** Span (degrees of latitude) that fits a lon/lat bbox in a box of the given aspect ratio, with padding. */
export function spanFor(bbox: number[], width: number, height: number, pad = 1.15): number {
  const lat = (bbox[1] + bbox[3]) / 2;
  const w = (bbox[2] - bbox[0]) * Math.cos(lat * RAD), h = bbox[3] - bbox[1];
  return Math.max(h, w * (height / width)) * pad;
}
