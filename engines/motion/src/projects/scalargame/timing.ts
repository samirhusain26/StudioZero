import type {Format, Timing} from './types';

export const FPS = 30;
export const MIN_THINK_SECONDS = 6;
/** Conservative working safe rectangle for essential content (VIDEO_GENERATION_PIPELINE.md). */
export const SAFE_RECT = {x0: 90, x1: 900, y0: 270, y1: 1530};
export const ENTRY_SECONDS = 0.5; // an entry animation is complete this long after its start

// Reveals sit on a 120 BPM downbeat (even seconds) so the music beds' drop/groove entry lands on the answer.
export const TIMING: Record<Format, Timing> = {
  'progressive-clues':     {duration: 24, items: [1.0, 3.0, 5.0],       choicesIn: 6.5, infoComplete: 7.5, reveal: 14, explain: 18, cta: 21.5},
  'candidate-elimination': {duration: 24, items: [2.5, 4.0, 5.5],       choicesIn: 0.8, infoComplete: 7.0, reveal: 14, explain: 18, cta: 21.5},
  'head-to-head':          {duration: 20, items: [],                    choicesIn: 1.0, infoComplete: 3.5, reveal: 10, explain: 13.5, cta: 17.5},
  'missing-slot':          {duration: 22, items: [1.0, 2.5],            choicesIn: 4.0, infoComplete: 5.5, reveal: 12, explain: 16, cta: 19.5},
  'guess-the-year':        {duration: 22, items: [0.6],                 choicesIn: 3.0, infoComplete: 5.5, reveal: 12, explain: 16, cta: 19.5},
  'before-after':          {duration: 22, items: [0.6, 2.0],            choicesIn: 3.5, infoComplete: 5.5, reveal: 12, explain: 16, cta: 19.5},
  'missing-country':       {duration: 22, items: [0.5, 1.5, 2.5],       choicesIn: 4.0, infoComplete: 5.5, reveal: 12, explain: 16, cta: 19.5},
  'neighbor-clues':        {duration: 24, items: [1.0, 2.5, 4.0],       choicesIn: 6.0, infoComplete: 7.5, reveal: 14, explain: 18, cta: 21.5},
};

export const f = (seconds: number) => Math.round(seconds * FPS);

/** Throws if a timing would cut the thinking window or overlap phases. Called by episodes.mjs and at render. */
export function assertTiming(t: Timing, format: string) {
  const last = Math.max(t.choicesIn, ...t.items) + ENTRY_SECONDS;
  if (t.infoComplete < last) throw new Error(`${format}: infoComplete ${t.infoComplete}s before last entry ends (${last}s)`);
  if (t.reveal - t.infoComplete < MIN_THINK_SECONDS) throw new Error(`${format}: thinking window ${t.reveal - t.infoComplete}s < ${MIN_THINK_SECONDS}s`);
  if (!(t.reveal < t.explain && t.explain < t.cta && t.cta < t.duration)) throw new Error(`${format}: phase order`);
  if (t.duration < 20 || t.duration > 24) throw new Error(`${format}: duration ${t.duration}s outside 20–24s`);
  if (t.duration - t.cta < 2) throw new Error(`${format}: CTA shorter than 2s`);
}
