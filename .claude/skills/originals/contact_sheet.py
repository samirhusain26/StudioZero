"""Frames and a contact sheet of one story render, for visual QA (no ffmpeg tile filter needed).

    engines/motion/.venv/bin/python .claude/skills/originals/contact_sheet.py <video.mp4> <out-dir> [frames=12]

Writes <out-dir>/f<NN>-<seconds>s.png (full size) and <out-dir>/sheet.png (a grid with timestamps).
Uses `ffmpeg`/`ffprobe` from PATH when they run, else the Remotion-bundled binaries in
engines/motion/node_modules (system ffmpeg on the owner's Mac is broken).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]


def tool(name: str) -> list:
    try:
        if subprocess.run([name, "-version"], capture_output=True, timeout=30).returncode == 0:
            return [name]
    except (OSError, subprocess.TimeoutExpired):
        pass
    for binary in sorted((ROOT / "engines/motion/node_modules/@remotion").glob(f"compositor-*/{name}")):
        os.environ["DYLD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"] = str(binary.parent)
        return [str(binary)]
    sys.exit(f"no working {name}")


def main(video: str, out_dir: str, count: int = 12) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    probe = json.loads(subprocess.run(tool("ffprobe") + ["-v", "error", "-show_format", "-of", "json", video],
                                      capture_output=True, text=True, check=True).stdout)
    duration = float(probe["format"]["duration"])
    times = [duration * (i + 0.5) / count for i in range(count)]
    frames = []
    for i, t in enumerate(times):
        frame = out / f"f{i:02d}-{t:05.1f}s.png"
        subprocess.run(tool("ffmpeg") + ["-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", str(frame)],
                       check=True)
        frames.append((t, frame))
    cols, w = 6, 270
    ims = [Image.open(f).convert("RGB") for _, f in frames]
    h = int(ims[0].height * w / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 8), rows * (h + 26)), "white")
    for i, ((t, _), im) in enumerate(zip(frames, ims)):
        x, y = (i % cols) * (w + 8), (i // cols) * (h + 26)
        sheet.paste(im.resize((w, h)), (x, y + 22))
        ImageDraw.Draw(sheet).text((x + 4, y + 4), f"{t:.1f} s", fill="black")
    sheet.save(out / "sheet.png")
    print(out / "sheet.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12)
