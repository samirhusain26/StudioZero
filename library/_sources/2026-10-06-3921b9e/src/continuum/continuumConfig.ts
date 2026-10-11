/**
 * Continuum-approved metrics per category.
 *
 * A valid Continuum metric must be:
 *   1. Purely numeric and continuous (no booleans, strings, categoricals).
 *   2. Have high value uniqueness (>65%) so sequential ordering isn't arbitrary.
 *   3. Have reasonable data coverage (>70% non-null) to support a 10-card round.
 *
 * Data audit (2026-04):
 *   Countries (195 entities) — excluded: border_countries_count (6%), timezone_count (5%),
 *     olympics_hosted_count (4%), olympics_latest_year (12%), first_letter (alpha, not continuous),
 *     unesco_sites (17%), Armed Forces size (60% unique but sparse & clustered).
 *   Elements (118 entities) — excluded: group (15%), period (6%),
 *     YearDiscovered (64% unique, many same-year discoveries),
 *     ElectronAffinity (only 48% data coverage).
 */

export const CONTINUUM_METRICS: Record<string, string[]> = {
  countries: [
    'population',      // 100% unique, 195/195
    'area',            // 99% unique, 195/195
    'gdp_per_capita',  // 100% unique, 158/195
  ],
  elements: [
    'AtomicNumber',  // 100% unique, 118/118
    'Density',       // 77% unique, 118/118
    'AtomicRadius',  // 67% unique, 99/118
  ],
};
