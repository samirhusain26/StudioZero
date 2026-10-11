/** Metadata for the official local-date Daily set. Optional modes are not games in this registry. */
export const OFFICIAL_DAILY_GAMES = [
  {
    id: 'scalar',
    name: 'Scalar',
    dailyName: 'Scalar Countries',
    href: '/scalar',
    aboutHref: '/about/scalar',
    description: 'Deduce a country from numerical clues.',
    duration: '3–6 min',
    specialization: 'Geography and estimation',
    structuredGenre: 'Deduction puzzle',
    hasThemedFreePlay: true,
    accent: '#14B8A6',
    mark: '◎',
    answerEpoch: '2026-03-01',
  },
  {
    id: 'continuum',
    name: 'Continuum',
    dailyName: 'Continuum',
    href: '/continuum',
    aboutHref: '/about/continuum',
    description: 'Place countries along a hidden scale.',
    duration: '2–4 min',
    specialization: 'Numerical ordering and estimation',
    structuredGenre: 'Ranking puzzle',
    hasThemedFreePlay: true,
    accent: '#F472B6',
    mark: '↕',
    answerEpoch: '2026-03-01',
  },
  {
    id: 'whenabouts',
    name: 'Whenabouts',
    dailyName: 'Whenabouts',
    href: '/whenabouts',
    aboutHref: '/about/whenabouts',
    description: 'Place five events on the timeline.',
    duration: '3–5 min',
    specialization: 'Historical deduction',
    structuredGenre: 'History puzzle',
    hasThemedFreePlay: true,
    accent: '#EAB308',
    mark: '◷',
    answerEpoch: '2026-04-19',
  },
  {
    id: 'tectonic',
    name: 'Tectonic',
    dailyName: 'Tectonic',
    href: '/tectonic',
    aboutHref: '/about/tectonic',
    description: 'Build the world on a tactile 3D globe.',
    duration: '3–5 min',
    specialization: 'Visual geography and spatial reasoning',
    structuredGenre: 'Geography puzzle',
    hasThemedFreePlay: false,
    accent: '#F2A154',
    mark: '⌘',
    answerEpoch: '2026-07-11',
  },
] as const;

export type DailyGameKey = (typeof OFFICIAL_DAILY_GAMES)[number]['id'];
export type OfficialDailyGame = (typeof OFFICIAL_DAILY_GAMES)[number];

export const OFFICIAL_DAILY_GAME_KEYS: readonly DailyGameKey[] = OFFICIAL_DAILY_GAMES.map(({ id }) => id);
export const OFFICIAL_DAILY_GAME_COUNT = OFFICIAL_DAILY_GAMES.length;
const COUNT_WORDS: readonly string[] = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
export const OFFICIAL_DAILY_GAME_COUNT_WORD = COUNT_WORDS[OFFICIAL_DAILY_GAME_COUNT] ?? String(OFFICIAL_DAILY_GAME_COUNT);

export function isOfficialDailyGame(value: string | undefined): value is DailyGameKey {
  return value !== undefined && OFFICIAL_DAILY_GAME_KEYS.includes(value as DailyGameKey);
}

export function getOfficialDailyGame(game: DailyGameKey): OfficialDailyGame {
  const metadata = OFFICIAL_DAILY_GAMES.find((entry) => entry.id === game);
  if (!metadata) throw new RangeError(`Unknown official Daily game: ${game}`);
  return metadata;
}
