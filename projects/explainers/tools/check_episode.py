#!/usr/bin/env python3
"""Explainers episode checker (stdlib): validates an episode's ledger.json and, when present, lints its script.json.

Usage: python3 projects/explainers/tools/check_episode.py <episodeDir> [--json]
<episodeDir> holds ledger.json (required) and script.json (optional), e.g. library/<batchId>/review/jobs/<episodeId>/.
Exit 0 when there are no errors (warnings allowed), 1 on errors, 2 on unreadable input.
Rules: projects/explainers/SYSTEM.md §5 (ledger), §6 (facts and rights), formats/formats.json (spines and limits).
"""
import json
import re
import sys
from pathlib import Path

FORMATS_FILE = Path(__file__).resolve().parent.parent / 'formats' / 'formats.json'

EPISODE_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,79}$')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
FACT_KINDS = {'background', 'problem', 'old-way', 'insight', 'mechanism', 'product', 'context', 'number', 'news', 'expiry', 'aftermath', 'people'}
VISUAL_KINDS = {'patent-figure', 'product-reference', 'licensed-image', 'owner-footage', 'our-build'}
STATUS_WORDS = re.compile(r'\b(expired|expire[sd]?|active|in force|still valid|lapsed)\b', re.I)
RISKY_WORDS = re.compile(r'\b(invented|inventor of|first[- ]ever|(was|is|were|are) the first|the first to|revolutionary|genius|secretly|everyone uses)\b', re.I)
LADDER_WORDS = re.compile(r"\b(ships in|is how (your|every|the)\b|inside every|uses this patent|every \w+ (has|uses)|your \w+ (uses|does))", re.I)
NUMBER = re.compile(r'\d[\d,.]*')
LONG_NUMBER = re.compile(r'\d{1,3}(,\d{3})+|\d{4,}')


def load_formats():
    with open(FORMATS_FILE, encoding='utf-8') as f:
        return json.load(f)


def words(text):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,-]*", text or '')


def is_https(value):
    return isinstance(value, str) and value.startswith('https://')


def nonempty(value):
    return isinstance(value, str) and value.strip() != ''


