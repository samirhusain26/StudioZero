// Decorative paint as SVG instead of CSS that client-side rendering (@remotion/web-renderer) cannot emulate:
// repeating and tiled gradients, radial gradients and inset shadows. Same geometry as the CSS each one replaces, so
// render.sh output stays the same and the browser export matches it. A layer is absolute and fills its containing
// block, so it must come before the content it sits under, and that content needs `position: relative` (positioned
// elements paint in DOM order in both renderers). Every layer has explicit pixel dimensions: the client-side renderer
// rasterizes each <svg> on its own, where a percentage size would fall back to 300 × 150 and be stretched.
import React from 'react';

const layer: React.CSSProperties = {position: 'absolute', left: 0, top: 0};

/** Index-card ruling: a 3 px header rule at `top`, then 2 px lines at 58–60 px of every 60 px (from the padding edge). */
export const RuledLines: React.FC<{width: number; height: number; top: number; rule: string; ruled: string}> = ({width, height, top, rule, ruled}) => (
  <svg width={width} height={height} style={layer} shapeRendering="crispEdges" aria-hidden>
    {Array.from({length: Math.floor((height - 58) / 60) + 1}, (_, k) => <rect key={k} x={0} y={58 + 60 * k} width={width} height={2} fill={ruled} />)}
    <rect x={0} y={top} width={width} height={3} fill={rule} />
  </svg>
);

/** A 1 px grid every `step` px from the top-left corner (both directions). */
export const GridLines: React.FC<{step: number; color: string; width: number; height: number}> = ({step, color, width, height}) => (
  <svg width={width} height={height} style={layer} shapeRendering="crispEdges" aria-hidden>
    {Array.from({length: Math.ceil(width / step)}, (_, k) => <rect key={`x${k}`} x={k * step} y={0} width={1} height={height} fill={color} />)}
    {Array.from({length: Math.ceil(height / step)}, (_, k) => <rect key={`y${k}`} x={0} y={k * step} width={width} height={1} fill={color} />)}
  </svg>
);

/** Diagonal hatching like `repeating-linear-gradient(135deg, color 0 on, transparent on period)`. `id` must be unique per frame. */
export const Hatch: React.FC<{id: string; width: number; height: number; color: string; on: number; period: number}> = ({id, width, height, color, on, period}) => (
  <svg width={width} height={height} style={layer} aria-hidden>
    <defs>
      {/* Rotated 45°, the pattern's x axis runs along the gradient line (towards the bottom right). */}
      <pattern id={id} width={period} height={period} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect x={0} y={0} width={on} height={period} fill={color} />
      </pattern>
    </defs>
    <rect width={width} height={height} fill={`url(#${id})`} />
  </svg>
);

/** `box-shadow: inset 0 0 0 <width>px <color>` as four bands inside the padding box. */
export const InsetRing: React.FC<{width: number; color: string}> = ({width, color}) =>
  width > 0 ? (
    <>
      <div style={{position: 'absolute', left: 0, top: 0, right: 0, height: width, background: color}} />
      <div style={{position: 'absolute', left: 0, bottom: 0, right: 0, height: width, background: color}} />
      <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width, background: color}} />
      <div style={{position: 'absolute', right: 0, top: 0, bottom: 0, width, background: color}} />
    </>
  ) : null;
