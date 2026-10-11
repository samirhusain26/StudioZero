import type {StyleTokens} from '../types';
import {FONT} from '../fonts';

/** Scalar · field notebook: paper, charcoal ink, teal accent, thermal green/orange; index cards dealt onto a desk. */
export const style: StyleTokens = {
  id: 'scalar-notebook-1', version: 1, game: 'scalar',
  summary: 'Field notebook on a graph-paper desk: paper #FAFAF9, charcoal #18181B ink, teal #14B8A6 accent, thermal green #22C55E / orange #F97316. ' +
    'Fraunces 900 headlines and clue text, Geist Mono labels and numbers. Sharp-cornered white index cards (3 px ink border, hard 8 px offset shadow, ' +
    'orange header rule, teal number tab) are dealt in from off-frame with a decelerating slide-and-settle; a tally card counts the countries that still fit ' +
    '(195 → … → 1) on an honest zero-based bar. Reveal = a speckled green rubber stamp slammed onto the pile, then a ruled locator card ' +
    '(orthographic, answer in teal, neighbours paper with ink outlines). Candidate checklists tick/cross per clue with thermal green/orange marks.',
  bg: '#FAFAF9', bg2: '#F1EFEA', fg: '#18181B', muted: '#52525B', line: '#18181B', card: '#FFFFFF',
  accent: '#14B8A6', accent2: '#F97316', good: '#22C55E', bad: '#A1A1AA',
  fontDisplay: FONT.fraunces, fontBody: FONT.geist, fontNumber: FONT.geist,
  sfx: {item: 'flip', choices: 'pop', think: 'tock', reveal: 'stamp', cta: 'swoosh'},
};

/** Extra notebook tokens (ink-strength variants of the thermal colours for text/lines on paper). */
export const NB = {
  stampInk: '#15803D',     // deep thermal green: stamp ink and tick marks (legible on paper)
  crossInk: '#C2410C',     // deep thermal orange: strike-outs and crosses
  tealInk: '#0F766E',      // teal for small text on paper
  grid: '#ECE9E2',         // desk graph-paper lines
  margin: '#FDC9A3',       // notebook margin rule
  rule: '#F97316',         // index-card header rule
  ruled: '#DCEBE9',        // faint index-card ruling
  ocean: '#E3EFED',        // locator map sea
  land: '#FFFFFF',
  goodWash: '#ECFDF3',     // pale green wash behind the confirmed answer
  shadow: 8,               // hard offset shadow (px), no blur
};