def check_ledger(ledger, formats):
    errors, warnings = [], []
    if not isinstance(ledger, dict):
        return ['ledger.json is not an object'], warnings, set()
    if not (isinstance(ledger.get('episodeId'), str) and EPISODE_ID.fullmatch(ledger['episodeId'])):
        errors.append('ledger.episodeId: lowercase letters, digits and hyphens')
    format_ids = {f['id'] for f in formats['formats']}
    if ledger.get('format') not in format_ids:
        errors.append(f"ledger.format: one of {', '.join(sorted(format_ids))}")

    patent = ledger.get('patent')
    if not isinstance(patent, dict):
        errors.append('ledger.patent: missing')
        patent = {}
    for key in ('number', 'title', 'assignee'):
        if not nonempty(patent.get(key)):
            errors.append(f'ledger.patent.{key}: missing')
    if not (isinstance(patent.get('inventors'), list) and patent['inventors'] and all(nonempty(i) for i in patent['inventors'])):
        errors.append('ledger.patent.inventors: a non-empty list of names')
    for key in ('filingDate', 'grantDate'):
        if not (isinstance(patent.get(key), str) and DATE.fullmatch(patent[key])):
            errors.append(f'ledger.patent.{key}: YYYY-MM-DD')
    if patent.get('priorityDate') is not None and not (isinstance(patent['priorityDate'], str) and DATE.fullmatch(patent['priorityDate'])):
        errors.append('ledger.patent.priorityDate: YYYY-MM-DD or null')
    if not is_https(patent.get('url')):
        errors.append('ledger.patent.url: an https link to the patent (Google Patents page)')

    status = ledger.get('status')
    if not isinstance(status, dict) or not nonempty(status.get('statement')):
        errors.append('ledger.status.statement: missing (e.g. "granted 2005-04-26")')
        status = status if isinstance(status, dict) else {}
    elif STATUS_WORDS.search(status['statement']):
        if not (isinstance(status.get('checkedAt'), str) and DATE.fullmatch(status['checkedAt']) and is_https(status.get('checkUrl'))):
            errors.append('ledger.status: "expired"/"active" needs checkedAt (YYYY-MM-DD) and checkUrl (USPTO record)')

    notice = ledger.get('copyrightNotice')
    if not (isinstance(notice, dict) and notice.get('checked') is True and isinstance(notice.get('present'), bool)):
        errors.append('ledger.copyrightNotice: {checked: true, present: true|false} (start of the specification and under figures)')
    elif notice['present']:
        warnings.append('ledger.copyrightNotice.present: figures from this patent must not be used or redrawn')

    ids = set()

    def take_id(item, where):
        i = item.get('id')
        if not nonempty(i):
            errors.append(f'{where}: id missing')
        elif i in ids:
            errors.append(f'{where}: duplicate id {i}')
        else:
            ids.add(i)

    claims = ledger.get('claims')
    if not (isinstance(claims, list) and claims):
        errors.append('ledger.claims: at least claim 1 (paraphrase + location)')
        claims = []
    for n, c in enumerate(claims):
        where = f'ledger.claims[{n}]'
        if not isinstance(c, dict):
            errors.append(f'{where}: not an object')
            continue
        take_id(c, where)
        if not (nonempty(c.get('text')) and nonempty(c.get('location'))):
            errors.append(f'{where}: text and location required')

    facts = ledger.get('facts')
    if not (isinstance(facts, list) and facts):
        errors.append('ledger.facts: missing')
        facts = []
    for n, fact in enumerate(facts):
        where = f'ledger.facts[{n}]'
        if not isinstance(fact, dict):
            errors.append(f'{where}: not an object')
            continue
        take_id(fact, where)
        if fact.get('kind') not in FACT_KINDS:
            errors.append(f"{where}.kind: one of {', '.join(sorted(FACT_KINDS))}")
        if not nonempty(fact.get('text')):
            errors.append(f'{where}.text: missing')
        source = fact.get('source')
        if not (isinstance(source, dict) and (is_https(source.get('url')) or nonempty(source.get('location')))):
            errors.append(f'{where}.source: an https url or a location in the patent')
        if fact.get('confidence') not in ('verified', 'inferred'):
            errors.append(f'{where}.confidence: verified or inferred')

    link = ledger.get('productLink')
    if not isinstance(link, dict) or link.get('level') not in (1, 2, 3, 4):
        errors.append('ledger.productLink.level: 1 (record) · 2 (content) · 3 (marking) · 4 (ships in)')
        link = link if isinstance(link, dict) else {}
    else:
        evidence = link.get('evidence') if isinstance(link.get('evidence'), list) else []
        good = [e for e in evidence if isinstance(e, dict) and is_https(e.get('url')) and isinstance(e.get('checkedAt'), str) and DATE.fullmatch(e['checkedAt'])]
        if link['level'] >= 3 and not good:
            errors.append('ledger.productLink: level 3+ needs evidence [{url, what, checkedAt}]')
        if link['level'] >= 2 and not nonempty(link.get('product')):
            errors.append('ledger.productLink.product: name the product')

    visuals = ledger.get('visuals') if isinstance(ledger.get('visuals'), list) else None
    if visuals is None:
        errors.append('ledger.visuals: a list (may be empty)')
        visuals = []
    for n, v in enumerate(visuals):
        where = f'ledger.visuals[{n}]'
        if not isinstance(v, dict):
            errors.append(f'{where}: not an object')
            continue
        if v.get('kind') not in VISUAL_KINDS:
            errors.append(f"{where}.kind: one of {', '.join(sorted(VISUAL_KINDS))}")
        if v.get('kind') == 'licensed-image' and not (is_https(v.get('source')) and nonempty(v.get('licence')) and nonempty(v.get('author'))):
            errors.append(f'{where}: a licensed image needs source (https), licence and author')
        licence = v.get('licence') or ''
        if v.get('kind') == 'licensed-image' and re.search(r'\b(NC|ND)\b|non-?commercial|no-?deriv', licence, re.I):
            errors.append(f'{where}: {licence} is not usable (NonCommercial or NoDerivatives)')
        elif v.get('kind') == 'licensed-image' and re.search(r'\bSA\b|share-?alike', licence, re.I):
            warnings.append(f'{where}: {licence} is ShareAlike; only with the standards editor clearing the exact use')
        if v.get('kind') == 'patent-figure' and isinstance(notice, dict) and notice.get('present'):
            errors.append(f'{where}: the patent carries a copyright notice; no figures')
    if not isinstance(ledger.get('risks'), list):
        errors.append('ledger.risks: a list (may be empty)')
    return errors, warnings, ids


