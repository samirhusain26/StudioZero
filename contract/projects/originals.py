"""Contract v2 rules for the originals project (docs/STUDIO_PLAN.md §5.3): StudioZero's own recaps and shorts.

Batch projectData = null. Episode projectData = {subject: {kind, title, year}, sources[], checks: {rights, garbage,
visualQa}, reviewer, series: {seriesId, episode} | null}. Formats movie-recap and story-recap (story/recap),
animated-short (story/series, needs `series`). The link is optional; no poll and no answer reply. Credits must
name every footage, poster and music asset with a known licence (the core refuses "unknown"); a recap credits its
footage; the core requires aiGenerated whenever a generative model made part of the video.
"""
import re

import library_contract as lc

NAME = 'originals'
NAMESPACES = ('originals',)
EPISODE_PREFIXES = ('originals',)
FORMATS = {'movie-recap': ('story', 'recap'), 'story-recap': ('story', 'recap'), 'animated-short': ('story', 'series')}
LINK_REQUIRED = False
POLL = False
ANSWER_REPLY = False
SUBJECT_KINDS = ('movie', 'book', 'story', 'original')
EPISODE_DATA = ('subject', 'sources', 'checks', 'reviewer', 'series')
CHECKS = ('rights', 'garbage', 'visualQa')


def link_allowed(url):
    return True


def check_batch(data, path, styles, report):
    if data is not None:
        report.error(path, 'Originals batches have no batch-level projectData; use null')


def check_episode(episode, path, styles, report, today):
    data, dpath = episode['projectData'], path + '.projectData'
    if not lc._keys(report, dpath, data, EPISODE_DATA):
        return {}
    subject = data['subject']
    if lc._keys(report, dpath + '.subject', subject, ('kind', 'title', 'year')):
        if subject['kind'] not in SUBJECT_KINDS:
            report.error(dpath + '.subject.kind', f"Use one of {', '.join(SUBJECT_KINDS)}")
        if not lc._is_str(subject['title']):
            report.error(dpath + '.subject.title', 'Required text')
        year = subject['year']
        if year is not None and (not isinstance(year, int) or isinstance(year, bool) or not -3000 <= year <= today.year + 5):
            report.error(dpath + '.subject.year', 'A year or null')
    sources = data['sources']
    recap = episode['format'] in ('movie-recap', 'story-recap')
    if not isinstance(sources, list) or (recap and not sources):
        report.error(dpath + '.sources', 'List of sources; a recap needs at least one')
    else:
        for j, source in enumerate(sources):
            spath = f'{dpath}.sources[{j}]'
            if not lc._keys(report, spath, source, ('title', 'url', 'retrieved')):
                continue
            if not lc._https(source['url']):
                report.error(spath + '.url', 'HTTPS URL required')
            lc._date(report, spath + '.retrieved', source['retrieved'], today)
            if not lc._is_str(source['title']):
                report.error(spath + '.title', 'Required text')
    checks = data['checks']
    if lc._keys(report, dpath + '.checks', checks, CHECKS):
        for key in CHECKS:
            if checks[key] is not True:
                report.error(f'{dpath}.checks.{key}', 'The reviewer must pass this check (true)', 'check')
    if not lc._is_str(data['reviewer']):
        report.error(dpath + '.reviewer', 'Required text')
    series = data['series']
    if series is None:
        if episode['format'] == 'animated-short':
            report.error(dpath + '.series', 'An animated short names its series')
    elif lc._keys(report, dpath + '.series', series, ('seriesId', 'episode')):
        if not isinstance(series['seriesId'], str) or not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', series['seriesId']):
            report.error(dpath + '.series.seriesId', 'Lowercase [a-z0-9-]')
        if not lc._positive_int(series['episode']):
            report.error(dpath + '.series.episode', 'Positive integer required')

    credits = episode['credits'] if isinstance(episode['credits'], list) else []
    kinds = {c.get('kind') for c in credits if isinstance(c, dict)}
    if recap and 'footage' not in kinds:
        report.error(path + '.credits', 'A recap credits its footage', 'credits')
    return {}
