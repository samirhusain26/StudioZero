import type {StyleTokens} from '../types';
import {style as scalarNotebook} from './scalar-notebook-1';
import {style as continuumPoster} from './continuum-poster-1';
import {style as whenaboutsAlmanac} from './whenabouts-almanac-1';
import {style as tectonicOcean} from './tectonic-ocean-1';

export const STYLES: Record<string, StyleTokens> = Object.fromEntries(
  [scalarNotebook, continuumPoster, whenaboutsAlmanac, tectonicOcean].map((s) => [s.id, s]),
);
