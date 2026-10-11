import type {StyleTokens} from '../types';
import {FONT} from '../fonts';

/** Pink fills carry black text; when pink must be text on cream it uses this deeper ink (≥ 4.5:1). */
export const PINK_INK = '#BE185D';
/** Faint print grid on the paper (decoration only). */
export const GRID = 'rgba(17,17,17,0.045)';
/** Hidden-value hatching inside empty bar tracks. */
export const HATCH = 'rgba(17,17,17,0.10)';

/** Continuum · data poster: cream, black, hot pink; Montserrat + IBM Plex Mono figures; honest zero-baseline bars. */
export const style: StyleTokens = {
  id: 'continuum-poster-1', version: 1, game: 'continuum',
  summary: 'Swiss data poster: cream #F7F3EC paper with a faint 90 px print grid and a pink/black spine bleeding off the left edge; black #111 type and 3–6 px rules, one hot-pink #F472B6 accent used as fills (with black text) for the subject and the answer. Montserrat 900 headlines, Montserrat 600–800 copy, IBM Plex Mono 700 figures. Head-to-head: two stacked white A/B cards with identical hatched empty tracks; at the reveal both bars grow together from one labelled zero line on one linear scale (axis 0 → nice round max), values count up to the exact text, winner turns pink with a check. Missing-slot: an ordinal ladder (equal rungs, “rank order · not to scale”) of two anchors with three dashed A/B/C insertion gaps; the pink target card drops into its gap on the downbeat, then values count up and thin bars grow from the ladder’s left edge, which becomes a labelled zero line. Ease-out entries ≤ 0.5 s, no camera moves, calm think window, source line always visible.',
  bg: '#F7F3EC', bg2: '#EFE8DC', fg: '#111111', muted: '#5B5651', line: '#111111', card: '#FFFFFF',
  accent: '#F472B6', accent2: '#111111', good: '#16A34A', bad: '#A8A29E',
  fontDisplay: FONT.montserrat, fontBody: FONT.montserrat, fontNumber: FONT.plex,
  sfx: {item: 'thock', choices: 'pop', think: 'tock', reveal: 'hit', cta: 'swoosh'},
};
