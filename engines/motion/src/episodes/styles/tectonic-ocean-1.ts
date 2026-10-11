import type {StyleTokens} from '../types';
import {FONT} from '../fonts';

/** Tectonic · low-poly ocean: deep navy ocean, warm orange land, sand neighbours; Nunito; real geometry, spring snap. */
export const style: StyleTokens = {
  id: 'tectonic-ocean-1', version: 1, game: 'tectonic',
  summary: 'Low-poly ocean: deep navy #0B1F33 full-frame depth gradient with a faint static triangular facet mesh; maps sit in a rounded '
    + 'card of lighter shallow-water navy. Neighbors are muted sand #E8D5B0, other land is dim slate #4A5966 and unlabelled, the answer is '
    + 'warm orange #F2A154 with a subtle low-poly facet overlay. Nunito 900 for the question, 800 for map labels (white with navy halo). '
    + 'Canonical globe rings in one orthographic projection centred on the target, cropped to the generator window. Neighbors drift in '
    + 'radially (0.5 s ease-out); the gap is a dashed white outline pulsing softly; before the reveal a shadow gathers, then the answer piece '
    + 'drops in with a spring and a soft drop shadow, the label pops, and the camera pulls back (span ×2.2, same centre, ease-in-out).',
  bg: '#0B1F33', bg2: '#123049', fg: '#F8FAFC', muted: '#9FB3C8', line: '#33597A', card: '#15324B',
  accent: '#F2A154', accent2: '#E8D5B0', good: '#FFC07A', bad: '#64748B',
  fontDisplay: FONT.nunito, fontBody: FONT.nunito, fontNumber: FONT.nunito,
  sfx: {item: 'thock', choices: 'pop', think: 'tock', reveal: 'hit', cta: 'swoosh'},
};

/** Extra Tectonic constants (ocean depth ramp, land fills, halos). */
export const OCEAN = {
  top: '#0F2A44', mid: '#0B1F33', deep: '#06121F',
  shallow: '#17426A', mapEdge: '#0C2238', halo: '#0A1C2E', cardBorder: 'rgba(248,250,252,0.14)',
  gap: '#071523', gapLit: '#1B3A57', fog: '#0B1F33', haze: '#2A4258',
};
export const LAND = {
  neighbor: '#E8D5B0', neighborEdge: '#0B1F33', context: '#4A5966', contextEdge: '#0E2236', answer: '#F2A154', answerEdge: '#7A3E0C',
  border: '#FFF4E3', pulled: '#9C957F',
};
