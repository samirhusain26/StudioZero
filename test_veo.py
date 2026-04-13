"""
Standalone Veo API test — run this to diagnose whether Veo generation works at all.

Usage:
    python test_veo.py                  # text-only prompt (no image)
    python test_veo.py --image path.png # include a reference image

Prints full error details so you can see exactly what the API returns.
"""

import argparse
import logging
import mimetypes
import os
import time
import traceback
from pathlib import Path

# Full verbose logging so nothing is hidden
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("veo_test")

# ── Load env vars (looks for .env in CWD) ─────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info(".env loaded")
except ImportError:
    logger.warning("python-dotenv not installed — relying on shell env vars")

GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
VERTEX_PROJECT   = os.getenv("VERTEX_PROJECT_ID")
VERTEX_LOCATION  = os.getenv("VERTEX_LOCATION", "us-central1")

# ── Sanity check credentials ───────────────────────────────────────────────────
print("\n=== CREDENTIAL CHECK ===")
print(f"  GEMINI_API_KEY   : {'SET (' + GEMINI_API_KEY[:8] + '...)' if GEMINI_API_KEY else 'NOT SET'}")
print(f"  VERTEX_PROJECT_ID: {VERTEX_PROJECT or 'NOT SET'}")
print(f"  VERTEX_LOCATION  : {VERTEX_LOCATION}")
print()

if not GEMINI_API_KEY and not VERTEX_PROJECT:
    print("ERROR: Neither GEMINI_API_KEY nor VERTEX_PROJECT_ID is set. Check your .env file.")
    raise SystemExit(1)

# ── Build client ───────────────────────────────────────────────────────────────
from google import genai
from google.genai import types

def build_client() -> genai.Client:
    if VERTEX_PROJECT:
        logger.info(f"Using Vertex AI  project={VERTEX_PROJECT}  location={VERTEX_LOCATION}")
        return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    logger.info("Using standard GenAI (API Key)")
    return genai.Client(api_key=GEMINI_API_KEY)

# ── Model names ────────────────────────────────────────────────────────────────
# Vertex uses the -001 suffix; standard GenAI uses the -preview suffix
VEO_MODEL_VERTEX  = "veo-3.0-generate-001"     # Vertex AI
VEO_MODEL_GENAI   = "veo-3.0-generate-preview" # Standard GenAI (AI Studio key)
# Also try fast variants if above fail:
VEO_FAST_VERTEX   = "veo-3.1-fast-generate-001"
VEO_FAST_GENAI    = "veo-3.1-fast-generate-preview"

POLL_INTERVAL = 10
MAX_POLL_TIME = 300  # 5 min

SIMPLE_PROMPT = (
    "A friendly cartoon fox sitting at a wooden desk, daylight streaming through "
    "a nearby window, animated short film style. The fox looks directly at the camera "
    "and says: 'Hello! This is a Veo test.' Natural lip-sync, warm colours."
)


def run_test(image_path: str | None = None) -> None:
    client = build_client()
    model = VEO_FAST_VERTEX if VERTEX_PROJECT else VEO_FAST_GENAI

    print(f"\n=== VEO REQUEST ===")
    print(f"  Model  : {model}")
    print(f"  Prompt : {SIMPLE_PROMPT[:100]}...")
    print(f"  Image  : {image_path or '(none)'}\n")

    # Build keyword args — image is optional
    kwargs: dict = {
        "model": model,
        "prompt": SIMPLE_PROMPT,
        "config": types.GenerateVideosConfig(aspect_ratio="9:16"),
    }
    if image_path:
        img_bytes = Path(image_path).read_bytes()
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        kwargs["image"] = types.Image(image_bytes=img_bytes, mime_type=mime)

    try:
        logger.info("Submitting generate_videos request…")
        operation = client.models.generate_videos(**kwargs)
    except Exception as exc:
        print("\n=== SUBMISSION ERROR ===")
        print(f"Type   : {type(exc).__name__}")
        print(f"Message: {exc}")
        print("\nFull traceback:")
        traceback.print_exc()
        _try_fallback_model(client, image_path, kwargs)
        return

    print(f"Operation submitted. Polling every {POLL_INTERVAL}s (max {MAX_POLL_TIME}s)…\n")
    deadline = time.time() + MAX_POLL_TIME

    while not operation.done:
        if time.time() > deadline:
            print(f"\n=== TIMEOUT — operation did not complete in {MAX_POLL_TIME}s ===")
            return
        elapsed = int(time.time() - (deadline - MAX_POLL_TIME))
        print(f"  … {elapsed}s elapsed", end="\r", flush=True)
        time.sleep(POLL_INTERVAL)
        try:
            operation = client.operations.get(operation)
        except Exception as poll_exc:
            print(f"\n=== POLL ERROR ===\n{type(poll_exc).__name__}: {poll_exc}")
            traceback.print_exc()
            return

    print()  # newline after the carriage-return progress line

    # ── Completed ─────────────────────────────────────────────────────────────
    if operation.error:
        print("\n=== OPERATION COMPLETED WITH ERROR ===")
        print(f"Error: {operation.error}")
        print(f"\nFull operation object:\n{operation}")
        return

    print("\n=== OPERATION SUCCEEDED ===")
    resp = getattr(operation, "response", None)
    if not resp:
        print("No response object on operation.")
        return

    videos = getattr(resp, "generated_videos", [])
    print(f"Videos returned: {len(videos)}")

    for i, vid in enumerate(videos):
        print(f"\n  Video {i}:")
        print(f"    metadata : {getattr(vid, 'video_metadata', 'n/a')}")
        raw = getattr(vid, "video", None)
        print(f"    Raw video object: {raw}")

        if raw and getattr(raw, "video_bytes", None):
            out = Path(f"veo_test_output_{i}.mp4")
            out.write_bytes(raw.video_bytes)
            print(f"    Saved to : {out.resolve()}  ({len(raw.video_bytes):,} bytes)")
        elif raw and getattr(raw, "uri", None):
            # Video returned as a download URI — fetch it
            import urllib.request
            uri = raw.uri
            print(f"    Downloading from URI: {uri}")
            # The URI needs the API key appended for auth
            download_url = uri if "key=" in uri else f"{uri}&key={GEMINI_API_KEY}"
            out = Path(f"veo_test_output_{i}.mp4")
            urllib.request.urlretrieve(download_url, out)
            print(f"    Saved to : {out.resolve()}  ({out.stat().st_size:,} bytes)")
        else:
            print(f"    No video_bytes or uri found.")


def _try_fallback_model(client: genai.Client, image_path, original_kwargs: dict) -> None:
    """If the fast model failed, try the non-fast variant."""
    fallback = VEO_MODEL_VERTEX if VERTEX_PROJECT else VEO_MODEL_GENAI
    print(f"\n--- Retrying with fallback model: {fallback} ---")
    kwargs = dict(original_kwargs)
    kwargs["model"] = fallback
    try:
        operation = client.models.generate_videos(**kwargs)
        print(f"Fallback submission succeeded. Operation: {operation}")
    except Exception as exc2:
        print(f"Fallback also failed: {type(exc2).__name__}: {exc2}")
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Veo video generation")
    parser.add_argument("--image", help="Optional path to a reference image (PNG/JPG)")
    args = parser.parse_args()
    run_test(image_path=args.image)
