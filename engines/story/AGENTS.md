# StudioZero Agent Guide

> Part of the StudioZero studio: this is the **story engine** (`engines/story`). Run every command from this folder. Retired in October 2026: the Google Sheets batch runner, Drive/iCloud upload, Groq captions, the app launcher, Cloud Run, StudioZero.app and the legacy Vertex client. Studio rules (public repository, no paid generation without the owner's OK): `../../AGENTS.md`.

StudioZero is a Python pipeline for producing vertical social video through stock-footage and multi-step animation routes.

## Read first

- Read `CLAUDE.md`, `README.md`, and the relevant document under `docs/` before changing a pipeline stage.

## Working rules

- Preserve checkpointed pipeline state, retry/edit/skip recovery, budget enforcement, model-tier fallback, and resumability.
- Keep stage inputs and outputs validated with the existing Pydantic models and avoid passing unstructured state between stages.
- Treat external model, media, and upload providers as fallible; preserve useful completed work when one fails.
- Never commit API keys, service-account credentials, generated private media, or provider responses containing sensitive input.
- Do not start paid generation, batch production, or uploads without explicit authorization.

## Verify

- Prefer a low-cost or mocked smoke path for changed stages: `.venv/bin/python -m unittest discover -s tests -v` runs both routes at $0 (`docs/HEADLESS.md`).
- Validate resume behavior when changing persisted pipeline state.
