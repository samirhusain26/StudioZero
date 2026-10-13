#!/usr/bin/env python3
"""Post stats for a retro, from the Pi's feedback export (read only, stdlib).

    python3 tools/retro_stats.py library/_inbox/feedback-<batchId>.json [--game scalar] [--since 2026-10-10]

Groups the export's `performance` posts by platform, then by game/format, and only at matched checkpoints: a post
counts in the column of its newest read (1h, 24h, 72h, 7d, 30d), never mixed with another checkpoint. Prints n
(posts), and the median views, engagements, average watch (s) and A–D answers of each group. Small groups are
flagged; views are plays, not people. Posts without a questionId (exports before 2026-10-12) are grouped as "?".
"""
import argparse
import json
import statistics
from collections import defaultdict

CHECKPOINTS = ('1h', '24h', '72h', '7d', '30d')
SMALL = 5   # fewer posts than this in a group: say "small sample"


def game_format(question_id):
    """'scalar:CAN:clues' -> ('scalar', 'clues'); 'continuum:area:ESP-JPN:head-to-head' -> ('continuum', 'head-to-head')."""
    parts = (question_id or '').split(':')
    if not parts[0]:
        return '?', '?'
    fmt = {'scalar': lambda p: p[2] if len(p) > 2 else '?', 'continuum': lambda p: p[3] if len(p) > 3 else '?',
           'whenabouts': lambda p: p[2] if len(p) > 2 else '?', 'tectonic': lambda p: p[2] if len(p) > 2 else '?'}
    return parts[0], fmt.get(parts[0], lambda p: '?')(parts)


def watch_seconds(values):
    if 'avg_watch_seconds' in values:
        return values['avg_watch_seconds']
    for key in ('ig_reels_avg_watch_time', 'total_video_avg_time_watched', 'post_video_avg_time_watched'):
        if key in values:
            return values[key] / 1000
    return None


def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def rows(performance, game=None, since=None):
    for post in performance:
        read = post.get('metrics') or {}
        if read.get('status') != 'ok' or read.get('checkpoint') not in CHECKPOINTS:
            continue
        if since and (post.get('at') or '') < since:
            continue
        g, f = game_format(post.get('questionId'))
        if game and g != game:
            continue
        values = read.get('values') or {}
        answers = sum(v for k, v in values.items() if k.startswith('answers.'))
        yield post['platform'], g, f, read['checkpoint'], {
            'views': values.get('impressions'), 'engagements': values.get('engagements'),
            'watch': watch_seconds(values), 'answers': answers}


def report(performance, game=None, since=None):
    groups = defaultdict(list)
    for platform, g, f, checkpoint, values in rows(performance, game, since):
        groups[(platform, f'{g}/{f}', checkpoint)].append(values)
    lines = ['platform   game/format                    at    n  views  engaged  watch(s)  answers']
    for (platform, gf, checkpoint), vs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], CHECKPOINTS.index(kv[0][2]))):
        med = {k: median(v[k] for v in vs) for k in ('views', 'engagements', 'watch', 'answers')}
        show = lambda x: '—' if x is None else f'{x:g}'
        flag = '  small sample' if len(vs) < SMALL else ''
        lines.append(f'{platform:<10} {gf:<30} {checkpoint:<4} {len(vs):>2} {show(med["views"]):>6} {show(med["engagements"]):>8} '
                     f'{show(med["watch"]):>9} {show(med["answers"]):>8}{flag}')
    lines.append('Medians per group; each post counts once, at its newest checkpoint. Views are plays, not people.')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('feedback')
    parser.add_argument('--game')
    parser.add_argument('--since', help='only posts published on or after this date (YYYY-MM-DD)')
    args = parser.parse_args()
    with open(args.feedback, encoding='utf-8') as handle:
        doc = json.load(handle)
    print(report(doc.get('performance') or [], args.game, args.since))


if __name__ == '__main__':
    main()
