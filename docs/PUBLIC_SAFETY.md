# Public safety

This repository is public (GitHub `samirhusain26/StudioZero`), and whoever can push to `main` decides what the Pi runs. These rules are permanent; `CLAUDE.md`/`AGENTS.md` repeat them.

## Never committed

- Credentials, tokens, passcodes, deploy keys: `.env*` (except `.env.template` placeholders), `env.yaml`, `assets/creds/`, `publisher/config.json`, key files.
- Media and renders: anything under `out/`, `output/`, `.audio-work/`, review folders, QA screenshots (some show tokens). Batch videos, covers and masters stay in `library/<batch>/` locally (only `batch.json` is tracked).
- Music or sound effects without a recorded free licence (`beds.json` entry with a CC0/CC BY licence, or a procedural generator).
- Pi and tailnet addresses: `*.ts.net` names, IP addresses. Docs use the ssh alias `scalar-pi` and placeholders such as `https://<pi>.<tailnet>.ts.net`. The Pi's short LAN name and login user (`scout`) appear in historical notes and one-off scripts; that is accepted, the tailnet name is not.
- Personal details: e-mail addresses, phone numbers, home addresses, home-directory paths (`/Users/<name>`). Two vendor strings in the committed UI bundle are allowed by name: Remotion's public support address (`…@remotion.dev`) and Emscripten's virtual `/home/web_user` in a WebAssembly encoder.
- Platform account IDs (Buffer channel IDs, provider IDs, Page IDs, Bluesky DID, Cloudflare account ID): they live only in the Pi's root-owned `/etc/scalar-social/config.json` under `identities`; `publisher/config.example.json` and tests carry fakes.
- Unreleased or future game answers, and private game-repo content beyond the snapshot rules, **except** `library/_sources/**`: the owner decided on 2026-10-11 that the frozen snapshots (including future Whenabouts puzzles, which the live site serves anyway) may be public.

## Required

- `python3 tools/public_safety_check.py` passes before every commit that will be pushed and before every push (it checks tracked files plus untracked files that are not ignored). It is stdlib only and prints masked findings only.
- On the owner's Mac a private hash list (`~/.config/studiozero/private-id-hashes.txt`, never in the repo) holds `sha256(value)[:16]` of the real IDs, the tailnet name and private e-mail addresses; the check reads it automatically, so a real ID is caught even when it looks like an ordinary number.
- `config.example.json` carries placeholders only.
- Paid generation never runs from CI; there is no deploy workflow, and no workflow may upload anything.
- History is never rewritten: what was ever pushed stays public, so the check runs before the push, not after.

## History notes

- The old StudioZero history never contained a credential (audited 2026-10-11). It does contain the story engine's stock fallback clips and Pixabay-style music files, removed from the tree in October 2026; removing them from history would need a rewrite, which these rules forbid.
- The marketing history (private repository `scalargame-marketing-plan`, archived) was imported as one audited commit; its earlier commits, with operational records, stay private.
