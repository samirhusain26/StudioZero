"""Tile PNG stills side by side: contact.py out.png a.png b.png ..."""
import sys
from PIL import Image, ImageDraw
ims = [Image.open(p).convert('RGB') for p in sys.argv[2:]]
# overlay safe zones (theme.ts SAFE: top 270, bottom 380, right 130 at 1080x1920)
for im in ims:
    k = im.width / 1080; d = ImageDraw.Draw(im, 'RGBA')
    d.rectangle([0, 0, im.width, 270 * k], fill=(255, 0, 0, 40)); d.rectangle([0, im.height - 380 * k, im.width, im.height], fill=(255, 0, 0, 40))
    d.rectangle([im.width - 130 * k, 270 * k, im.width, im.height - 380 * k], fill=(255, 0, 0, 30))
h = 900; ims = [i.resize((int(i.width * h / i.height), h)) for i in ims]
sheet = Image.new('RGB', (sum(i.width for i in ims) + 10 * len(ims), h + 30), 'white')
x = 0
for p, i in zip(sys.argv[2:], ims):
    sheet.paste(i, (x, 30)); ImageDraw.Draw(sheet).text((x + 5, 8), p.split('/')[-1], fill='black'); x += i.width + 10
sheet.save(sys.argv[1])
