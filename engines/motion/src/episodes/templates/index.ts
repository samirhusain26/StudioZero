import type {Format} from '../types';
import type {Template} from './types';
import {ProgressiveClues} from './scalar/ProgressiveClues';
import {CandidateElimination} from './scalar/CandidateElimination';
import {HeadToHead} from './continuum/HeadToHead';
import {MissingSlot} from './continuum/MissingSlot';
import {GuessTheYear} from './whenabouts/GuessTheYear';
import {BeforeAfter} from './whenabouts/BeforeAfter';
import {MissingCountry} from './tectonic/MissingCountry';
import {NeighborClues} from './tectonic/NeighborClues';

export const TEMPLATES: Record<Format, Template> = {
  'progressive-clues': ProgressiveClues,
  'candidate-elimination': CandidateElimination,
  'head-to-head': HeadToHead,
  'missing-slot': MissingSlot,
  'guess-the-year': GuessTheYear,
  'before-after': BeforeAfter,
  'missing-country': MissingCountry,
  'neighbor-clues': NeighborClues,
};
