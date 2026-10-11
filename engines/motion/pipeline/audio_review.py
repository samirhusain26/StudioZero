"""Write the owner's audition sheet for the calm audio corpus: out/audio-review/index.html (docs/AUDIO_CORPUS_PLAN.md).

    .venv/bin/python pipeline/audio_review.py            (from engines/motion/; run pipeline/music_catalog.py first)

Music comes from music/catalog.json (best quiz fit first, players start 30 s in), grouped by suggested game. SFX are every calm-fitting file under
sfx/sources/ (Kenney CC0 packs + tools/make_calm_sfx.py), grouped by a guessed role. Choices persist in the browser;
"Copy selections" puts a JSON block on the clipboard to paste back to Claude, which applies it to the catalogs.
Players reference the local files by relative path, so the sheet only works from this Mac.
"""
import html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # engines/motion/
OUT = ROOT / 'out/audio-review/index.html'
SFX = ROOT / 'sfx/sources'
# Kenney families that do not fit the calm look (sci-fi, harsh, error, footsteps)
SKIP = re.compile(r'^(preview|laser|zap|phaser|phasejump|spacetrash|error|glitch|impactpunch|impactmining|impactmetal_heavy'
                  r'|impactplate_heavy|footstep|lowrandom|lowdown)', re.I)
ROLES = [  # first match wins
    ('think', r'tick|tock|clock|scroll|think-pad'),
    ('reveal', r'glass|bell|shimmer|reveal|threetone|twotone|tone1|pepsound|powerup|highup|bong|confirmation'),
    ('explain', r'paper|pencil|scratch|minimize|close|carpet|back_'),
    ('cta', r'whoosh|stinger|maximize|question|open_'),
    ('choices', r'pop|pickup|drop|plank|soft|toggle|rollover'),
    ('item', r'.'),
]
ROLE_ORDER = ['item', 'choices', 'think', 'reveal', 'explain', 'cta']
GAMES = ['scalar', 'continuum', 'whenabouts', 'tectonic']
BRIEF = {  # music brief per game (docs/AUDIO_CORPUS_PLAN.md)
    'scalar': 'curious light-detective lo-fi: plucks, marimba, muted guitar, brushes',
    'continuum': 'clean minimal chillhop: soft synth plucks, tidy beat',
    'whenabouts': 'warm vintage acoustic: felt piano, nylon guitar, jazz-hop',
    'tectonic': 'airy ambient exploration: pads, gentle arps, water textures',
}


def role_of(name):
    return next(r for r, pat in ROLES if re.search(pat, name, re.I))


def rel(p):
    return '../../' + str(p.relative_to(ROOT))


def main():
    tracks = list(json.loads((ROOT / 'music/catalog.json').read_text())['tracks'].values())
    sfx = {r: [] for r in ROLE_ORDER}
    for p in sorted(SFX.glob('*/**/*')):
        if p.suffix.lower() not in {'.wav', '.ogg'} or SKIP.match(p.name):
            continue
        sfx[role_of(p.stem)].append(p)

    rows = []
    for g in GAMES:
        rows.append(f'<tr><th colspan="7" class="g">{g} <small>{BRIEF[g]}</small></th></tr>')
        for t in sorted((t for t in tracks if t['flavour'] == g), key=lambda t: (not t.get('pick'), -t['quizFit'])):
            star = '<span class="pick">★ pick</span> ' if t.get('pick') else ''
            rows.append(f'''<tr data-id="{t['id']}"{' class="picked"' if t.get('pick') else ''}><td>{star}<b>{html.escape(t['title'])}</b><br><small>{t['artist']} · {t['pack']}</small></td>
<td>{t['quizFit']:.2f}</td><td>{t['feltBpm']:.0f} · {t['key']}</td><td>{t['durationSeconds']:.0f}s</td><td>{'yes' if t['cuttable'] else '—'}</td>
<td><audio controls preload="none" src="{html.escape(rel(ROOT / t['file']))}#t=30"></audio></td>
<td class="st">{''.join(f'<label><input type="radio" name="m:{t["id"]}" value="{v}">{v}</label>' for v in ('keep', 'maybe', 'reject'))}</td></tr>''')

    groups = []
    for r in ROLE_ORDER:
        items = ''.join(f'''<div class="sfx"><button data-src="{html.escape(rel(p))}">▶</button><label><input type="checkbox" data-k="{html.escape(str(p.relative_to(SFX)))}">
{html.escape(p.parent.name + '/' + p.stem)}</label></div>''' for p in sfx[r])
        groups.append(f'<h3>{r} <small>({len(sfx[r])})</small></h3><div class="grid">{items}</div>')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audio audition</title><style>
