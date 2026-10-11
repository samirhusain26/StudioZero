"""Batch contract v1 (contract/BATCH_CONTRACT.md): Mac generation -> Pi publishing.

Stdlib only; the Mac packager and the Pi importer call the same functions, so a batch
the Mac accepts is one the Pi accepts. Media facts are re-measured with ffprobe and are
never trusted from batch.json.

    python3 contract/library_contract.py validate library/<batchId> [--json]
    python3 contract/library_contract.py finalize library/<batchId>
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse

SCHEMA_VERSION = 1
MARKER = 'READY_FOR_UPLOAD'
GAMES = ('scalar', 'continuum', 'whenabouts', 'tectonic')
FORMATS = ('progressive-clues', 'candidate-elimination', 'head-to-head', 'missing-slot',
           'guess-the-year', 'before-after', 'missing-country', 'neighbor-clues')
DIFFICULTIES = ('approachable', 'moderate', 'challenging')
CAPTION_PLATFORMS = ('instagram', 'facebook', 'threads', 'x', 'bluesky', 'tiktok')
# Platforms whose post text renders clickable links. `{link}` is refused elsewhere.
LINK_PLATFORMS = ('facebook', 'threads', 'x', 'bluesky')
# Own first comment/reply routes (PUBLISHING_PIPELINE_PLAN.md "Polls and comments").
# Facebook/YouTube/TikTok have no comment route in this build.
COMMENT_PLATFORMS = ('instagram', 'threads', 'bluesky', 'x')
ANSWER_REPLY_PLATFORMS = ('instagram', 'threads', 'bluesky')
MAX_VIDEO_BYTES = 24_000_000      # Cloudflare Pages free file ceiling
MAX_COVER_BYTES = 2_000_000
MAX_BATCH_JSON_BYTES = 1_000_000
SITE = 'https://www.scalargame.com'

# Text limits in Unicode code points (a conservative upper bound for graphemes).
CAPTION_LIMITS = {'instagram': 2200, 'facebook': 2200, 'threads': 500, 'x': 280,
                  'bluesky': 300, 'tiktok': 2200}
COMMENT_LIMITS = {'instagram': 2200, 'threads': 500, 'bluesky': 300, 'x': 280}
X_URL_WEIGHT = 23
YOUTUBE_TITLE_LIMIT = 100
YOUTUBE_DESCRIPTION_BYTES = 5000
ALT_TEXT_LIMIT = 1000
MAX_HASHTAGS = 30
POLL_OPTION_LIMIT = 25

BATCH_ID = re.compile(r'\d{4}-(0[1-9]|1[0-2])-[a-z0-9]+(-[a-z0-9]+)*')
PI_BATCH_ID = re.compile(r'(manual-\d{8}-[1-9][0-9]*|legacy-\d{4}-\d{2}-\d{2})')
EPISODE_ID = re.compile(r'(scalar|continuum|whenabouts|tectonic)-[a-z0-9]+(-[a-z0-9]+)*-[0-9]{3,}')
SHA256 = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{7,40}')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
UTC_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z')
FPS = re.compile(r'[1-9][0-9]*/[1-9][0-9]*')
PLACEHOLDER = re.compile(r'\{([^{}]*)\}')
SPACER_LINE = re.compile(r'[\s.·•⠀ㅤ​_-]*')


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, path, message, code='invalid'):
        self.errors.append({'code': code, 'path': path, 'message': message})

    def warn(self, path, message, code='warning'):
        self.warnings.append({'code': code, 'path': path, 'message': message})

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {'ok': self.ok, 'errors': self.errors, 'warnings': self.warnings}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def episode_metadata_hash(episode):
    """Hash of everything the owner approves; the Pi-owned eligibility status is excluded."""
    return hashlib.sha256(canonical({k: v for k, v in episode.items() if k != 'eligibility'})).hexdigest()


def caption_hash(episode):
    return hashlib.sha256(canonical(episode.get('publication') or {})).hexdigest()


def normalize(text):
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c)).casefold()
    return ' '.join(re.sub(r'[^\w]+', ' ', text).split())


def _spans(text, term):
    found, start = [], 0
    padded = f' {text} '
    needle = f' {term} '
    while (i := padded.find(needle, start)) != -1:
        found.append((i, i + len(term)))
        start = i + 1
    return found


def answer_mentions(text, terms, blank=()):
    """Number of separate answer mentions after removing distractor labels."""
    text = normalize(text)
    for other in sorted(blank, key=len, reverse=True):
        if other:
            text = f' {text} '.replace(f' {other} ', ' ' + '_' * len(other) + ' ').strip()
    spans = sorted(s for term in terms if term for s in _spans(text, term))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return len(merged)


def link_for(episode, platform):
    publication = episode['publication']
    query = urllib.parse.urlencode({'utm_source': platform, 'utm_medium': 'organic_social',
                                    'utm_campaign': publication['utmCampaign'],
                                    'utm_content': episode['episodeId']})
    return SITE + publication['deepLink'] + '?' + query


def expand(episode, platform, text):
    """Final text the Pi publishes: `{link}` expanded, nothing else changed."""
    return None if text is None else text.replace('{link}', link_for(episode, platform))


def text_length(platform, text):
    if platform == 'x':
        # X weighs each URL as 23 characters.
        urls = re.findall(r'https?://\S+', text)
        return len(re.sub(r'https?://\S+', '', text)) + X_URL_WEIGHT * len(urls)
    return len(text)


def _is_str(value, allow_empty=False):
    return isinstance(value, str) and (allow_empty or value.strip() != '')


def _date(report, path, value, today):
    if value is None:
        return None
    try:
        parsed = dt.date.fromisoformat(value) if isinstance(value, str) and DATE.fullmatch(value) else None
    except ValueError:
        parsed = None
    if parsed is None:
        report.error(path, 'Use YYYY-MM-DD or null')
    return parsed


def _keys(report, path, value, required, optional=()):
    if not isinstance(value, dict):
        report.error(path, 'Must be an object')
        return False
    missing = [k for k in required if k not in value]
    unknown = sorted(set(value) - set(required) - set(optional))
    for k in missing:
        report.error(f'{path}.{k}', 'Required field missing')
    for k in unknown:
        report.error(f'{path}.{k}', 'Unknown field (contract change needed)')
    return not missing


def validate_document(data, *, now=None, origin='mac', report=None):
    """Shape, enums, IDs, captions, spoilers. No file access."""
    report = report or Report()
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(dt.timezone.utc).date()
    if not _keys(report, 'batch', data, ('schemaVersion', 'batchId', 'createdAt', 'generator',
                                         'sourceSnapshotHash', 'styleRecipes', 'episodes')):
        return report
    if data['schemaVersion'] != SCHEMA_VERSION:
        report.error('batch.schemaVersion', f'Unsupported schemaVersion; this validator reads {SCHEMA_VERSION}')
        return report
    batch_id = data['batchId']
    if not isinstance(batch_id, str) or not (BATCH_ID.fullmatch(batch_id) or (origin == 'pi' and PI_BATCH_ID.fullmatch(batch_id))):
        report.error('batch.batchId', 'Use YYYY-MM-<slug>, lowercase [a-z0-9-]')
    if not isinstance(data['createdAt'], str) or not UTC_STAMP.fullmatch(data['createdAt']):
        report.error('batch.createdAt', 'Use a UTC ISO-8601 timestamp ending in Z')
    generator = data['generator']
    if _keys(report, 'batch.generator', generator, ('repoCommit', 'dirty', 'assetKitVersion')):
        if not isinstance(generator['repoCommit'], str) or not COMMIT.fullmatch(generator['repoCommit']):
            report.error('batch.generator.repoCommit', 'Use a lowercase git commit hash')
        if not isinstance(generator['dirty'], bool):
            report.error('batch.generator.dirty', 'Must be true or false')
        elif generator['dirty']:
            report.warn('batch.generator.dirty', 'Rendered from a working tree with uncommitted changes', 'dirty_generator')
        if not _is_str(generator['assetKitVersion']):
            report.error('batch.generator.assetKitVersion', 'Required text')
    if not isinstance(data['sourceSnapshotHash'], str) or not SHA256.fullmatch(data['sourceSnapshotHash']):
        report.error('batch.sourceSnapshotHash', 'Use a lowercase sha256 hex digest')
    styles = {}
    if not isinstance(data['styleRecipes'], list):
        report.error('batch.styleRecipes', 'Must be a list')
    else:
        for i, recipe in enumerate(data['styleRecipes']):
            path = f'batch.styleRecipes[{i}]'
            if not _keys(report, path, recipe, ('styleId', 'game', 'version', 'summary')):
                continue
            if not _is_str(recipe['styleId']) or recipe['styleId'] in styles:
                report.error(path + '.styleId', 'Required, unique styleId')
            if recipe['game'] not in GAMES:
                report.error(path + '.game', 'Unknown game')
            if not isinstance(recipe['version'], int) or isinstance(recipe['version'], bool) or recipe['version'] < 1:
                report.error(path + '.version', 'Positive integer required')
            if not _is_str(recipe['summary']):
                report.error(path + '.summary', 'Required text')
            styles[recipe['styleId']] = recipe
    episodes = data['episodes']
    if not isinstance(episodes, list) or not episodes:
        report.error('batch.episodes', 'At least one episode required')
        return report
    seen = set()
    for i, episode in enumerate(episodes):
        validate_episode(episode, f'episodes[{i}]', styles, today, report, origin)
        episode_id = episode.get('episodeId') if isinstance(episode, dict) else None
        if episode_id in seen:
            report.error(f'episodes[{i}].episodeId', 'Duplicate episodeId in batch')
        seen.add(episode_id)
    return report


def validate_episode(episode, path, styles, today, report, origin='mac'):
    required = ('episodeId', 'questionId', 'revision', 'game', 'format', 'language', 'difficulty',
                'styleId', 'experimentId', 'variantId', 'creative', 'evidence', 'music', 'video',
                'cover', 'publication', 'eligibility')
    if not _keys(report, path, episode, required):
        return
    episode_id, game = episode['episodeId'], episode['game']
    if game not in GAMES:
        report.error(path + '.game', 'Unknown game')
    if not isinstance(episode_id, str) or not EPISODE_ID.fullmatch(episode_id) or episode_id.split('-')[0] != game:
        report.error(path + '.episodeId', 'Use <game>-<format>-<nnn>, lowercase, prefixed by its game')
        episode_id = None
    question_id = episode['questionId']
    if (not isinstance(question_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:._#-]{0,119}', question_id)
            or '#' in question_id or (origin == 'mac' and not question_id.startswith(f'{game}:'))):
        report.error(path + '.questionId', 'Use <game>:<id>…, no spaces or #')
    if not isinstance(episode['revision'], int) or isinstance(episode['revision'], bool) or episode['revision'] < 1:
        report.error(path + '.revision', 'Positive integer required')
    if episode['format'] not in FORMATS:
        report.error(path + '.format', 'Unknown format (contract update needed)')
    if not isinstance(episode['language'], str) or not re.fullmatch(r'[a-z]{2}(-[A-Z]{2})?', episode['language']):
        report.error(path + '.language', 'Use a language tag such as en')
    if episode['difficulty'] not in DIFFICULTIES:
        report.error(path + '.difficulty', 'Use approachable, moderate or challenging')
    style = styles.get(episode['styleId'])
    if origin == 'mac' and (not style or style.get('game') != game):
        report.error(path + '.styleId', 'Must name a styleRecipe for the same game')
    for key in ('experimentId', 'variantId'):
        if episode[key] is not None and not _is_str(episode[key]):
            report.error(f'{path}.{key}', 'Text or null')

    creative = episode['creative']
    terms, choice_labels, answer_labels = [], [], []
    if _keys(report, path + '.creative', creative, ('hook', 'question', 'clues', 'choices', 'answer',
                                                     'answerAliases', 'explanation')):
        for key in ('hook', 'question', 'answer'):
            if not _is_str(creative[key]):
                report.error(f'{path}.creative.{key}', 'Required text')
        if not isinstance(creative['explanation'], str):
            report.error(path + '.creative.explanation', 'Text required (may be empty)')
        if not isinstance(creative['clues'], list) or not all(_is_str(c) for c in creative['clues']):
            report.error(path + '.creative.clues', 'List of text')
        aliases = creative['answerAliases']
        if not isinstance(aliases, list) or not all(_is_str(a) for a in aliases):
            report.error(path + '.creative.answerAliases', 'List of text')
            aliases = []
        if _is_str(creative['answer']):
            terms = sorted({normalize(t) for t in [creative['answer'], *aliases] if normalize(t)})
        choices = creative['choices']
        if choices is not None:
            if not isinstance(choices, list) or not 2 <= len(choices) <= 4:
                report.error(path + '.creative.choices', '2–4 choices or null')
            else:
                for j, choice in enumerate(choices):
                    cpath = f'{path}.creative.choices[{j}]'
                    if not _keys(report, cpath, choice, ('key', 'label')):
                        continue
                    if choice['key'] != 'ABCD'[j]:
                        report.error(cpath + '.key', 'Keys run A, B, C, D in order')
                    if not _is_str(choice['label']):
                        report.error(cpath + '.label', 'Required text')
                        continue
                    choice_labels.append(normalize(choice['label']))
                    if normalize(choice['label']) in terms:
                        answer_labels.append(normalize(choice['label']))
                if terms and len(answer_labels) != 1:
                    report.error(path + '.creative.choices', 'Choices must contain the answer exactly once', 'answer_choice')
                if len(set(choice_labels)) != len(choice_labels):
                    report.error(path + '.creative.choices', 'Duplicate choice labels')

    evidence = episode['evidence']
    if _keys(report, path + '.evidence', evidence, ('sources', 'checks', 'reviewer')):
        sources = evidence['sources']
        if not isinstance(sources, list) or not sources:
            report.error(path + '.evidence.sources', 'At least one source required')
        else:
            for j, source in enumerate(sources):
                spath = f'{path}.evidence.sources[{j}]'
                if not _keys(report, spath, source, ('title', 'url', 'retrieved')):
                    continue
                url = urllib.parse.urlsplit(source['url']) if isinstance(source['url'], str) else None
                if not url or url.scheme != 'https' or not url.hostname:
                    report.error(spath + '.url', 'HTTPS URL required')
                _date(report, spath + '.retrieved', source['retrieved'], today)
                if not _is_str(source['title']):
                    report.error(spath + '.title', 'Required text')
        if not isinstance(evidence['checks'], dict) or evidence['checks'].get('uniqueAnswer') is not True:
            report.error(path + '.evidence.checks.uniqueAnswer', 'Answer uniqueness must be checked and true')
        if not _is_str(evidence['reviewer']):
            report.error(path + '.evidence.reviewer', 'Required text')

    music = episode['music']
    if music is not None and _keys(report, path + '.music', music, ('trackId', 'sha256', 'license')):
        if not isinstance(music['sha256'], str) or not SHA256.fullmatch(music['sha256']):
            report.error(path + '.music.sha256', 'sha256 hex required')
        for key in ('trackId', 'license'):
            if not _is_str(music[key]):
                report.error(f'{path}.music.{key}', 'Required text')

    video = episode['video']
    if _keys(report, path + '.video', video, ('file', 'sha256', 'bytes', 'durationSeconds', 'width', 'height',
                                               'fps', 'videoCodec', 'audioCodec')):
        if episode_id and video['file'] != f'videos/{episode_id}.mp4':
            report.error(path + '.video.file', f'Must be videos/{episode_id}.mp4')
        _file_fields(report, path + '.video', video, MAX_VIDEO_BYTES)
        if not isinstance(video['durationSeconds'], (int, float)) or isinstance(video['durationSeconds'], bool) or video['durationSeconds'] <= 0:
            report.error(path + '.video.durationSeconds', 'Positive number required')
        w, h = video['width'], video['height']
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (w, h)) or w * 16 != h * 9:
            report.error(path + '.video.width', 'Integer 9:16 dimensions required')
        if not isinstance(video['fps'], str) or not FPS.fullmatch(video['fps']):
            report.error(path + '.video.fps', 'Use a rational such as 30/1')
        if video['videoCodec'] != 'h264':
            report.error(path + '.video.videoCodec', 'H.264 required')
        if video['audioCodec'] not in ('aac', None):
            report.error(path + '.video.audioCodec', 'AAC or null (silent)')

    cover = episode['cover']
    if _keys(report, path + '.cover', cover, ('file', 'sha256', 'bytes')):
        if episode_id and cover['file'] != f'covers/{episode_id}.jpg':
            report.error(path + '.cover.file', f'Must be covers/{episode_id}.jpg')
        _file_fields(report, path + '.cover', cover, MAX_COVER_BYTES)
        if episode_id and terms and answer_mentions(episode_id, terms):
            report.error(path + '.cover.file', 'Cover file name reveals the answer', 'spoiler')

    publication = episode['publication']
    if _keys(report, path + '.publication', publication,
             ('deepLink', 'utmCampaign', 'captions', 'youtube', 'altText', 'hashtags', 'credits', 'poll',
              'firstComment', 'answerReply')):
        _publication(report, path + '.publication', episode, publication, terms, choice_labels, answer_labels)

    eligibility = episode['eligibility']
    if _keys(report, path + '.eligibility', eligibility, ('status', 'notBefore', 'reviewBy', 'expiresAt')):
        allowed = ('qa-passed',) if origin == 'mac' else ('qa-passed', 'approved', 'withdrawn', 'expired')
        if eligibility['status'] not in allowed:
            report.error(path + '.eligibility.status', 'The Mac always sends qa-passed; only the Pi approves')
        not_before = _date(report, path + '.eligibility.notBefore', eligibility['notBefore'], today)
        review_by = _date(report, path + '.eligibility.reviewBy', eligibility['reviewBy'], today)
        expires = _date(report, path + '.eligibility.expiresAt', eligibility['expiresAt'], today)
        for key, value in (('reviewBy', review_by), ('expiresAt', expires)):
            if value and value < today:
                report.error(f'{path}.eligibility.{key}', 'Date is already in the past', 'expired')
        if not_before and expires and not_before > expires:
            report.error(path + '.eligibility.notBefore', 'notBefore is after expiresAt')


def _file_fields(report, path, value, cap):
    if not isinstance(value['sha256'], str) or not SHA256.fullmatch(value['sha256']):
        report.error(path + '.sha256', 'Lowercase sha256 hex required')
    if not isinstance(value['bytes'], int) or isinstance(value['bytes'], bool) or not 0 < value['bytes'] <= cap:
        report.error(path + '.bytes', f'1–{cap:,} bytes required')


def _text_checks(report, path, episode, platform, text, limit, terms, choice_labels, answer_labels, links):
    unknown = {p for p in PLACEHOLDER.findall(text) if p != 'link'}
    if unknown:
        report.error(path, 'Unknown placeholder; only {link} is expanded')
    if '{link}' in text and not links:
        report.error(path, 'This platform does not show clickable links; remove {link}', 'link')
    final = expand(episode, platform, text) if '{link}' in text else text
    if limit and text_length(platform, final) > limit:
        report.error(path, f'Too long for {platform}: {text_length(platform, final)} > {limit}', 'length')
    spoiler_check(report, path, text, terms, choice_labels, answer_labels)


def spoiler_check(report, path, text, terms, choice_labels, answer_labels, allow_choice_list=True):
    if not terms:
        return
    others = [label for label in choice_labels if label not in answer_labels]
    mentions = answer_mentions(text, terms, others)
    if not mentions:
        return
    listed = (allow_choice_list and answer_labels and mentions == 1
              and all(answer_mentions(text, [label]) for label in choice_labels))
    # The answer may appear only once, as one item of the complete choice list.
    if not listed:
        report.error(path, 'Reveals the answer (only answerReply may)', 'spoiler')


def _publication(report, path, episode, publication, terms, choice_labels, answer_labels):
    deep = publication['deepLink']
    if not isinstance(deep, str) or not re.fullmatch(r'/[a-z0-9/_-]*', deep) or '//' in deep or '..' in deep:
        report.error(path + '.deepLink', 'Site path such as /scalar')
    if not isinstance(publication['utmCampaign'], str) or not re.fullmatch(r'[a-z0-9_]{1,64}', publication['utmCampaign']):
        report.error(path + '.utmCampaign', 'Lowercase [a-z0-9_]')
    links_ok = not any(e['path'].startswith(path + '.deepLink') or e['path'].startswith(path + '.utmCampaign') for e in report.errors)
    captions = publication['captions']
    if not isinstance(captions, dict):
        report.error(path + '.captions', 'Object keyed by platform')
        captions = {}
    for platform in sorted(set(captions) - set(CAPTION_PLATFORMS)):
        report.error(f'{path}.captions.{platform}', 'Unknown caption platform')
    usable = 0
    for platform in CAPTION_PLATFORMS:
        text = captions.get(platform)
        if text is None:
            continue
        if not _is_str(text):
            report.error(f'{path}.captions.{platform}', 'Text or null')
            continue
        usable += 1
        if links_ok:
            _text_checks(report, f'{path}.captions.{platform}', episode, platform, text, CAPTION_LIMITS[platform],
                         terms, choice_labels, answer_labels, platform in LINK_PLATFORMS)
        if platform == 'instagram' and len(re.findall(r'(?<!\w)#\w+', text)) > MAX_HASHTAGS:
            report.error(f'{path}.captions.instagram', f'More than {MAX_HASHTAGS} hashtags')
    youtube = publication['youtube']
    if youtube is not None and _keys(report, path + '.youtube', youtube, ('title', 'description')):
        usable += 1
        for key in ('title', 'description'):
            value = youtube[key]
            if not isinstance(value, str) or (key == 'title' and not value.strip()):
                report.error(f'{path}.youtube.{key}', 'Text required')
                continue
            if '<' in value or '>' in value:
                report.error(f'{path}.youtube.{key}', 'YouTube rejects < and >')
            if '{link}' in value or PLACEHOLDER.search(value):
                report.error(f'{path}.youtube.{key}', 'No placeholders in YouTube text', 'link')
            spoiler_check(report, f'{path}.youtube.{key}', value, terms, choice_labels, answer_labels)
        if isinstance(youtube['title'], str) and len(youtube['title']) > YOUTUBE_TITLE_LIMIT:
            report.error(path + '.youtube.title', f'Over {YOUTUBE_TITLE_LIMIT} characters', 'length')
        if isinstance(youtube['description'], str) and len(youtube['description'].encode()) > YOUTUBE_DESCRIPTION_BYTES:
            report.error(path + '.youtube.description', f'Over {YOUTUBE_DESCRIPTION_BYTES} bytes', 'length')
    if not usable:
        report.error(path + '.captions', 'No platform has a caption; nothing could be scheduled')
    alt = publication['altText']
    if not _is_str(alt) or len(alt) > ALT_TEXT_LIMIT:
        report.error(path + '.altText', f'Required, at most {ALT_TEXT_LIMIT} characters')
    else:
        spoiler_check(report, path + '.altText', alt, terms, choice_labels, answer_labels)
    hashtags = publication['hashtags']
    if (not isinstance(hashtags, list) or len(hashtags) > MAX_HASHTAGS
            or not all(isinstance(t, str) and re.fullmatch(r'#\w{1,100}', t) for t in hashtags)):
        report.error(path + '.hashtags', 'List of #tags')
    if not isinstance(publication['credits'], list) or not all(_is_str(c) for c in publication['credits']):
        report.error(path + '.credits', 'List of text')
    poll = publication['poll']
    if poll is not None and _keys(report, path + '.poll', poll, ('question', 'options')):
        if not _is_str(poll['question']):
            report.error(path + '.poll.question', 'Required text')
        else:
            spoiler_check(report, path + '.poll.question', poll['question'], terms, choice_labels, answer_labels, False)
        options = poll['options']
        if (not isinstance(options, list) or not 2 <= len(options) <= 4
                or not all(isinstance(o, str) and 1 <= len(o) <= POLL_OPTION_LIMIT and o.strip() for o in options)):
            report.error(path + '.poll.options', f'2–4 options of 1–{POLL_OPTION_LIMIT} characters')
        elif terms and sum(normalize(o) in terms for o in options) != 1:
            report.error(path + '.poll.options', 'Options must contain the answer exactly once', 'answer_choice')
        elif len({normalize(o) for o in options}) != len(options):
            report.error(path + '.poll.options', 'Duplicate options')
    comments = publication['firstComment']
    if comments is not None:
        if not isinstance(comments, dict):
            report.error(path + '.firstComment', 'Object keyed by platform, or null')
            comments = {}
        for platform in sorted(set(comments) - set(COMMENT_PLATFORMS)):
            report.error(f'{path}.firstComment.{platform}', 'No comment route for this platform', 'route')
        for platform in COMMENT_PLATFORMS:
            text = comments.get(platform)
            if text is None:
                continue
            if not _is_str(text):
                report.error(f'{path}.firstComment.{platform}', 'Text or null')
            elif links_ok:
                _text_checks(report, f'{path}.firstComment.{platform}', episode, platform, text,
                             COMMENT_LIMITS[platform], terms, choice_labels, answer_labels, platform in LINK_PLATFORMS)
    reply = publication['answerReply']
    if reply is not None and _keys(report, path + '.answerReply', reply, ('text', 'delayHours')):
        text = reply['text']
        if not isinstance(text, str) or '\n' not in text or not SPACER_LINE.fullmatch(text.split('\n', 1)[0]) or not text.split('\n', 1)[1].strip():
            report.error(path + '.answerReply.text', 'Must open with a spacer line, then the reply')
        elif len(text) > min(COMMENT_LIMITS[p] for p in ANSWER_REPLY_PLATFORMS) or PLACEHOLDER.search(text):
            report.error(path + '.answerReply.text', 'Too long for every reply route, or contains a placeholder')
        delay = reply['delayHours']
        if not isinstance(delay, (int, float)) or isinstance(delay, bool) or not 0.25 <= delay <= 168:
            report.error(path + '.answerReply.delayHours', '0.25–168 hours')


def ffprobe_command():
    override = os.environ.get('SCALAR_FFPROBE')
    if override:
        return override.split()
    if Path('/usr/bin/ffprobe').exists():
        return ['/usr/bin/ffprobe']
    remotion = Path(__file__).resolve().parents[1] / 'engines/motion/node_modules/.bin/remotion'
    if remotion.exists():
        return [str(remotion), 'ffprobe']
    found = shutil.which('ffprobe')
    if found:
        return [found]
    raise RuntimeError('ffprobe unavailable; set SCALAR_FFPROBE')


def run_ffprobe(path):
    result = subprocess.run([*ffprobe_command(), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError('ffprobe could not read the file')
    return json.loads(result.stdout)


def mp4_faststart(path):
    """True when the moov box precedes mdat (progressive playback before full download)."""
    with open(path, 'rb') as handle:
        size = os.fstat(handle.fileno()).st_size
        offset = 0
        while offset + 8 <= size:
            handle.seek(offset)
            header = handle.read(16)
            length = int.from_bytes(header[:4], 'big')
            kind = header[4:8]
            if length == 1:
                length = int.from_bytes(header[8:16], 'big')
            elif length == 0:
                length = size - offset
            if kind == b'moov':
                return True
            if kind == b'mdat':
                return False
            if length < 8:
                return False
            offset += length
    return False


def measure(probe, path=None):
    """Re-measured media facts in batch.json vocabulary."""
    streams = probe.get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video' and not (s.get('disposition') or {}).get('attached_pic')]
    audios = [s for s in streams if s.get('codec_type') == 'audio']
    video = videos[0] if len(videos) == 1 else {}
    audio = audios[0] if len(audios) == 1 else {}
    try:
        duration = round(float(probe['format']['duration']), 3)
    except (KeyError, TypeError, ValueError):
        duration = None
    result = {
        'videoStreams': len(videos), 'audioStreams': len(audios),
        'videoCodec': video.get('codec_name'), 'pixFmt': video.get('pix_fmt'),
        'width': video.get('width'), 'height': video.get('height'),
        'fps': video.get('avg_frame_rate') if video.get('avg_frame_rate') not in (None, '0/0') else video.get('r_frame_rate'),
        'durationSeconds': duration,
        'audioCodec': audio.get('codec_name') if audio else None,
        'audioSampleRate': int(audio['sample_rate']) if audio.get('sample_rate') else None,
        'audioChannels': audio.get('channels') if audio else None,
    }
    if path is not None:
        result['bytes'] = Path(path).stat().st_size
        result['fastStart'] = mp4_faststart(path)
    return result


def fps_value(text):
    try:
        a, b = text.split('/')
        return int(a) / int(b)
    except (AttributeError, ValueError, ZeroDivisionError):
        return None


def media_errors(m, legacy=False):
    """Hard media rules every platform shares (BATCH_CONTRACT.md); returns plain messages.

    `legacy` tolerates full-range yuvj420p, which the already-published 2026-10-05 Pi
    clips use; new batches must be yuv420p."""
    errors = []
    if m['videoStreams'] != 1:
        errors.append('Exactly one video stream required')
    if m['videoCodec'] != 'h264':
        errors.append('Video must be H.264')
    if m['pixFmt'] != 'yuv420p' and not (legacy and m['pixFmt'] == 'yuvj420p'):
        errors.append('Pixel format must be yuv420p')
    w, h = m.get('width'), m.get('height')
    if not (isinstance(w, int) and isinstance(h, int) and w * 16 == h * 9):
        errors.append('Video must be 9:16 portrait')
    if m['audioStreams'] > 1:
        errors.append('At most one audio stream')
    elif m['audioStreams'] == 1 and (m['audioCodec'] != 'aac' or m['audioSampleRate'] != 48000 or m['audioChannels'] != 2):
        errors.append('Audio must be AAC 48 kHz stereo, or absent')
    if not m.get('durationSeconds') or m['durationSeconds'] <= 0:
        errors.append('Duration unreadable')
    if 'bytes' in m and not 0 < m['bytes'] <= MAX_VIDEO_BYTES:
        errors.append(f'File must be at most {MAX_VIDEO_BYTES:,} bytes')
    if m.get('fastStart') is False:
        errors.append('MP4 is not fast-start (moov after mdat); remux with -movflags +faststart')
    return errors


# Per-platform publishing limits applied when scheduling (not at import). Sources and
# check dates are recorded in publisher/docs/PLATFORM_MATRIX.md "Media and text limits used by the Pi scheduler".
PLATFORM_MEDIA = {
    'instagram': {'minSeconds': 3, 'maxSeconds': 900, 'minFps': 23, 'maxFps': 60},
    'facebook': {'minSeconds': 3, 'maxSeconds': 90, 'minFps': 24, 'maxFps': 60},
    'threads': {'minSeconds': 0, 'maxSeconds': 300, 'minFps': 23, 'maxFps': 60},
    'x': {'minSeconds': 0.5, 'maxSeconds': 140, 'minFps': 0, 'maxFps': 60},
    'youtube': {'minSeconds': 1, 'maxSeconds': 180, 'minFps': 0, 'maxFps': 60},
    'bluesky': {'minSeconds': 0, 'maxSeconds': 60, 'minFps': 0, 'maxFps': 60},
    'tiktok': {'minSeconds': 3, 'maxSeconds': 600, 'minFps': 23, 'maxFps': 60},
}


def platform_eligibility(m, legacy=False):
    """Per platform: (eligible, reason). Hard-rule failures disable every platform."""
    hard = media_errors(m, legacy)
    fps = fps_value(m.get('fps') or '')
    result = {}
    for platform, limit in PLATFORM_MEDIA.items():
        if hard:
            result[platform] = (False, hard[0])
        elif not limit['minSeconds'] <= (m['durationSeconds'] or 0) <= limit['maxSeconds']:
            result[platform] = (False, f"Duration must be {limit['minSeconds']}–{limit['maxSeconds']} s on {platform}")
        elif fps is None or (limit['minFps'] and fps < limit['minFps']) or fps > limit['maxFps']:
            result[platform] = (False, f'Frame rate outside {platform} limits')
        else:
            result[platform] = (True, None)
    return result


def compare_measured(report, path, declared, m):
    if m['durationSeconds'] is None or abs(m['durationSeconds'] - float(declared['durationSeconds'])) > 0.1:
        report.error(path + '.durationSeconds', f"Measured {m['durationSeconds']} s differs from batch.json", 'mismatch')
    for key in ('width', 'height', 'videoCodec', 'audioCodec'):
        if m[key] != declared[key]:
            report.error(f'{path}.{key}', f'Measured {m[key]!r} differs from batch.json', 'mismatch')
    if fps_value(m['fps'] or '') is None or abs(fps_value(m['fps']) - (fps_value(declared['fps']) or -1)) > 0.01:
        report.error(path + '.fps', f"Measured {m['fps']!r} differs from batch.json", 'mismatch')


def file_digest(path):
    digest, total = hashlib.sha256(), 0
    with open(path, 'rb') as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def is_jpeg(path):
    with open(path, 'rb') as handle:
        return handle.read(3) == b'\xff\xd8\xff'


def verify_video_file(report, path, episode, file_path, probe=run_ffprobe):
    """Hash, size and ffprobe re-measurement of one delivered video file."""
    declared = episode['video']
    digest, size = file_digest(file_path)
    if digest != declared['sha256']:
        report.error(path + '.sha256', 'File hash differs from batch.json', 'hash')
    if size != declared['bytes']:
        report.error(path + '.bytes', 'File size differs from batch.json', 'hash')
    try:
        m = measure(probe(file_path), file_path)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        report.error(path + '.file', f'Media could not be measured: {error}', 'media')
        return None
    for message in media_errors(m):
        report.error(path + '.file', message, 'media')
    compare_measured(report, path, declared, m)
    return m


def verify_cover_file(report, path, episode, file_path):
    declared = episode['cover']
    digest, size = file_digest(file_path)
    if digest != declared['sha256']:
        report.error(path + '.sha256', 'File hash differs from batch.json', 'hash')
    if size != declared['bytes']:
        report.error(path + '.bytes', 'File size differs from batch.json', 'hash')
    if not is_jpeg(file_path):
        report.error(path + '.file', 'Cover must be a JPEG', 'media')


def safe_member(root, relative):
    """Resolve a declared relative file inside the batch folder; refuse links and escapes."""
    if not isinstance(relative, str) or relative.startswith('/') or '\\' in relative or '..' in Path(relative).parts:
        return None
    candidate = Path(root) / relative
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(Path(root).resolve()):
        return None
    return candidate


def load_batch(batch_dir, report):
    path = Path(batch_dir) / 'batch.json'
    if not path.is_file() or path.is_symlink():
        report.error('batch.json', 'batch.json missing')
        return None, None
    raw = path.read_bytes()
    if len(raw) > MAX_BATCH_JSON_BYTES:
        report.error('batch.json', 'batch.json exceeds 1 MB')
        return None, raw
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        report.error('batch.json', f'Invalid JSON: {error}')
        return None, raw


def validate(batch_dir, *, now=None, probe=run_ffprobe, origin='mac'):
    """Full Mac-side validation: document, files, hashes, re-measured media."""
    batch_dir = Path(batch_dir)
    report = Report()
    data, raw = load_batch(batch_dir, report)
    if data is None:
        return report
    validate_document(data, now=now, origin=origin, report=report)
    if not report.ok:
        return report
    if data['batchId'] != batch_dir.name:
        report.error('batch.batchId', 'Folder name must equal batchId')
    for i, episode in enumerate(data['episodes']):
        for kind in ('video', 'cover'):
            path = f'episodes[{i}].{kind}'
            target = safe_member(batch_dir, episode[kind]['file'])
            if target is None:
                report.error(path + '.file', 'Path escapes the batch folder or is a link')
            elif not target.is_file():
                report.error(path + '.file', 'File missing', 'missing')
            elif kind == 'video':
                verify_video_file(report, path, episode, target, probe)
            else:
                verify_cover_file(report, path, episode, target)
    declared = {e[k]['file'] for e in data['episodes'] for k in ('video', 'cover')}
    for folder in ('videos', 'covers'):
        for extra in sorted((batch_dir / folder).glob('*')) if (batch_dir / folder).is_dir() else []:
            if f'{folder}/{extra.name}' not in declared:
                report.warn(f'{folder}/{extra.name}', 'Not referenced by batch.json; it will not be uploaded', 'unreferenced')
    marker = batch_dir / MARKER
    if marker.exists():
        try:
            recorded = json.loads(marker.read_text()).get('batchJsonSha256')
        except (ValueError, OSError):
            recorded = None
        if recorded != hashlib.sha256(raw).hexdigest():
            report.error(MARKER, 'batch.json changed after finalize; files are immutable once finalized', 'immutable')
    return report


def finalize(batch_dir, *, now=None, probe=run_ffprobe):
    batch_dir = Path(batch_dir)
    marker = batch_dir / MARKER
    report = validate(batch_dir, now=now, probe=probe)
    if not report.ok:
        return report
    if marker.exists():
        return report  # validate() already proved the marker matches this batch.json
    digest = hashlib.sha256((batch_dir / 'batch.json').read_bytes()).hexdigest()
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    body = json.dumps({'schemaVersion': SCHEMA_VERSION, 'batchJsonSha256': digest, 'finalizedAt': stamp,
                       'warnings': len(report.warnings)}, indent=2) + '\n'
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'w') as handle:
        handle.write(body)
    return report


def _print(report, as_json, action):
    if as_json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return
    for item in report.errors:
        print(f"ERROR   {item['path']}: {item['message']}")
    for item in report.warnings:
        print(f"WARNING {item['path']}: {item['message']}")
    if report.ok:
        print(f'{action}: passed with {len(report.warnings)} warning(s).')
    else:
        print(f'{action}: failed with {len(report.errors)} error(s).')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate or finalize a video batch (contract v1).')
    parser.add_argument('command', choices=('validate', 'finalize'))
    parser.add_argument('batch_dir')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = (finalize if args.command == 'finalize' else validate)(args.batch_dir)
    except (OSError, RuntimeError) as error:
        print(f'{args.command} could not run: {error}', file=sys.stderr)
        return 1
    _print(report, args.json, 'Finalize' if args.command == 'finalize' else 'Validation')
    if args.command == 'finalize' and report.ok:
        print(f'{MARKER} written; upload batch.json, videos/ and covers/ in the Pi UI.')
    return 0 if report.ok else 2


if __name__ == '__main__':
    sys.exit(main())
