/** Canonical date-seeded selection primitives shared by the live games and prerender. */
export function mulberry32(seed) {
  return function next() {
    let t = (seed += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i++) hash = ((hash * 31) + value.charCodeAt(i)) >>> 0;
  return hash;
}

/**
 * Entities added after launch join the Daily answer pool on their cutover
 * date, so every earlier pick keeps its original pool. They are guessable
 * immediately. Mirrored by DAILY_POOL_CUTOVERS in fetch_data.py.
 */
export const DAILY_POOL_CUTOVERS = { countries: { TWN: '2026-10-01' } };

export function getDailyEntity(category, entities, date) {
  const rand = mulberry32(hashString(`${date}:${category}`));
  const cutovers = DAILY_POOL_CUTOVERS[category] ?? {};
  const sorted = entities
    .filter(entity => !(cutovers[entity.id] > date))
    .sort((a, b) => a.id.localeCompare(b.id));
  return sorted[Math.floor(rand() * sorted.length)];
}

export function selectContinuumDailyMetric(date, metrics) {
  const rand = mulberry32(hashString(`${date}:continuum`));
  return metrics[Math.floor(rand() * metrics.length)];
}

/**
 * Pinned Tectonic seed pool: the largest third of countries with at least
 * three neighbors, derived from the original 194-country globe. Pinned so
 * globe data changes (new countries, neighbors or geometry) never move a
 * published or future Daily seed.
 */
export const TECTONIC_SEED_POOL = [
  'RUS', 'CHN', 'BRA', 'AUS', 'IND', 'ARG', 'KAZ', 'COD', 'DZA', 'MEX', 'SAU', 'IDN', 'SDN', 'LBY',
  'IRN', 'PER', 'TCD', 'ZAF', 'MLI', 'AGO', 'NER', 'COL', 'ETH', 'BOL', 'MRT', 'EGY', 'TZA', 'VEN',
  'NGA', 'PAK', 'NAM', 'MOZ', 'TUR', 'CHL', 'ZMB', 'MMR', 'AFG', 'FRA', 'SDS', 'CAF', 'MDG', 'KEN',
  'BWA', 'UKR', 'THA', 'ESP', 'SOM', 'CMR', 'TKM', 'PNG', 'UZB', 'IRQ', 'PRY', 'ZWE',
];

export function pickTectonicSeedCountry(countries, rand) {
  const all = [...countries];
  const byId = new Map(all.map(country => [country.id, country]));
  let pool = TECTONIC_SEED_POOL.map(id => byId.get(id)).filter(Boolean);
  if (pool.length === 0) {
    // Country subsets without any pinned seed (e.g. test fixtures) use the original rule.
    const candidates = all
      .filter(country => country.neighbors.length >= 3)
      .sort((a, b) => b.areaSr - a.areaSr);
    pool = candidates.slice(0, Math.max(1, Math.floor(candidates.length / 3)));
  }
  return pool[Math.floor(rand() * pool.length)];
}
