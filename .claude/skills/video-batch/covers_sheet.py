"""Covers sheet for a batch review (PIL; Remotion's ffmpeg has no `tile` filter).

  studio/.venv/bin/python .claude/skills/video-batch/covers_sheet.py library/<batchId> library/<batchId>/review/covers.png

Reads <batch>/covers/*.jpg (read-only) and writes one labelled grid, five covers per row.
"""
import glob
import os
import sys

from PIL import Image, ImageDraw

batch, out = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(os.path.join(batch, 'covers', '*.jpg')))
if not files:
    sys.exit(f'no covers in {batch}/covers')
W, H, COLS = 270, 480, 5
rows = (len(files) + COLS - 1) // COLS
sheet = Image.new('RGB', (COLS * (W + 10), rows * (H + 30)), 'white')
for i, f in enumerate(files):
    x, y = (i % COLS) * (W + 10), (i // COLS) * (H + 30)
    sheet.paste(Image.open(f).convert('RGB').resize((W, H)), (x, y + 24))
    ImageDraw.Draw(sheet).text((x + 4, y + 6), os.path.basename(f)[:-4], fill='black')
sheet.save(out)
print(out, sheet.size, len(files))
