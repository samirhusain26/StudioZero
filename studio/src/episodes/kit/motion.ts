import {Easing, interpolate, spring} from 'remotion';
import {FPS, f} from '../timing';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

/** 0 → 1 over `dur` seconds starting at `at` seconds (deliberate ease-out). */
export const enter = (frame: number, at: number, dur = 0.5, ease = easeOut) =>
  interpolate(frame, [f(at), f(at + dur)], [0, 1], {...clamp, easing: ease});

/** 1 → 0 over `dur` seconds starting at `at`. */
export const exit = (frame: number, at: number, dur = 0.35) => 1 - enter(frame, at, dur, easeInOut);

/** Spring 0 → ~1 (slight overshoot) starting at `at` seconds; 0 before. */
export const pop = (frame: number, at: number, config = {damping: 12, stiffness: 180, mass: 0.8}) =>
  frame < f(at) ? 0 : spring({frame: frame - f(at) + 1, fps: FPS, config});

/** Linear progress 0 → 1 between two times in seconds. */
export const progress = (frame: number, from: number, to: number) => interpolate(frame, [f(from), f(to)], [0, 1], clamp);

export const mix = (a: number, b: number, t: number) => a + (b - a) * t;
