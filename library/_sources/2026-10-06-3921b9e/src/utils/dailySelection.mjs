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

export function getDailyEntity(category, entities, date) {
  const rand = mulberry32(hashString(`${date}:${category}`));
  const sorted = [...entities].sort((a, b) => a.id.localeCompare(b.id));
  return sorted[Math.floor(rand() * sorted.length)];
}

export function selectContinuumDailyMetric(date, metrics) {
  const rand = mulberry32(hashString(`${date}:continuum`));
  return metrics[Math.floor(rand() * metrics.length)];
}

export function pickTectonicSeedCountry(countries, rand) {
  const candidates = [...countries]
    .filter(country => country.neighbors.length >= 3)
    .sort((a, b) => b.areaSr - a.areaSr);
  const pool = candidates.slice(0, Math.max(1, Math.floor(candidates.length / 3)));
  return pool[Math.floor(rand() * pool.length)];
}
