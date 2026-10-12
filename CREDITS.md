# Credits and asset licences

The source code is MIT-licensed (see `LICENSE`, including what it does not cover). Assets in this repository keep their own licences:

| Asset | Where | Licence | Record |
|---|---|---|---|
| Music beds (90 calm beds) | `engines/motion/public/episodes/music/*.m4a` | CC0 1.0: HoliznaCC0 and other OpenGameArt artists | one entry per bed in `engines/motion/public/episodes/music/beds.json` (track, source file, licence); corpus notes in `engines/motion/music/TRACKS.md`, `engines/motion/music/catalog.json` |
| Sound effects | `engines/motion/public/sfx/*.wav` | made procedurally by `engines/motion/tools/make_sfx.py` (no samples) | the generator itself |
| Fonts: Fraunces, Geist Mono, IBM Plex Mono, Montserrat, Nunito | `engines/motion/public/episodes/fonts/` | SIL Open Font License 1.1 | `engines/motion/public/episodes/fonts/licenses/` |
| Caption font: Fraunces Black (latin subset, WOFF, from Fontsource 5.3.0) | `engines/story/fonts/` | SIL Open Font License 1.1 | `engines/story/fonts/fraunces-LICENSE` |
| Map geometry | game data in `library/_sources/` and the episode kit | Natural Earth, public domain ("Made with Natural Earth") | `engines/motion/music/rights.json` (approved sources) |
| Country reference data | `library/_sources/*/data/reference/` | World Bank Open Data (CC BY 4.0: attribution required) and CIA World Factbook (public domain) | `data/reference/README.md` in each snapshot |
| Game data and puzzles | `library/_sources/` | scalargame.com (the owner's game), frozen snapshots of committed files | each snapshot's `manifest.json` |

Not in this repository (local to the owner's Mac): the owner's six Gemini-generated music beds and source tracks, the CC0 source tracks behind `engines/motion/music/catalog.json` (story recaps use them as background music, credited per track with artist and page), downloaded SFX packs, the story engine's old stock fallback clips and music in `engines/story/assets/` (no source or licence recorded; the engine no longer uses them), and every render.

Published videos list their own per-asset credits in `batch.json` (and from contract v2, `credits[]` with licences). Recaps that use TMDB data or images carry the notice "This product uses the TMDB API but is not endorsed or certified by TMDB".
