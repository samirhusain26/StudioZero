"""
Step 7 (per episode): Scene Generator — Render each director shot as a video clip.

Input:  director_shots.json + scene_starts/{char}_{loc}.png (from set_designer)
        Falls back to characters/{character_id}_reference.png if no scene start exists.
Output: episodes/episode_N/clips/scene_N.mp4
Persists: project_dir/episodes/episode_N/clips/

Supports multiple video generation providers via UnifiedVideoClient:
  - fal.ai models (Kling, Seedance, Wan)
  - Gemini API Veo (google.genai SDK)

The active model is read from config (ACTIVE_VIDEO_MODEL from settings.json, or the
worker's per-project model). Each shot is requested at the model's clip_seconds
(registry.json). Audio policy (review B3): with Config.SERIES_NATIVE_AUDIO a model
that has native audio is asked for it (and priced with it); the editor gives silent
clips a silent track.

Rate limits are enforced between requests (35 s for Gemini API Veo, 5 s for fal.ai).

Budget: spend is tracked per project in spend_ledger.json (budget_guard.SpendLedger).
Every billed attempt is recorded with the model that actually ran (after fallback or
downgrade); clips that predate the ledger are backfilled with an estimate.

Retry / override mechanism:
  - Before sending, the generator checks for clips/scene_X_override.txt.
    If present, its contents replace the default veo_prompt.
  - A skip marker at clips/scene_X.skip causes the scene to be skipped entirely.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

from src.config import Config
from src.video_models import clip_duration, get_model, estimate_cost
from src.video_client import UnifiedVideoClient
from src.budget_guard import BudgetGuard, BudgetExceeded, SpendLedger
from src.steps import StepContext, StepResult, slug_part
from src.steps.director import load_director_shots

logger = logging.getLogger(__name__)

# Seconds between requests: Veo preview models allow about 2 requests a minute; fal.ai queues
_RATE_LIMIT_GEMINI = 35
_RATE_LIMIT_FAL = 5


def _rate_limit(provider: str) -> int:
    return _RATE_LIMIT_GEMINI if provider == "gemini_api" else _RATE_LIMIT_FAL


class SceneGenerationError(Exception):
    """Raised when a scene fails, carrying enough context for a retry/edit flow."""
    def __init__(self, scene_id: int, veo_prompt: str, original_error: str):
        self.scene_id = scene_id
        self.veo_prompt = veo_prompt
        self.original_error = original_error
        super().__init__(
            f"Scene {scene_id} failed: {original_error}"
        )


def _get_scene_start_image(ctx: StepContext, character_id: str, location_id: str) -> Optional[Path]:
    """Look up the cached scene starting image for a character+location combo."""
    scene_starts_dir = ctx.project_dir / "scene_starts"
    cache_path = scene_starts_dir / f"{slug_part(character_id)}_{slug_part(location_id)}.png"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path
    return None


def _recorded_model_id(project_dir: Path) -> Optional[str]:
    """The video model a dashboard run recorded in project.json step_data, if any."""
    project_file = project_dir / "project.json"
    if not project_file.exists():
        return None
    try:
        step_data = json.loads(project_file.read_text(encoding="utf-8")).get("step_data") or {}
    except Exception:
        return None
    for data in step_data.values():
        if isinstance(data, dict) and data.get("model_id"):
            return data["model_id"]
    return None


def backfill_existing_clips(project_dir: Path, episode_number: int, ledger: SpendLedger, shots, clips_dir: Path) -> None:
    """Record clips rendered before the ledger existed, so the budget and render.json count them
    (also called by render_json when only the editor re-runs on an old project)."""
    assumed_model = _recorded_model_id(project_dir) or Config.ACTIVE_VIDEO_MODEL
    try:
        assumed_cfg = get_model(assumed_model)
    except KeyError:
        assumed_model, assumed_cfg = Config.ACTIVE_VIDEO_MODEL, get_model(Config.ACTIVE_VIDEO_MODEL)
    for shot in shots.shots:
        clip_path = clips_dir / f"scene_{shot.scene_id}.mp4"
        if not (clip_path.exists() and clip_path.stat().st_size > 0):
            continue
        if ledger.clip_entry(episode_number, shot.scene_id):
            continue
        pending = [e for e in ledger.entries_for(episode_number, shot.scene_id) if e.get("status") == "submitted"]
        if pending:
            # Billed and downloaded, but the run stopped before the entry was closed
            ledger.update(pending[-1], status="ok")
            continue
        cost = estimate_cost(assumed_model, assumed_cfg.max_duration_sec, False)
        ledger.record(
            episode=episode_number,
            scene_id=shot.scene_id,
            model_id=assumed_cfg.model_id,
            duration_sec=assumed_cfg.max_duration_sec,
            cost_usd=cost,
            status="ok",
            source="backfill",
        )
        logger.info(
            f"[scene_generator] Backfilled ledger for existing clip {clip_path.name}: "
            f"assumed {assumed_model}, ${cost:.2f}"
        )


def run(ctx: StepContext) -> StepResult:
    """Render each director shot as a video clip, sequentially."""
    shots = load_director_shots(ctx.episode_dir)
    clips_dir = ctx.episode_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Project-wide spend ledger: the budget covers every episode and every earlier run
    ledger = SpendLedger(ctx.project_dir)
    backfill_existing_clips(ctx.project_dir, ctx.episode_number, ledger, shots, clips_dir)

    # Initialize video client and budget guard with the configured model
    model_id = Config.ACTIVE_VIDEO_MODEL
    model_config = get_model(model_id)
    client = UnifiedVideoClient(model_id)
    guard = BudgetGuard(
        max_budget=Config.VIDEO_MAX_BUDGET,
        auto_downgrade=Config.VIDEO_AUTO_DOWNGRADE,
        ledger=ledger,
    )

    rate_limit_wait = _rate_limit(model_config.provider)

    artifact_paths: List[str] = []
    last_call_at: Optional[float] = None

    logger.info(
        f"[scene_generator] Episode {ctx.episode_number}: "
        f"rendering {len(shots.shots)} shot(s) via {model_config.display_name} ({model_id}), "
        f"budget: ${Config.VIDEO_MAX_BUDGET:.2f} (project spend so far: ${guard.cumulative_spend:.2f})"
    )

    def _record_attempt(scene_id: int, event: str, attempt: dict) -> None:
        """Ledger + guard bookkeeping for every attempt the client makes."""
        if event == "submitted":
            # Billed from the moment the provider accepted the job (or may have)
            attempt["ledger_entry"] = ledger.record(
                episode=ctx.episode_number,
                scene_id=scene_id,
                model_id=attempt["model_id"],
                duration_sec=attempt["duration"],
                cost_usd=attempt["cost"],
                status="uncertain" if attempt.get("uncertain") else "submitted",
            )
            guard.record_spend(attempt["cost"])
        elif "ledger_entry" in attempt:
            failed = "uncertain" if attempt.get("uncertain") else "failed"
            fields = {"status": "ok" if event == "succeeded" else failed}
            if attempt.get("error"):
                fields["error"] = attempt["error"][:300]
            ledger.update(attempt["ledger_entry"], **fields)

    for shot in shots.shots:
        # Cancel (worker agent): stop before the next scene's paid submit
        ctx.check_cancelled()
        # The client may have switched model (fallback/downgrade) on an earlier scene
        model_config = get_model(client.model_id)
        rate_limit_wait = _rate_limit(model_config.provider)
        clip_path = clips_dir / f"scene_{shot.scene_id}.mp4"
        skip_marker = clips_dir / f"scene_{shot.scene_id}.skip"
        override_file = clips_dir / f"scene_{shot.scene_id}_override.txt"

        # ── Skip marker ─────────────────────────────────────────────────────
        if skip_marker.exists():
            logger.info(f"[scene_generator] Scene {shot.scene_id} marked as skipped — omitting")
            continue

        # ── Already rendered ─────────────────────────────────────────────────
        if clip_path.exists() and clip_path.stat().st_size > 0:
            logger.info(
                f"[scene_generator] Scene {shot.scene_id} clip already exists "
                f"({clip_path.stat().st_size // 1024} KB) — skipping"
            )
            artifact_paths.append(str(clip_path))
            continue

        # ── Resolve prompt (check for user override) ────────────────────────
        if override_file.exists():
            veo_prompt = override_file.read_text(encoding="utf-8").strip()
            logger.info(
                f"[scene_generator] Scene {shot.scene_id}: using user-edited prompt override "
                f"({len(veo_prompt.split())} words)"
            )
        else:
            veo_prompt = shot.veo_prompt

        # ── Locate scene starting image (prefer set_designer output) ───────
        scene_start = _get_scene_start_image(ctx, shot.primary_character_id, shot.location_id)
        if scene_start:
            ref_image = scene_start
            logger.info(
                f"[scene_generator] Using scene start image for "
                f"'{shot.primary_character_id}' @ '{shot.location_id}'"
            )
        else:
            # Fall back to character reference if no scene start was generated
            ref_image = ctx.characters_dir / f"{slug_part(shot.primary_character_id)}_reference.png"
            logger.warning(
                f"[scene_generator] No scene start image for "
                f"'{shot.primary_character_id}' @ '{shot.location_id}' "
                f"— falling back to character reference"
            )

        if not ref_image.exists():
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=(
                    f"No starting image found for character '{shot.primary_character_id}' "
                    f"at location '{shot.location_id}'. "
                    f"Re-run the Set Designer or Casting step, or skip this scene."
                ),
            )

        # ── Collect reference images for models that support them ───────────
        # Pass scene start images as references to avoid white character sheets
        # bleeding into the video output
        reference_images = None
        if model_config.has_reference_images and scene_start:
            reference_images = [str(scene_start)]
            logger.info(
                f"[scene_generator] Passing scene start as reference image "
                f"for '{shot.primary_character_id}' @ '{shot.location_id}'"
            )

        # ── Rate-limit enforcement ──────────────────────────────────────────
        if last_call_at is not None:
            elapsed = time.monotonic() - last_call_at
            wait_needed = rate_limit_wait - elapsed
            if wait_needed > 0:
                logger.info(
                    f"[scene_generator] Rate-limit wait: {wait_needed:.1f}s remaining "
                    f"(enforcing {rate_limit_wait}s minimum between requests)..."
                )
                time.sleep(wait_needed)

        # ── Budget check ────────────────────────────────────────────────────
        native_audio = Config.SERIES_NATIVE_AUDIO
        try:
            approved_model = guard.check_budget(
                client.model_id,
                duration=model_config.clip_seconds,
                include_audio=native_audio and model_config.has_audio,
            )
            if approved_model != client.model_id:
                logger.info(
                    f"[scene_generator] Budget guard downgraded model: "
                    f"{client.model_id} -> {approved_model}"
                )
                client.switch_model(approved_model)
                model_config = get_model(approved_model)
                rate_limit_wait = _rate_limit(model_config.provider)
        except BudgetExceeded as e:
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=(
                    f"Budget exceeded: ${e.remaining:.2f} remaining, "
                    f"${e.estimated:.2f} needed. Increase budget or switch to a cheaper model."
                ),
            )

        logger.info(
            f"[scene_generator] Sending scene {shot.scene_id} to {model_config.display_name} "
            f"— character: '{shot.primary_character_id}', location: '{shot.location_id}', "
            f"shot: {shot.shot_type} {shot.camera_angle}"
        )
        logger.debug(f"[scene_generator] Prompt preview: {veo_prompt[:150]}...")

        def _on_poll(elapsed: int) -> None:
            if ctx.progress_callback:
                ctx.progress_callback({
                    "type": "veo_polling",
                    "scene_id": shot.scene_id,
                    "elapsed": elapsed,
                    "model": client.model_id,
                })

        client.on_attempt = lambda event, attempt, _sid=shot.scene_id: _record_attempt(_sid, event, attempt)

        try:
            last_call_at = time.monotonic()

            # Use fallback for fal.ai models, direct for Vertex
            if model_config.provider == "fal.ai":
                result_path = client.generate_with_fallback(
                    prompt=veo_prompt,
                    output_dir=clips_dir,
                    filename=f"scene_{shot.scene_id}.mp4",
                    duration=clip_duration(model_config.model_id),
                    resolution=model_config.max_resolution,
                    include_audio=native_audio,  # native audio where the model has it (B3 policy)
                    image_path=str(ref_image),
                    reference_images=reference_images,
                    dialogue=shot.dialogue,
                    voice_profile=shot.voice_profile,
                    on_poll=_on_poll,
                    budget_check=lambda _mid, cost: guard.can_afford(cost),
                )
            else:
                result_path = client.generate_video(
                    prompt=veo_prompt,
                    output_dir=clips_dir,
                    filename=f"scene_{shot.scene_id}.mp4",
                    # Veo renders clip_seconds (8 s) by default; cost it at that length
                    duration=clip_duration(model_config.model_id),
                    include_audio=native_audio,
                    image_path=str(ref_image),
                    dialogue=shot.dialogue,
                    voice_profile=shot.voice_profile,
                    on_poll=_on_poll,
                )

            if not result_path:
                # Build detailed error from fallback chain or single model failure
                fallback_errs = client.get_fallback_errors()
                if fallback_errs:
                    detail = "All models failed:\n" + "\n".join(f"  - {e}" for e in fallback_errs)
                elif client._last_error:
                    detail = f"Generation failed ({client.model_id}): {client._last_error}"
                else:
                    detail = "Video generation returned no output"
                raise RuntimeError(detail)

            size_kb = clip_path.stat().st_size // 1024
            # Spend was recorded per billed attempt (ledger + guard) by _record_attempt
            scene_cost = round(sum(e.get("costUsd", 0.0) for e in ledger.entries_for(ctx.episode_number, shot.scene_id)), 4)

            # Emit live cost update to UI
            if ctx.progress_callback:
                ctx.progress_callback({
                    "type": "cost_update",
                    "scene_id": shot.scene_id,
                    "scene_cost": scene_cost,
                    "budget": guard.summary(),
                    "model_name": client.model.display_name,
                })

            logger.info(
                f"[scene_generator] Scene {shot.scene_id} rendered successfully "
                f"— {size_kb} KB saved to {clip_path.name}"
            )
            artifact_paths.append(str(clip_path))

            # Clean up override file after successful render
            if override_file.exists():
                override_file.unlink()
                logger.info(f"[scene_generator] Override file removed after successful render")

        except Exception as e:
            # Unwrap tenacity RetryError to expose the actual underlying exception
            cause = getattr(e, 'last_attempt', None)
            if cause is not None:
                try:
                    underlying = cause.exception()
                except Exception:
                    underlying = None
                if underlying is not None:
                    e = underlying
            logger.error(
                f"[scene_generator] Scene {shot.scene_id} FAILED: {e}\n"
                f"  Prompt sent ({len(veo_prompt.split())} words): {veo_prompt[:200]}..."
            )
            raise SceneGenerationError(
                scene_id=shot.scene_id,
                veo_prompt=veo_prompt,
                original_error=str(e),
            )

    if not artifact_paths:
        raise RuntimeError(
            f"[scene_generator] No clips were rendered for episode {ctx.episode_number}"
        )

    total_cost = client.get_total_cost()
    budget = guard.summary()
    logger.info(
        f"[scene_generator] Episode {ctx.episode_number} complete — "
        f"{len(artifact_paths)} clip(s) rendered, estimated cost this run: ${total_cost:.2f}, "
        f"episode total: ${ledger.total(ctx.episode_number):.2f} "
        f"(budget: ${budget['remaining']:.2f} remaining)"
    )
    return StepResult(
        artifact_paths=artifact_paths,
        data={
            "model_id": client.model_id,
            "model_name": client.model.display_name,
            "generation_count": client.get_generation_count(),
            "estimated_cost": total_cost,
            "episode_cost": ledger.total(ctx.episode_number),
            "clip_models": {
                str(shot.scene_id): entry["modelId"]
                for shot in shots.shots
                if (entry := ledger.clip_entry(ctx.episode_number, shot.scene_id))
            },
            "budget": budget,
        },
    )
