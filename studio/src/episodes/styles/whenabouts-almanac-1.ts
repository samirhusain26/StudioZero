import type {StyleTokens} from '../types';
import {FONT} from '../fonts';

/** Highlighter yellow: used only as a fill (reveal marks, odometer highlight, answer chip), never as text on parchment. */
export const ALMANAC_YELLOW = '#EAB308';
/** Rust ink for the before-after anchor pin. */
export const ALMANAC_RUST = '#9A3412';

/**
 * Whenabouts · almanac. `accent` is a deep ochre (not the highlighter yellow) because the kit sets text in `accent`
 * (choice letters, scalargame.com on the closing card); #EAB308 on parchment is ~1.7:1 and unreadable at phone scale.
 */
export const style: StyleTokens = {
  id: 'whenabouts-almanac-1', version: 1, game: 'whenabouts',
  summary: 'Almanac: parchment #F4ECD8 with a soft vignette, laid-paper lines and a double-rule page frame; sepia ink #2B1D0E; '
    + 'highlighter yellow #EAB308 as fill only, deep ochre #A16207 for accent text. Fraunces italic 900 headlines, Geist Mono for '
    + 'years and labels. Typographic event card (double rule, vector fleurons, no photos). A horizontal ruler timeline pans in '
    + 'unlabelled, then carries the A/B/C year marks (or the pinned anchor). Calm ease-out entries; anticipation wind-up; the '
    + 'reveal is a year odometer rolling to the answer (or the “?” token gliding onto its side of the anchor at an honest distance), followed by a single '
    + 'pan/zoom of the ruler and a yellow highlight on the correct mark.',
  bg: '#F4ECD8', bg2: '#EADFC4', fg: '#2B1D0E', muted: '#6B5B45', line: '#2B1D0E', card: '#FBF6EA',
  accent: '#A16207', accent2: ALMANAC_RUST, good: '#14532D', bad: '#A8977A',
  fontDisplay: FONT.fraunces, fontBody: FONT.fraunces, fontNumber: FONT.geist,
  sfx: {item: 'flip', choices: 'pop', think: 'tock', reveal: 'ding', cta: 'swoosh'},
};
