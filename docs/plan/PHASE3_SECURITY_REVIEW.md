# Phase 3 security review (2026-10-12)

Scope: the new surfaces of Phase 3:
- the motion asset route (`ui_server.py` `get_motion_manifest` / `get_motion_asset` / `ranged`, `ui_assets.py`, `publisher/motion-assets.json`);
- the Studio proxy (`ui_server.py` `studio()`, `publisher/app/studio_proxy.py`, `scalar-social-studio-proxy.service`, `studio-worker.sh`);
- the story worker agent (`engines/story/src/agent.py`, `scripts/agent-token.py`, `scripts/install-agent.sh`);
- uploads of browser-made media, and the CSP change.

Method: an independent read-only review (a separate agent, which verified agent behaviour against `create_app` in a temp dir), then fixes with tests. Threat model: the Pi is the trusted publisher, holding the session and the publishing credentials. The laptop worker is **less** trusted than the Pi: it runs LLM pipelines whose output (ids, file names, artifacts) is attacker-influenced through briefs. Every Pi UI route needs the owner's session.

## Findings and resolution

| # | Severity | Finding | Resolution |
|---|---|---|---|
| F1 | Medium | The worker chose the Content-Type of `/api/studio/*` responses, which are served from the Pi's origin. An artifact `x.html` with `<script src="x.js">` (both served as HTML/JS) would run as `script-src 'self'` on the Pi UI, with the session cookie: full control of approvals and the schedule. The UI also linked "Open" to any non-media file. | Fixed. `ui_server.studio()` no longer passes `Content-Type` through. JSON routes are `application/json`; worker files get a type from a fixed suffix list (mp4, jpg/jpeg, png, json, txt), and anything else is `application/octet-stream` with `Content-Disposition: attachment`. Every studio response carries `Content-Security-Policy: sandbox; default-src 'none'; frame-ancestors 'none'`. The agent serves only those suffixes, with explicit types. The UI links "Open" only for text and JSON. Tests in `test_studio_proxy.py` (html, js, svg and no-extension files become sandboxed downloads) and `test_agent.py`. |
| F2 | Low | Non-ASCII names made projects whose ids the API refuses (`Café_ünï`): not reachable, runnable or deletable from Studio; through the Pi a 500. | Fixed: `create` refuses names whose id is outside `[A-Za-z0-9_-]{1,120}` (422). Test. |
| F3 | Low | Model-written `character_id` / `location_slug` / `location_id` became file names unchecked; a prompt-injected brief could write `*_layout.json` / `*_reference.png` outside the project (only with paid runs on). | Fixed: `steps.slug_part()` (`[A-Za-z0-9_-]{1,64}`) guards every such path in casting, world builder, set designer and scene generator. Test. |
| F4 | Low | The files route served `project.json` and `pipeline_state.json` (absolute laptop paths, unredacted errors); JSON previews were unredacted. | Fixed: `project.json`, `pipeline_state.json` and `spend_ledger.json` are never served; served JSON/text and previews go through `_redact` (engine folder → `…`, home → `~`). Test. |
| F5 | Low | A signed-in Pi session can raise the budget cap (`PUT /studio/settings`, up to $1000) and recap estimates price nothing (LLM/TTS are unpriced), so the budget check is not an independent limit; the random-idea confirmation is a fixed string. | Accepted for now, documented. The estimate/confirm flow prevents accidental spend by the owner; it is not a defence against someone holding the owner's session (who could also approve and publish). The real gate is on the laptop: paid work is off unless the agent starts with `STUDIO_AGENT_ALLOW_PAID=1`. Pricing LLM/TTS calls is an open story-engine item (plan §14); revisit before enabling paid runs. |
| F6 | Low | `agent-token.py --send-to-pi` put `--url`/`--addr` unquoted into the ssh remote command (root shell on the Pi parses them before validation). Only the operator's own arguments reach it. | Fixed: `shlex.quote` on both. |
| F7 | Low (quality) | The Pi re-measures browser uploads (hash, size, codec, pixel format, aspect, audio format, fast start, duration, fps) but trusts the browser's loudness, true peak, silence and black-frame QA; covers are checked by magic bytes. | Accepted, documented: the uploader is the authenticated owner and the batch is reviewed and approved per episode. A Pi-side `ebur128` / `blackdetect` pass would decode on a Pi Zero; candidate for Phase 4 alongside the v2 validator. |
| F8 | Low | The agent parsed JSON bodies before checking auth (unauthenticated 422 with the parse error); the proxy's `Content-Length` check accepted non-ASCII digits (`²`), crashing the handler (worker-only input); the proxy has per-operation timeouts (30–60 s) but no overall deadline. | Fixed: the agent checks the token in a middleware before routing or parsing (401 first); the proxy requires ASCII digits. The missing overall deadline is accepted: only signed-in UI requests reach the proxy, one worker, capped at `MemoryMax=48M`. |