def check_script(script, ledger, ledger_ids, formats):
    errors, warnings, stats = [], [], {}
    if not isinstance(script, dict):
        return ['script.json is not an object'], warnings, stats
    if script.get('episodeId') != ledger.get('episodeId'):
        errors.append('script.episodeId: must equal ledger.episodeId')
    fmt = next((f for f in formats['formats'] if f['id'] == script.get('format')), None)
    if fmt is None or script.get('format') != ledger.get('format'):
        errors.append('script.format: must equal ledger.format')
    if script.get('status') not in ('draft', 'locked'):
        errors.append('script.status: draft or locked')
    if not nonempty(script.get('angle')):
        errors.append('script.angle: missing')
    title = script.get('title')
    if not nonempty(title) or len(title) > 70:
        errors.append('script.title: 1–70 characters')

    lines = script.get('lines')
    if not (isinstance(lines, list) and len(lines) >= 5):
        errors.append('script.lines: at least 5 lines')
        lines = []
    spine = fmt['spine'] if fmt else []
    seen, last_index, all_words, numbers = set(), -1, [], 0
    status_ok = isinstance(ledger.get('status'), dict) and nonempty(ledger['status'].get('checkedAt'))
    level = (ledger.get('productLink') or {}).get('level') if isinstance(ledger.get('productLink'), dict) else None
    for n, line in enumerate(lines):
        where = f'script.lines[{n}]'
        if not isinstance(line, dict):
            errors.append(f'{where}: not an object')
            continue
        lid = line.get('id')
        if not nonempty(lid) or lid in seen:
            errors.append(f'{where}.id: missing or duplicate')
        seen.add(lid)
        beat = line.get('beat')
        if spine:
            if beat not in spine:
                errors.append(f"{where}.beat: one of {', '.join(spine)}")
            else:
                index = spine.index(beat)
                if index < last_index:
                    errors.append(f'{where}.beat: {beat} is out of spine order')
                last_index = max(last_index, index)
        vo = line.get('vo')
        if not nonempty(vo):
            errors.append(f'{where}.vo: missing')
            vo = ''
        line_words = words(vo)
        all_words += line_words
        numbers += len(NUMBER.findall(vo))
        banner = line.get('banner')
        if banner is not None and (not isinstance(banner, str) or len(words(banner)) > formats['bannerMaxWords']):
            errors.append(f"{where}.banner: null or at most {formats['bannerMaxWords']} words")
        refs = line.get('factRefs')
        if not isinstance(refs, list):
            errors.append(f'{where}.factRefs: a list of ledger ids')
            refs = []
        unknown = [r for r in refs if r not in ledger_ids]
        if unknown:
            errors.append(f"{where}.factRefs: not in the ledger: {', '.join(map(str, unknown))}")
        if not refs and line.get('noClaim') is not True:
            errors.append(f'{where}: no factRefs; cite ledger ids or set noClaim: true for a line that claims nothing')
        if STATUS_WORDS.search(vo) and not status_ok:
            errors.append(f'{where}: says expired/active but the ledger status has no dated USPTO check')
        if RISKY_WORDS.search(vo):
            warnings.append(f'{where}: "{RISKY_WORDS.search(vo).group(0)}" needs a source that says exactly that')
        if LADDER_WORDS.search(vo) and level != 4:
            warnings.append(f'{where}: "{LADDER_WORDS.search(vo).group(0)}" claims product use; the ledger is at level {level}, not 4')
        if LONG_NUMBER.search(vo):
            warnings.append(f'{where}: write long numbers for speech ("six million" or "patent six, eight, eight, three…"); the banner can show digits')
        if n == 0 and len(line_words) > formats['hookMaxWords']:
            errors.append(f"{where}: the hook is {len(line_words)} words; at most {formats['hookMaxWords']}")
    if spine and lines:
        present = {l.get('beat') for l in lines if isinstance(l, dict)}
        missing = [b for b in spine if b not in present and b not in (fmt.get('optional') or [])]
        if missing:
            errors.append(f"script.lines: missing beats {', '.join(missing)}")
        if isinstance(lines[0], dict) and lines[0].get('beat') != 'hook':
            errors.append('script.lines[0]: must be the hook')
        if isinstance(lines[-1], dict) and lines[-1].get('beat') != 'loop':
            errors.append('script.lines[-1]: must be the loop')
    low, high = formats['words']
    count = len(all_words)
    stats = {'words': count, 'estimatedSeconds': round(count / formats['wordsPerSecond'], 1), 'spokenNumbers': numbers}
    if lines and not low <= count <= high:
        errors.append(f'script: {count} spoken words; {low}–{high} fits 45–75 s')
    if numbers > 8:
        warnings.append(f'script: {numbers} spoken numbers; more than 8 is hard to follow')

    caption = script.get('caption')
    if not (isinstance(caption, dict) and all(nonempty(caption.get(k)) for k in ('hook', 'payoff', 'question'))):
        errors.append('script.caption: hook, payoff and question')
    return errors, warnings, stats


def check_dir(path, formats=None):
    formats = formats or load_formats()
    path = Path(path)
    result = {'episodeDir': str(path), 'errors': [], 'warnings': [], 'stats': {}}
    with open(path / 'ledger.json', encoding='utf-8') as f:
        ledger = json.load(f)
    errors, warnings, ids = check_ledger(ledger, formats)
    result['errors'] += errors
    result['warnings'] += warnings
    script_path = path / 'script.json'
    if script_path.exists():
        with open(script_path, encoding='utf-8') as f:
            script = json.load(f)
        errors, warnings, stats = check_script(script, ledger if isinstance(ledger, dict) else {}, ids, formats)
        result['errors'] += errors
        result['warnings'] += warnings
        result['stats'] = stats
    result['ok'] = not result['errors']
    return result


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    try:
        result = check_dir(args[0])
    except (OSError, ValueError) as exc:
        print(f'cannot read episode: {exc}', file=sys.stderr)
        return 2
    if '--json' in argv:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['episodeDir']}: {'OK' if result['ok'] else 'FAIL'} {result['stats']}")
        for e in result['errors']:
            print(f'  error: {e}')
        for w in result['warnings']:
            print(f'  warning: {w}')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
