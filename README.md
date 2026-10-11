# StudioZero

The studio behind the **@studiozeroflow** social accounts: it makes short vertical videos on a Mac and publishes them from a Raspberry Pi. Each **project** has its own rules, sources and voice; each **engine** knows how to make a kind of video; the **publisher** owns the channels. Full context, commands and rules: [AGENTS.md](AGENTS.md). Running plan: [docs/STUDIO_PLAN.md](docs/STUDIO_PLAN.md).

| Folder | Runs on | What |
|---|---|---|
| [studio/](studio/pipeline/README.md) | Mac | Motion engine (Remotion) and the Scalargame pipeline: frozen game data → checked questions → rendered, QA'd videos → `batch.json`. Moves to `engines/motion/` after the Pi cutover |
| [engines/story/](engines/story/README.md) | Mac | Story engine (Python): `recap` (stock footage, TTS, captions) and `series` (multi-model AI animation with a budget guard) |
| [publisher/](publisher/docs/PI_UI.md) | Pi | Publishing runtime, private management UI (source in `publisher/ui`, committed build in `publisher/app/static`), installers and units |
| [contract/](contract/BATCH_CONTRACT.md) | both | Batch contract and its validator `library_contract.py` |
| `library/` | Mac | Batches (`batch.json` tracked; media local) and frozen source snapshots |
| [tools/](tools/public_safety_check.py) | Mac | Repository tools, starting with the public-safety check |

Projects: **originals** (P0: recaps and AI shorts on the story engine) and **scalargame** (P1: quiz videos for [scalargame.com](https://www.scalargame.com) on the motion engine).

```bash
python3 tools/public_safety_check.py                          # before every push
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
python3 contract/library_contract.py validate library/<batchId>
```

Code is MIT-licensed; assets keep their own licences ([CREDITS.md](CREDITS.md)). Public-safety rules: [docs/PUBLIC_SAFETY.md](docs/PUBLIC_SAFETY.md).