## Checked and fine

- **Asset route:** the route regex and the manifest allowlist must both match; `resolve()` + `is_relative_to` stops symlink escapes and the size must equal the manifest's; both endpoints need the session; Range digits capped at 15, 416 for suffix 0, start > end, start ≥ size or multiple ranges; nothing buffered; immutable caching keyed by version; 304 without a body.
- **Proxy / SSRF:** origin-form targets only (`//` and absolute URLs refused); allowlisted routes, `..` segments refused, every query key and value regex-checked; the UI decodes `%2e%2e` / `%3F` first and the proxy re-checks; host, IP and port fixed by the Pi-local drop-in; TLS with SNI and certificate checks; `IPAddressDeny=any` except the worker's address.
- **Smuggling:** both hops refuse `Transfer-Encoding` and need a digits-only `Content-Length`; the UI re-serializes request JSON; a fresh connection per request; `http.client` refuses CR/LF in the path and in `Range`.
- **Token handling:** systemd credential (never in the environment, arguments or logs; the proxy logs route names only); worker 401 → 502; redirects and `Set-Cookie` never passed on; `studio-worker.sh` writes the token with the shell's `printf` builtin; the laptop token file must be 0600; `hmac.compare_digest`.
- **Agent:** every route needs the token (now also before routing); no docs/OpenAPI; files and renders paths resolved and contained; deletes take regex-checked ids and `rmtree` refuses symlinks; `SettingsBody` ignores unknown keys and refuses NaN/Infinity; estimate tokens are HMAC'd over the project's `updated_at`, so one cannot be reused after a run; one run at a time.
- **Uploads:** server-side SHA-256 and byte checks, size caps, ffprobe re-measure, Content-Type gate, `O_EXCL` temp files.
- **CSP:** `'wasm-unsafe-eval'`, `worker-src blob:` and `connect-src blob:` only matter once same-origin script already runs; no practical weakening.
- **UI:** no `dangerouslySetInnerHTML`; URLs built with `encodeURIComponent`; `JsonView` renders text only; `target=_blank` with `rel="noopener noreferrer"`.

## Round 2

A second read-only pass over the fixes confirmed F1, F2, F3 and F6, and the agent's token check (before routing and body parsing; 404, `OPTIONS` and `/docs` all 401). It found two gaps, both low and both fixed with tests:
- **F4, part 2:** the Mac's disk ignores case, so `Project.JSON` / `PIPELINE_STATE.json` got past the private-file list. Now compared lower-cased, on the files route and in the artifact listing.
- **F8, part 2:** a 5000-digit `Content-Length` passed the digits check and then made `int()` raise (Python's 4300-digit limit), killing the proxy handler. The proxy (requests and worker responses) and the UI now accept `\d{1,15}` only (400/413 otherwise).

Status: resolved, except F5 and F7 (accepted with reasons above) and the proxy's missing overall deadline (F8, accepted).
