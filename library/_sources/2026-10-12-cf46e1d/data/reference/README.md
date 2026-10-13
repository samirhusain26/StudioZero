# Country reference snapshots (M0.4)

`fetch_data.py` validates `data/countries_enriched.csv` against these pinned files before it publishes a generation. It never downloads anything. Validation rules, tolerances and the allowlist policy are documented in [`docs/SCALAR.md`](../../docs/SCALAR.md#data-sources-and-validation).

| File | Source | Retrieved | As-of |
|---|---|---|---|
| `world_bank.csv` | World Bank World Development Indicators API, `https://api.worldbank.org/v2/country/all/indicator/<ID>?format=json&mrnev=1&per_page=500` (most recent non-empty value per country). Dataset `lastupdated` 2026-07-13. | 2026-09-25 | See `year` column. `SP.POP.TOTL`: 2025 for all 194 countries. `AG.SRF.TOTL.K2`: 2023 for all 194. `NY.GDP.MKTP.CD` / `NY.GDP.PCAP.CD`: 2025 for 181, 2024 for 6, and one each 2023, 2022, 2020, 2018, 2015 and 2011. |
| `cia_factbook.csv` | CIA World Factbook, via the `factbook/factbook.json` mirror at commit `144d6977b2b01ac1cbd220de754c0a005616760b` (https://github.com/factbook/factbook.json). The CIA withdrew the Factbook in February 2026, so this is the final published edition. | 2026-09-25 | Final Factbook edition (early 2026). |
| `allowlist.json` | Maintained here. It records deliberate game definitions that differ from the references, each with a reason. It also lists allowed duplicate display names (homonyms). | n/a | n/a |
| `build_reference.py` | Rebuilds both CSVs from raw downloads. Usage is in its docstring. | n/a | n/a |

## Field mapping

| Game field | Reference | Definition |
|---|---|---|
| `population` | World Bank `SP.POP.TOTL` | Total population, de facto residents. |
| `GDP` | World Bank `NY.GDP.MKTP.CD` | GDP, current US$. |
| `gdp_per_capita` | World Bank `NY.GDP.PCAP.CD` | GDP per capita, current US$. |
| `area` | World Bank `AG.SRF.TOTL.K2` | Surface area in km², land plus inland water. |
| `is_landlocked` | Factbook Geography → Coastline | "landlocked". A multi-part entity counts as landlocked only if every part is. |
| `border_countries_count` | Factbook Geography → Land boundaries → border countries | Distinct game countries plus Kosovo, mapped from Factbook names by `build_reference.py`. The West Bank and the Gaza Strip both map to Palestine. French Guiana maps to France. Gibraltar and the Guantanamo base are excluded. |
| `timezone_count` | Factbook Government → Capital → time difference / time zone note | The stated "N time zones" count if present. Otherwise the number of distinct UTC offsets named. |
| `government_type` | Factbook Government → Government type | The prose is mapped onto the game's eight categories by `map_government_type()` in `fetch_data.py`. |
| `Capital/Major City` | Factbook Government → Capital → name | Compared after accent/case folding. Parentheticals, "City"/"City of"/"District" and a trailing ", Country" are dropped. The value may match any listed capital. |
| `driving_side` | Not published in the Factbook snapshot | Not validated. It is a hidden field that gameplay does not use. |

Palestine (`PSE`) is read from the Factbook's West Bank (`we`) and Gaza Strip (`gz`) entries. The Factbook gives Palestine no capital or government type, so those two fields are not validated for it. The World Bank has no data for Vatican City and no GDP data for North Korea. Those values are reported as unvalidated advisories.
