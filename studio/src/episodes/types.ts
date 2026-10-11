// Library quiz episodes (kit-1). Props are produced by studio/pipeline/episodes.mjs from the
// checked question set and are immutable per render job: templates must render from props alone.
import type {SfxName} from '../kit/sfx';

export type Game = 'scalar' | 'continuum' | 'whenabouts' | 'tectonic';
export type Format =
  | 'progressive-clues' | 'candidate-elimination'
  | 'head-to-head' | 'missing-slot'
  | 'guess-the-year' | 'before-after'
  | 'missing-country' | 'neighbor-clues';

export type Choice = {key: string; label: string; id?: string; year?: number; poll?: string};
export type Valued = {id: string; label: string; value: number; text: string};
export type DatedEvent = {id: string; title: string; year: number; month?: number | null; day?: number | null};

/** The resolved question (subset of library/_sources/<snapshot>/questions-*.json). */
export type Question = {
  key: string; game: Game; format: Format; difficulty: 'approachable' | 'moderate' | 'challenging';
  hook: string; question: string; prompt?: string; anchorPrompt?: string;
  clues?: string[]; choices: Choice[]; answer: string; answerKey: string; explanation: string;
  // continuum
  metric?: {id: 'population' | 'area'; label: string; definition: string; year: number; unit: string};
  values?: Valued[]; anchors?: Valued[]; target?: Valued;
  // whenabouts
  event?: DatedEvent; anchor?: DatedEvent;
  // tectonic
  shown?: {id: string; label: string}[]; allNeighbors?: boolean;
  geometry?: {target: string; neighbors: string[]; frame: string[]; frameBbox?: number[]};
  /** Lon/lat window [minLon, minLat, maxLon, maxLat] a map should frame (scalar locator, tectonic). */
  geoWindow?: number[] | null;
  evidence: {checks: Record<string, unknown>};
};

/** Canonical country geometry from the snapshot's Tectonic globe (Natural Earth derived). */
export type GeoCountry = {id: string; name: string; label: string; centroid: [number, number]; bbox: number[]; rings: number[][][]};

/** All times in seconds from the start of the video. */
export type Timing = {
  duration: number;
  items: number[];       // entry time of each clue / neighbor / card / anchor, in order
  choicesIn: number;     // A/B/C chips appear
  infoComplete: number;  // everything the viewer needs is fully on screen (end of last entry animation)
  reveal: number;        // answer moment (a musical downbeat)
  explain: number;       // explanation text
  cta: number;           // closing card
};

export type StyleTokens = {
  id: string; version: number; game: Game; summary: string;
  bg: string; bg2: string; fg: string; muted: string; line: string; card: string;
  accent: string; accent2: string; good: string; bad: string;
  fontDisplay: string; fontBody: string; fontNumber: string;
  sfx: {item: SfxName; choices: SfxName; think: SfxName; reveal: SfxName; explain?: SfxName; cta: SfxName};
};

export type LibraryEpisodeProps = {
  episodeId: string;
  styleId: string;
  q: Question;
  timing: Timing;
  geo: GeoCountry[];              // countries a map in this episode may draw (empty when unused)
  music: {bed: string; volume: number} | null;   // file under public/episodes/music
  sfxVolume: number;
  durationInFrames: number;
  showSafeArea?: boolean;         // review overlay only; never in a delivered render
};
