# Review stage: frames, stills, sheets

All review output goes in `library/<batchId>/review/` (never uploaded) while the batch is **not** finalized. Run Remotion from `engines/motion/`.

## 1. Review sheet

```bash
node engines/motion/pipeline/review.mjs --batch=<batchId>     # → review/index.html, frames/<episodeId>/*.png, validator.json
```

Run it after `batch.mjs` has written `batch.json` (SKILL step 7); it refuses a finalized batch. Rehearsals add `--dir=library/_dev/<id>`.

Its frames are rendered at **half scale** (`--scale=0.5`): fine for layout, not for maps or small labels.

## 2. Full-resolution stills (maps and every changed template)

For every Tectonic episode and every Scalar episode (all Scalar formats show a locator map after the reveal), render full-size stills at the cover, the reveal and the explanation, and read each PNG. Frame = seconds × 30 from `props.json` → `timing`: cover `infoComplete + 0.5`, reveal `reveal + 1.5`, explanation `explain + 1` (24 s formats today: 240, 465, 570).

```bash
cd studio
P=../library/<batchId>/review/jobs/<episodeId>/props.json
mkdir -p ../library/<batchId>/review/stills
for fr in <cover> <reveal> <explain>; do
  ./node_modules/.bin/remotion still src/index.ts LibraryEpisode ../library/<batchId>/review/stills/<episodeId>-f$fr.png --props=$P --frame=$fr --log=error
done
```

Timings are in each `props.json` → `timing` (seconds). For a safe-area overlay, copy a props file to `library/_dev/` and add `"showSafeArea": true`.

## 3. Sheets (PIL, not ffmpeg)

Remotion's bundled ffmpeg has no `tile` filter. Use PIL:

```bash
engines/motion/.venv/bin/python engines/motion/render/contact.py library/<batchId>/review/<episodeId>-sheet.png library/<batchId>/review/frames/<episodeId>/*.png   # one row; ignore its old red zones
engines/motion/.venv/bin/python .claude/skills/video-batch/covers_sheet.py library/<batchId> library/<batchId>/review/covers.png
```

## 4. Frame checklist (every episode)

- Hook readable at 0.4 s; question ≤ 3 lines; primary text ≥ 56 px, nothing essential < 30 px (frames are seen at ~36 % on a phone).
- Essential content inside x 90–900, y 270–1530.
- Everything needed is on screen by `infoComplete` and stays still until `reveal`; thinking window ≥ 6 s.
- **No spoiler before the reveal:** the correct choice looks exactly like the others; no highlight, order, colour, size or label gives it away. The cover (frame at `infoComplete + 0.5 s`) is spoiler-free.
- Reveal is unambiguous; every choice marker stays on screen after it (2026-10-b01: guess-the-year A/C answers pushed a marker off-screen).
- Maps (full-res stills): enclaves visible (Lesotho, San Marino, Vatican City), no touching or stacked labels (2026-10-b01: Malawi/Mozambique, Gabon), north up, real shapes.
- Charts start at zero on one labelled scale; numbers match the explanation.
- Explanation says how the clues lead to the answer (2026-10-b01: the Uzbekistan explanation did not).
- Candidate elimination: each clue removes at least one choice (`evidence.checks.eliminatedPerClue` has no empty entry).
- End card "Play a new puzzle · scalargame.com" inside the safe area; branding subtle; no personal credit.
- Watch every MP4 muted at phone size (`review/index.html`); you cannot listen, so ask Samir to watch each once with sound at Checkpoint 3 (render.mjs has already checked loudness, true peak, silence gaps and sync).

## 5. Per-episode table (for Checkpoint 3)

Write `library/<batchId>/review/checkpoint3.md` like `library/2026-10-b01/review/checkpoint3.md`: episode, question, answer (letter and text), seconds, MB, LUFS, true peak, validator result, plus a line per issue found and what was done about it. Values come from `review/jobs/<episodeId>/status.json` and `review/validator.json`, never typed by hand.
