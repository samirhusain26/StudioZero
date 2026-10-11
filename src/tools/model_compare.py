"""
Model Comparison Tool — Generate the same prompt across multiple video models
and produce a side-by-side HTML comparison report.

Usage:
    python -m src.tools.model_compare --prompt "A cat walking through a sunlit garden" \
        --models kling-2.5-turbo-pro,veo-3.1-fast,seedance-2.0-fast

    python -m src.tools.model_compare --prompt "A cat walking" --models all --budget 3.0

    python -m src.tools.model_compare --prompt "Camera pans across a sunset" \
        --image input.jpg --models kling-2.5-turbo-pro,wan-2.2
"""

import argparse
import html
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.config import Config
from src.video_models import VIDEO_MODEL_REGISTRY, get_model, estimate_cost
from src.video_client import UnifiedVideoClient

logger = logging.getLogger(__name__)


def _generate_report(
    results: List[dict],
    prompt: str,
    output_dir: Path,
    total_cost: float,
    total_time: float,
) -> str:
    """Generate an HTML report with side-by-side video players."""
    report_path = output_dir / "report.html"

    video_cards = []
    for r in results:
        status_color = "#4ade80" if r["success"] else "#f87171"
        status_text = "Success" if r["success"] else f"Failed: {r.get('error', 'Unknown')}"

        video_html = ""
        if r["success"] and r.get("filename"):
            video_html = f"""
            <video controls preload="metadata" style="width:100%;border-radius:8px;margin-bottom:12px;">
                <source src="{html.escape(r['filename'])}" type="video/mp4">
                Your browser does not support video playback.
            </video>"""
        else:
            video_html = '<div style="height:200px;display:flex;align-items:center;justify-content:center;background:#1f2937;border-radius:8px;margin-bottom:12px;color:#9ca3af;">Generation failed</div>'

        video_cards.append(f"""
        <div style="background:#111827;border:1px solid #374151;border-radius:12px;padding:20px;flex:1;min-width:300px;">
            <h3 style="color:white;margin:0 0 4px 0;font-size:16px;">{html.escape(r['display_name'])}</h3>
            <div style="color:#9ca3af;font-size:12px;margin-bottom:12px;">{html.escape(r['model_id'])}</div>
            {video_html}
            <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:13px;color:#d1d5db;">
                <span>Cost: <strong>${r['cost']:.4f}</strong></span>
                <span>Time: <strong>{r['duration_sec']:.1f}s</strong></span>
                <span>Resolution: <strong>{html.escape(r['resolution'])}</strong></span>
            </div>
            <div style="margin-top:8px;font-size:12px;color:{status_color};">{html.escape(status_text)}</div>
        </div>""")

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>StudioZero Model Comparison</title>
    <style>
        body {{ background: #030712; color: #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ margin-bottom: 32px; }}
        .header h1 {{ color: white; margin: 0 0 8px 0; font-size: 24px; }}
        .header p {{ color: #9ca3af; margin: 0; font-size: 14px; }}
        .prompt-box {{ background: #1f2937; border: 1px solid #374151; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
        .prompt-box label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
        .prompt-box p {{ color: #e5e7eb; margin: 8px 0 0 0; font-size: 15px; }}
        .stats {{ display: flex; gap: 24px; margin-bottom: 24px; font-size: 14px; color: #9ca3af; }}
        .stats strong {{ color: white; }}
        .grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Model Comparison Report</h1>
            <p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class="prompt-box">
            <label>Prompt</label>
            <p>{html.escape(prompt)}</p>
        </div>
        <div class="stats">
            <span>Models tested: <strong>{len(results)}</strong></span>
            <span>Successful: <strong>{sum(1 for r in results if r['success'])}</strong></span>
            <span>Total cost: <strong>${total_cost:.4f}</strong></span>
            <span>Total time: <strong>{total_time:.1f}s</strong></span>
        </div>
        <div class="grid">
            {''.join(video_cards)}
        </div>
    </div>
</body>
</html>"""

    report_path.write_text(report_html, encoding="utf-8")
    return str(report_path)


def run_comparison(
    prompt: str,
    model_ids: List[str],
    budget: float = 5.0,
    duration: int = 5,
    image_path: Optional[str] = None,
) -> str:
    """
    Run video generation across multiple models and produce a comparison report.

    Returns the path to the HTML report.
    """
    Config.ensure_directories()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Config.OUTPUT_DIR / "model_comparison" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    cumulative_cost = 0.0
    start_time = time.time()

    logger.info(
        f"[model_compare] Starting comparison: {len(model_ids)} model(s), "
        f"budget ${budget:.2f}, prompt: '{prompt[:80]}...'"
    )

    for model_id in model_ids:
        model_config = get_model(model_id)
        est = estimate_cost(model_id, duration, include_audio=False)

        if cumulative_cost + est > budget:
            logger.warning(
                f"[model_compare] Skipping {model_id}: estimated ${est:.4f} "
                f"would exceed budget (${budget - cumulative_cost:.4f} remaining)"
            )
            results.append({
                "model_id": model_id,
                "display_name": model_config.display_name,
                "resolution": model_config.max_resolution,
                "cost": 0.0,
                "duration_sec": 0.0,
                "success": False,
                "error": "Skipped — budget exceeded",
                "filename": None,
            })
            continue

        logger.info(f"[model_compare] Generating with {model_config.display_name} ({model_id})...")
        client = UnifiedVideoClient(model_id)
        gen_start = time.time()

        filename = f"{model_id.replace('.', '_')}.mp4"
        result_path = client.generate_video(
            prompt=prompt,
            output_dir=output_dir,
            filename=filename,
            duration=duration,
            resolution=model_config.max_resolution,
            include_audio=False,
            image_path=image_path,
        )

        gen_duration = time.time() - gen_start
        cost = client.get_total_cost()
        cumulative_cost += cost

        results.append({
            "model_id": model_id,
            "display_name": model_config.display_name,
            "resolution": model_config.max_resolution,
            "cost": cost,
            "duration_sec": gen_duration,
            "success": result_path is not None,
            "error": None if result_path else "Generation failed",
            "filename": filename if result_path else None,
        })

        logger.info(
            f"[model_compare] {model_id}: {'OK' if result_path else 'FAILED'} "
            f"in {gen_duration:.1f}s, cost: ${cost:.4f}"
        )

    total_time = time.time() - start_time
    report_path = _generate_report(results, prompt, output_dir, cumulative_cost, total_time)

    logger.info(
        f"[model_compare] Comparison complete — {len(results)} model(s), "
        f"${cumulative_cost:.4f} total, report: {report_path}"
    )

    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Compare video outputs across multiple AI models"
    )
    parser.add_argument(
        "--prompt", required=True, help="Text prompt to generate video from"
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated model IDs, or 'all' for every model in registry",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=5.0,
        help="Maximum total spend for the comparison run (default: $5.00)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=5,
        help="Video duration in seconds (default: 5)",
    )
    parser.add_argument(
        "--image",
        default=None,
        help="Optional image path for image-to-video mode",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.models == "all":
        model_ids = [
            m_id for m_id, m in VIDEO_MODEL_REGISTRY.items()
            if m.provider == "fal.ai"  # Skip Vertex AI in all-model comparison
        ]
    else:
        model_ids = [m.strip() for m in args.models.split(",") if m.strip()]

    # Validate model IDs
    for mid in model_ids:
        if mid not in VIDEO_MODEL_REGISTRY:
            print(f"Error: Unknown model '{mid}'")
            print(f"Available: {', '.join(VIDEO_MODEL_REGISTRY.keys())}")
            sys.exit(1)

    report_path = run_comparison(
        prompt=args.prompt,
        model_ids=model_ids,
        budget=args.budget,
        duration=args.duration,
        image_path=args.image,
    )

    print(f"\nReport generated: {report_path}")
    print(f"Open in browser: file://{report_path}")


if __name__ == "__main__":
    main()
