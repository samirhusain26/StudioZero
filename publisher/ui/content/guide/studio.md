# Studio

Studio is where batches are made, for every project: **Originals** (the studio's own recaps and animated shorts) and **Scalargame** (quiz videos for scalargame.com). It is the Make step of the loop. The Pi only serves this page, stores the library, approves and publishes; it never makes videos.

- **Overview** lists each project with its formats, engine, budget, mix and runway (how far the approved schedule reaches). Budgets and target mix shares are yours to set; until you do, the page says so instead of showing a number.
- **Make a batch** builds the prompt for Claude Code from the studio catalog: only formats, styles and music the engines can make are offered. Pick the project with the chips at the top. Every prompt ends with the same safety lines (no finalize or upload without your approval, facts only from frozen sources, credits for every asset, paid generation only within budget after you confirm a cost estimate). See [Next batch](#next-batch).
- **Engines**: Motion (Scalargame's quiz videos) runs in the browser of the device you use; Story (Originals) runs on the laptop worker, and paid services and their keys stay there. See [Story jobs](#story-jobs).

Originals batches use contract v2, which this Pi validates only after the Phase 4 update; until then Make a batch builds the prompt and the checklist, and the upload step says it is not available yet.

## Export in the browser

Studio › **Export** makes a Scalargame batch's videos on the device you are using, with the same templates as the Mac (Chrome or Safari 26 and newer; a laptop is best for a whole batch, a phone can do one episode at a time).

1. Claude prepares the batch as usual up to the frozen job inputs, then runs `node engines/motion/pipeline/web-jobs.mjs --batch=<batchId> --set=questions-<set>`. It writes `library/<batchId>/review/web-jobs.json`. Open that file in step 1; it may name answers, so it stays in this browser and is never uploaded.
2. Preview any episode, then export. Each episode is rendered, its audio mastered to −14 LUFS with true peak at or below −1 dBTP, and the file checked like the Mac does (codec, size, frame rate, length, loudness, true peak, audio sync, silence and black frames). A failed check blocks the upload. Finished episodes are kept in this browser; an interrupted one starts again.
3. When every episode passed, press **Finalize and upload**. That is your approval to finalize: batch.json is written with the same code as the Mac and uploaded with the videos and covers, and the Pi validates everything again. Then review and approve the episodes in the Library as usual.

The Mac's `render.sh` stays available as the house-master path.

## Story jobs

Studio › **Story jobs** drives the story engine on the laptop (the *story worker*): narrated recaps and animated series for Originals. The Pi only passes requests through to the worker over the tailnet; it never runs the engine, and it never holds a key. When the laptop sleeps or the worker is not running, the page says **Worker offline**: wake the laptop, then press Try again.

- **New job**: a recap (a movie name or a story idea) or a series (name, brief, 1–10 episodes). Creating a job costs nothing. *Surprise me* asks Gemini for a series idea (one short text request, after you confirm).
- **Run** (Start, Continue or Retry) first shows the cost estimate the worker computed: priced video clips, the calls it cannot price in advance, what the job has spent and its budget. Nothing paid starts until you confirm it, and the worker checks the estimate and the budget again. Paid runs stay switched off on the worker until the open engine bugs are fixed.
- **Recap review**: after the script is written the run stops. Edit the JSON if needed, then *Approve script*; Continue narrates and renders exactly that script.
- **Failed scene** (series): read the error, then Retry, edit the prompt, change the video model for this job, or skip the scene. Each choice shows a new estimate before anything runs.
- **Cancel run** stops before the next paid step (in the scene generator, before the next clip is ordered).
- **Steps**: pre-production (writer, screenwriter, casting, world builder), then per episode director, set designer, scene generator and editor. Click a finished step to see its files: character sheets, shot lists, images and clips.
- **Renders** lists every finished story video on the laptop with its cost and credits. **Story settings** sets the text, image and voice models, the video tier and model, the budget per job and the auto-downgrade; a preset sets them all at once. Keys stay in the laptop's `.env`: the page only says whether each is set.

Setting up the worker (once, on the laptop and the Pi) is described in the story engine's docs (`engines/story/docs/HEADLESS.md`).
