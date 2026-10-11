# Credits and asset licences

The source code is MIT-licensed (see `LICENSE`, including what it does not cover). Assets in this repository keep their own licences:

| Asset | Where | Licence | Record |
|---|---|---|---|
| Music beds (90 calm beds) | `studio/public/episodes/music/*.m4a` | CC0 1.0: HoliznaCC0 and other OpenGameArt artists | one entry per bed in `studio/public/episodes/music/beds.json` (track, source file, licence); corpus notes in `studio/music/TRACKS.md`, `studio/music/catalog.json` |
| Sound effects | `studio/public/sfx/*.wav` | made procedurally by `studio/tools/make_sfx.py` (no samples) | the generator itself |
| Fonts: Fraunces, Geist Mono, IBM Plex Mono, Montserrat, Nunito | `studio/public/episodes/fonts/` | SIL Open Font License 1.1 | `studio/public/episodes/fonts/licenses/` |
| Map geometry | game data in `library/_sources/` and the episode kit | Natural Earth, public domain ("Made with Natural Earth") | `studio/music/rights.json` (approved sources) |
| Country reference data | `library/_sources/*/data/reference/` | World Bank Open Data (CC BY 4.0: attribution required) and CIA World Factbook (public domain) | `data/reference/README.md` in each snapshot |
| Game data and puzzles | `library/_sources/` | scalargame.com (the owner's game), frozen snapshots of committed files | each snapshot's `manifest.json` |

Not in this repository (local to the owner's Mac): the owner's six Gemini-generated music beds and source tracks, downloaded SFX packs, the story engine's stock fallback clips and music (no source or licence recorded), and every render.

Published videos list their own per-asset credits in `batch.json` (and from contract v2, `credits[]` with licences). Recaps that use TMDB data or images carry the notice "This product uses the TMDB API but is not endorsed or certified by TMDB".
