# Scalar marketing

Quiz videos for scalargame.com and the Raspberry Pi system that publishes them. Full context, commands and rules: [AGENTS.md](AGENTS.md).

| Folder | Runs on | What |
|---|---|---|
| [studio/](studio/pipeline/README.md) | Mac | Remotion project and the generation pipeline: frozen game data → checked questions → rendered, QA'd videos → `batch.json` |
| [publisher/](publisher/docs/PI_UI.md) | Pi | Publishing runtime, private management UI (source in `publisher/ui`, committed build in `publisher/app/static`), installers and units |
| [contract/](contract/BATCH_CONTRACT.md) | both | Batch contract v1 and its validator `library_contract.py` |
| `library/` | Mac | Batches (`batch.json` tracked; media local) and frozen source snapshots |

Status (8 October 2026): the Pi UI is installed and publishing is paused. See the [publishing plan](publisher/docs/PUBLISHING_PIPELINE_PLAN.md) and [platform matrix](publisher/docs/PLATFORM_MATRIX.md). The restructure is tracked in [docs/REBUILD_PLAN.md](docs/REBUILD_PLAN.md).

```bash
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
python3 contract/library_contract.py validate library/<batchId>
node studio/pipeline/render.mjs --batch=<batchId>
```

Upload a finalized batch to the Pi UI by hand: `batch.json`, then every file in `videos/` and `covers/`.