:root{{--bg:#fafaf9;--fg:#18181b;--line:#e2e8f0;--muted:#64748b;--accent:#16a34a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111113;--fg:#f4f4f5;--line:#2a2a30;--muted:#94a3b8}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.4 ui-monospace,Menlo,monospace;margin:0 auto;max-width:1200px;padding:16px}}
h1{{font-size:20px}} h2{{margin-top:32px;border-bottom:1px solid var(--line)}} small{{color:var(--muted)}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:middle}}
audio{{height:32px;width:260px}} .st label{{margin-right:8px;white-space:nowrap}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:4px 12px}}
.sfx{{display:flex;gap:8px;align-items:center}} .sfx button{{width:32px;height:28px;border:1px solid var(--line);background:none;color:var(--fg);cursor:pointer}}
tr.picked{{background:rgba(22,163,74,.07)}} .pick{{color:var(--accent);font-weight:700}}
th.g{{padding-top:20px;font-size:16px;text-transform:capitalize}}
.bar{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;z-index:1}}
.bar button{{padding:6px 12px;border:1px solid var(--fg);background:var(--fg);color:var(--bg);cursor:pointer}}
@media (max-width:700px){{td:nth-child(4),td:nth-child(5),th:nth-child(4),th:nth-child(5){{display:none}} audio{{width:160px}}}}
</style></head><body>
<h1>Calm audio audition</h1>
<p><small>Music brief: curious thinking music, light and gently playful, major key, 75–110 BPM, steady, never sad.
{len(tracks)} CC0 tracks grouped by the game they suit. ★ = Claude's pick (up to 15 per game), listed first; mark reject to veto. Then best fit first (fit = tempo, major key, calm, steady beat). Players start 30 s in. SFX: {sum(map(len, sfx.values()))} candidates grouped by guessed role.
Choices are saved in this browser. When done, press Copy and paste the result to Claude.</small></p>
<div class="bar"><button id="copy">Copy selections</button><span id="count"></span></div>
<h2>Music</h2><table><tr><th>Track</th><th>Fit</th><th>BPM · key</th><th>Length</th><th>Cuttable</th><th>Listen</th><th>Decision</th></tr>
{''.join(rows)}</table>
<h2>SFX</h2>{''.join(groups)}
<script>
const KEY='audio-review-v1'; let st={{m:{{}},s:{{}}}};
try{{st=JSON.parse(localStorage.getItem(KEY))||st}}catch(e){{}}
const save=()=>{{try{{localStorage.setItem(KEY,JSON.stringify(st))}}catch(e){{}};count()}};
const count=()=>{{const m=Object.values(st.m);document.getElementById('count').textContent=
 `music keep ${{m.filter(v=>v=='keep').length}} · maybe ${{m.filter(v=>v=='maybe').length}} · reject ${{m.filter(v=>v=='reject').length}} · sfx ${{Object.values(st.s).filter(Boolean).length}}`}};
document.querySelectorAll('input[type=radio]').forEach(i=>{{const id=i.name.slice(2);if(st.m[id]==i.value)i.checked=true;
 i.onchange=()=>{{st.m[id]=i.value;save()}}}});
document.querySelectorAll('input[type=checkbox]').forEach(i=>{{i.checked=!!st.s[i.dataset.k];i.onchange=()=>{{st.s[i.dataset.k]=i.checked;save()}}}});
const player=new Audio();document.querySelectorAll('.sfx button').forEach(b=>b.onclick=()=>{{player.src=b.dataset.src;player.play()}});
document.querySelectorAll('audio').forEach(a=>a.onplay=()=>document.querySelectorAll('audio').forEach(o=>o!==a&&o.pause()));
document.getElementById('copy').onclick=async()=>{{const out={{music:st.m,sfx:Object.keys(st.s).filter(k=>st.s[k])}};
 const txt='Audio audition selections:\\n'+JSON.stringify(out,null,1);
 try{{await navigator.clipboard.writeText(txt);document.getElementById('copy').textContent='Copied ✓'}}catch(e){{prompt('Copy this:',txt)}}}};
count();
</script></body></html>
''')
    print(f'{len(tracks)} tracks, {sum(map(len, sfx.values()))} sfx -> {OUT.relative_to(ROOT)}')
    for r in ROLE_ORDER:
        print(f'  {r}: {len(sfx[r])}')


if __name__ == '__main__':
    main()
