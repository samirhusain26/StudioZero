"""Contract v2 rules for the scalargame project (docs/STUDIO_PLAN.md §5.3): quiz videos for scalargame.com.

Batch projectData = {sourceSnapshotHash}. Episode projectData = {game, difficulty, styleId, creative, evidence,
music} with the v1 rules (answer/choice/spoiler gate, evidence sources, uniqueAnswer). The link is required and
points at scalargame.com. contentIds keep the v1 questionId form (<game>:<id>), so v1 and v2 share the ledger.
"""
import re
import urllib.parse

import library_contract as lc

NAME = 'scalargame'
NAMESPACES = lc.GAMES
EPISODE_PREFIXES = lc.GAMES
FORMATS = {f: ('motion', None) for f in lc.FORMATS}
LINK_REQUIRED = True
POLL = True
ANSWER_REPLY = True
EPISODE_DATA = ('game', 'difficulty', 'styleId', 'creative', 'evidence', 'music')


def link_allowed(url):
    parts = urllib.parse.urlsplit(url)
    return f'{parts.scheme}://{parts.netloc}' == lc.SITE and re.fullmatch(r'/[a-z0-9/_-]*', parts.path or '') is not None


def check_batch(data, path, styles, report):
    if lc._keys(report, path, data, ('sourceSnapshotHash',)):
        if not isinstance(data['sourceSnapshotHash'], str) or not lc.SHA256.fullmatch(data['sourceSnapshotHash']):
            report.error(path + '.sourceSnapshotHash', 'Use a lowercase sha256 hex digest')
    for i, recipe in enumerate(styles.values()):
        if recipe.get('engine') != 'motion':
            report.error(f'batch.styleRecipes[{i}].engine', 'Scalargame styles are motion styles')


def check_episode(episode, path, styles, report, today):
    """projectData rules; returns the spoiler context for the core's text checks."""
    data, dpath = episode['projectData'], path + '.projectData'
    if not lc._keys(report, dpath, data, EPISODE_DATA):
        return {}
    game = data['game']
    if game not in lc.GAMES:
        report.error(dpath + '.game', 'Unknown game')
    elif isinstance(episode['episodeId'], str) and episode['episodeId'].split('-')[0] != game:
        report.error(path + '.episodeId', 'Prefixed by its game')
    if game in lc.GAMES and isinstance(episode['contentId'], str) and not episode['contentId'].startswith(f'{game}:'):
        report.error(path + '.contentId', f'Use {game}:<id> for a {game} episode', 'namespace')
    if data['difficulty'] not in lc.DIFFICULTIES:
        report.error(dpath + '.difficulty', 'Use approachable, moderate or challenging')
    if not isinstance(data['styleId'], str) or data['styleId'] not in styles:
        report.error(dpath + '.styleId', 'Must name a styleRecipe of this batch')

    creative, cpath = data['creative'], dpath + '.creative'
    terms, choice_labels, answer_labels = [], [], []
    if lc._keys(report, cpath, creative, ('hook', 'question', 'clues', 'choices', 'answer', 'answerAliases', 'explanation')):
        for key in ('hook', 'question', 'answer'):
            if not lc._is_str(creative[key]):
                report.error(f'{cpath}.{key}', 'Required text')
        if not isinstance(creative['explanation'], str):
            report.error(cpath + '.explanation', 'Text required (may be empty)')
        if not isinstance(creative['clues'], list) or not all(lc._is_str(c) for c in creative['clues']):
            report.error(cpath + '.clues', 'List of text')
        aliases = creative['answerAliases']
        if not isinstance(aliases, list) or not all(lc._is_str(a) for a in aliases):
            report.error(cpath + '.answerAliases', 'List of text')
            aliases = []
        if lc._is_str(creative['answer']):
            terms = sorted({lc.normalize(t) for t in [creative['answer'], *aliases] if lc.normalize(t)})
        choices = creative['choices']
        if choices is not None:
            if not isinstance(choices, list) or not 2 <= len(choices) <= 4:
                report.error(cpath + '.choices', '2–4 choices or null')
            else:
                for j, choice in enumerate(choices):
                    jpath = f'{cpath}.choices[{j}]'
                    if not lc._keys(report, jpath, choice, ('key', 'label')):
                        continue
                    if choice['key'] != 'ABCD'[j]:
                        report.error(jpath + '.key', 'Keys run A, B, C, D in order')
                    if not lc._is_str(choice['label']):
                        report.error(jpath + '.label', 'Required text')
                        continue
                    choice_labels.append(lc.normalize(choice['label']))
                    if lc.normalize(choice['label']) in terms:
                        answer_labels.append(lc.normalize(choice['label']))
                if terms and len(answer_labels) != 1:
                    report.error(cpath + '.choices', 'Choices must contain the answer exactly once', 'answer_choice')
                if len(set(choice_labels)) != len(choice_labels):
                    report.error(cpath + '.choices', 'Duplicate choice labels')

    evidence, epath = data['evidence'], dpath + '.evidence'
    if lc._keys(report, epath, evidence, ('sources', 'checks', 'reviewer')):
        sources = evidence['sources']
        if not isinstance(sources, list) or not sources:
            report.error(epath + '.sources', 'At least one source required')
        else:
            for j, source in enumerate(sources):
                spath = f'{epath}.sources[{j}]'
                if not lc._keys(report, spath, source, ('title', 'url', 'retrieved')):
                    continue
                if not lc._https(source['url']):
                    report.error(spath + '.url', 'HTTPS URL required')
                lc._date(report, spath + '.retrieved', source['retrieved'], today)
                if not lc._is_str(source['title']):
                    report.error(spath + '.title', 'Required text')
        if not isinstance(evidence['checks'], dict) or evidence['checks'].get('uniqueAnswer') is not True:
            report.error(epath + '.checks.uniqueAnswer', 'Answer uniqueness must be checked and true')
        if not lc._is_str(evidence['reviewer']):
            report.error(epath + '.reviewer', 'Required text')

    music = data['music']
    if music is not None and lc._keys(report, dpath + '.music', music, ('trackId', 'sha256', 'license')):
        if not isinstance(music['sha256'], str) or not lc.SHA256.fullmatch(music['sha256']):
            report.error(dpath + '.music.sha256', 'sha256 hex required')
        for key in ('trackId', 'license'):
            if not lc._is_str(music[key]):
                report.error(f'{dpath}.music.{key}', 'Required text')
    return {'terms': terms, 'choiceLabels': choice_labels, 'answerLabels': answer_labels}
