"""Private local creation records, separate from the publishing batch contract."""
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid
import urllib.parse


FILE_CAP = 256 * 1024 * 1024
SLUG = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')
FILENAME = re.compile(r'^[a-zA-Z0-9_-]{1,96}\.(?:mp4|webm|mov|jpg|jpeg|png|json|txt)$')
PROJECTS = {'scalargame', 'explainers', 'marathon', 'originals'}
MEDIA = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.json': 'application/json', '.txt': 'text/plain'}


class CreationError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class CreationStore:
    def __init__(self, root, probe=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.probe = probe

    def _path(self, identity):
        if not isinstance(identity, str) or not SLUG.fullmatch(identity):
            raise CreationError(422, 'Production or file identity is invalid.')
        return self.root / f'{identity}.json'

    def _read(self, identity):
        path = self._path(identity)
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            raise CreationError(404, 'Production was not found.') from None
        except (OSError, ValueError):
            raise CreationError(500, 'Production record is unreadable.') from None

    def _write(self, record):
        path = self._path(record['id'])
        fd, temp = tempfile.mkstemp(dir=self.root, prefix='.production-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def list(self):
        items = []
        for path in self.root.glob('*.json'):
            try:
                items.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda x: x.get('updatedAt', ''), reverse=True)

    def get(self, identity):
        return self._read(identity)

    def create(self, body):
        if not isinstance(body, dict) or not isinstance(body.get('project'), str) or body.get('project') not in PROJECTS or not isinstance(body.get('brief'), str) or not body['brief'].strip() or len(body['brief']) > 12000:
            raise CreationError(422, 'Choose a project and enter a brief of at most 12,000 characters.')
        if body.get('title') is not None and (not isinstance(body['title'], str) or len(body['title']) > 160):
            raise CreationError(422, 'Title must be text of at most 160 characters.')
        if body.get('options') is not None and (not isinstance(body['options'], dict) or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 80 or len(v) > 500 for k, v in body['options'].items())):
            raise CreationError(422, 'Options must contain short text values.')
        identity = body.get('id')
        path = self._path(identity)
        existing = None
        try:
            existing = json.loads(path.read_text())
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            raise CreationError(500, 'Production record is unreadable.') from None
        payload = {k: body.get(k) for k in ('project', 'brief', 'title', 'options')}
        if existing:
            if existing.get('request') == payload:
                return existing
            raise CreationError(409, 'This production identity already belongs to a different brief.')
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        record = {'id': identity, **payload, 'request': payload, 'createdAt': now, 'updatedAt': now,
                  'currentRevisionId': None, 'revisions': [], 'research': {'status': 'not-started', 'version': 0, 'history': []}, 'decisions': [], 'manualDeliveries': []}
        self._write(record)
        return record

    def stage(self, identity, file_id, data, content_type):
        self._read(identity)
        if not FILENAME.fullmatch(file_id) or not data or len(data) > FILE_CAP:
            raise CreationError(422, 'Choose a non-empty file with a safe file identity.')
        ext = Path(file_id).suffix.lower()
        expected = MEDIA.get(ext)
        declared = content_type.split(';', 1)[0].strip().lower()
        if expected is None or declared != expected:
            raise CreationError(415, 'This file type is not supported or its content type does not match.')
        target_dir = self.root / identity / 'staging'
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = target_dir / file_id
        temp = target.with_name(f'.{file_id}.{uuid.uuid4().hex}.tmp')
        try:
            with open(temp, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()
        return {'fileId': file_id, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'mediaType': expected}

    def stage_stream(self, identity, file_id, reader, length, content_type):
        if length < 1 or length > FILE_CAP:
            raise CreationError(413, 'Artifact file is empty or exceeds the 256 MiB limit.')
        self._read(identity)
        if not FILENAME.fullmatch(file_id):
            raise CreationError(422, 'File identity must be a safe filename with a supported extension.')
        expected = MEDIA.get(Path(file_id).suffix.lower())
        if expected is None or content_type.split(';', 1)[0].strip().lower() != expected:
            raise CreationError(415, 'This file type is not supported or its content type does not match.')
        target_dir = self.root / identity / 'staging'
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = target_dir / file_id
        temp = target.with_name(f'.{file_id}.{uuid.uuid4().hex}.tmp')
        digest, consumed = hashlib.sha256(), 0
        try:
            with open(temp, 'wb') as stream:
                while consumed < length:
                    chunk = reader.read(min(65536, length - consumed))
                    if not chunk:
                        raise CreationError(400, 'Upload ended before all artifact bytes arrived.')
                    stream.write(chunk)
                    digest.update(chunk)
                    consumed += len(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()
        return {'fileId': file_id, 'size': consumed, 'sha256': digest.hexdigest(), 'mediaType': expected}

    def revise(self, identity, body):
        record = self._read(identity)
        manifest = body.get('manifest') if isinstance(body, dict) else None
        if not isinstance(manifest, dict) or manifest.get('productionId') != identity or manifest.get('project') != record['project']:
            raise CreationError(422, 'Manifest production identity or project does not match.')
        revision_id = manifest.get('revisionId')
        prior = next((r for r in record['revisions'] if r['id'] == revision_id), None) if isinstance(revision_id, str) else None
        if prior and prior.get('manifestData') == manifest:
            return record
        expected = body.get('expectedRevisionId')
        if expected != record['currentRevisionId']:
            raise CreationError(409, 'The production changed. Reload its current revision before importing.')
        if record['project'] == 'explainers' and body.get('expectedResearchVersion') != record['research'].get('version', 0):
            raise CreationError(409, 'The research context changed. Reload before returning a cut.')
        if not isinstance(revision_id, str) or not SLUG.fullmatch(revision_id) or revision_id in {r['id'] for r in record['revisions']}:
            raise CreationError(422, 'Revision identity is invalid or already exists.')
        for key in ('batchId', 'episodeId'):
            value = manifest.get(key)
            if value is not None and (not isinstance(value, str) or not SLUG.fullmatch(value)):
                raise CreationError(422, f'Manifest {key} must be a safe identity or null.')
        files = manifest.get('files')
        if not isinstance(files, list) or not files or len(files) > 64:
            raise CreationError(422, 'Manifest must identify at least one artifact file.')
        staging = self.root / identity / 'staging'
        checked = []
        seen_paths = set()
        video_count = 0
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not FILENAME.fullmatch(item['path']):
                raise CreationError(422, 'Manifest contains an unsafe artifact path.')
            if item['path'] in seen_paths or not isinstance(item.get('role'), str) or not item['role']:
                raise CreationError(422, 'Artifact paths must be unique and each file must have a role.')
            if item['role'] not in {'video', 'cover', 'thumbnail', 'caption', 'script', 'transcript', 'manifest', 'evidence'}:
                raise CreationError(422, 'Artifact role is not supported.')
            seen_paths.add(item['path'])
            file_id = item.get('fileId')
            if not isinstance(file_id, str) or not FILENAME.fullmatch(file_id):
                raise CreationError(422, 'Manifest file identity is invalid.')
            source = (staging / file_id).resolve()
            if not source.is_relative_to(staging.resolve()) or not source.is_file():
                raise CreationError(422, 'A listed staged artifact is missing.')
            digest_obj, size = hashlib.sha256(), 0
            with open(source, 'rb') as stream:
                while chunk := stream.read(65536):
                    digest_obj.update(chunk)
                    size += len(chunk)
            digest = digest_obj.hexdigest()
            with open(source, 'rb') as stream:
                header = stream.read(16)
            ext = Path(item['path']).suffix.lower()
            media_type = MEDIA.get(ext)
            if item.get('size') != size or item.get('sha256') != digest or item.get('mediaType') != media_type:
                raise CreationError(422, 'Artifact size, hash, or media type does not match its contents.')
            if item['role'] == 'video' and media_type not in {'video/mp4', 'video/webm', 'video/quicktime'}:
                raise CreationError(422, 'A video role must use a supported video media type.')
            if item['role'] in {'cover', 'thumbnail'} and media_type not in {'image/jpeg', 'image/png'}:
                raise CreationError(422, 'Cover and thumbnail roles must use a supported image type.')
            if item['role'] in {'caption', 'script', 'transcript', 'manifest'} and media_type not in {'application/json', 'text/plain'}:
                raise CreationError(422, 'Text artifact roles must use JSON or plain text.')
            if media_type == 'image/jpeg' and not header.startswith(b'\xff\xd8\xff'):
                raise CreationError(422, 'JPEG artifact bytes do not match their declared type.')
            if media_type == 'image/png' and not header.startswith(b'\x89PNG\r\n\x1a\n'):
                raise CreationError(422, 'PNG artifact bytes do not match their declared type.')
            if media_type == 'application/json':
                if size > 1_000_000:
                    raise CreationError(413, 'JSON artifacts are limited to 1 MB.')
                try:
                    json.loads(source.read_text())
                except (OSError, UnicodeError, ValueError):
                    raise CreationError(422, 'JSON artifact is not valid UTF-8 JSON.') from None
            if ext in {'.mp4', '.webm', '.mov'}:
                video_count += 1
                if not self.probe:
                    raise CreationError(503, 'Media validation is unavailable; cut remains unchanged.')
                try:
                    facts = self.probe(source)
                    videos = [s for s in facts.get('streams', []) if s.get('codec_type') == 'video' and not (s.get('disposition') or {}).get('attached_pic')]
                    duration = float(facts.get('format', {}).get('duration', 0))
                    if len(videos) != 1 or not math.isfinite(duration) or duration <= 0 or not self._container_ok(source, ext):
                        raise ValueError('not playable')
                except Exception:
                    raise CreationError(422, 'Video file does not contain a recognized media container.')
            checked.append({k: item[k] for k in ('path', 'size', 'sha256', 'mediaType', 'role') if k in item} | {'fileId': file_id})
        if video_count < 1:
            raise CreationError(422, 'Each production revision must contain a playable video cut.')
        if not any(x['role'] == 'video' and x['mediaType'] == 'video/mp4' for x in checked):
            raise CreationError(422, 'A playable video artifact is required before review.')
        if record['project'] == 'originals':
            raise CreationError(423, 'Originals production is on hold; the owner must authorize a run and cost estimate.')
        if record['project'] == 'explainers' and record['research'].get('status') != 'accepted':
            raise CreationError(423, 'Accept the real research decision before returning a cut.')
        mapping = {k: manifest.get(k) for k in ('batchId', 'episodeId')}
        if record['revisions'] and record['revisions'][-1].get('manifest') != mapping:
            raise CreationError(422, 'Revision batch and episode mapping must match the existing production.')
        final_dir = self.root / identity / 'revisions' / revision_id
        final_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if final_dir.exists():
            shutil.rmtree(final_dir)
        temp_dir = Path(tempfile.mkdtemp(dir=final_dir.parent, prefix='.revision-'))
        try:
            for item in checked:
                shutil.copyfile(staging / item['fileId'], temp_dir / Path(item['path']).name)
            os.replace(temp_dir, final_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        revision = {'id': revision_id, 'createdAt': now, 'manifest': mapping, 'manifestData': manifest, 'artifacts': checked, 'cutApproval': None, 'researchVersion': record['research'].get('version', 0)}
        record['revisions'].append(revision)
        record['currentRevisionId'] = revision_id
        record['updatedAt'] = now
        try:
            self._write(record)
        except Exception:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return record

    def research(self, identity, body):
        record = self._read(identity)
        if record['project'] != 'explainers':
            raise CreationError(422, 'Research decisions apply only to Explainers.')
        if not isinstance(body, dict) or not isinstance(body.get('status'), str) or body.get('status') not in {'held', 'accepted'}:
            raise CreationError(422, 'Choose held or accepted for the research decision.')
        if body.get('expectedVersion') != record['research'].get('version', 0):
            raise CreationError(409, 'The research decision changed. Reload before deciding.')
        question, angle, sources = body.get('question'), body.get('angle'), body.get('sources')
        if not isinstance(question, str) or not question.strip() or len(question) > 12000 or not isinstance(angle, str) or not angle.strip() or len(angle) > 4000:
            raise CreationError(422, 'A research decision needs the original question and a proposed angle.')
        if not isinstance(sources, list) or len(sources) > 30 or any(not isinstance(s, str) or len(s) > 2000 or not re.fullmatch(r'https://[^\s]+', s) for s in sources):
            raise CreationError(422, 'Research sources must be a list of HTTPS URLs.')
        if body['status'] == 'accepted' and not sources:
            raise CreationError(422, 'Accepted research needs at least one source URL.')
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        previous = record['research']
        context_changed = any(previous.get(k) != v for k, v in (('status', body['status']), ('question', question), ('angle', angle), ('sources', sources)))
        history = previous.get('history', []) + ([{k: previous.get(k) for k in ('status', 'question', 'angle', 'sources', 'decidedAt')}] if previous.get('status') != 'not-started' else [])
        record['research'] = {'status': body['status'], 'question': question, 'angle': angle, 'sources': sources, 'decidedAt': now,
                              'version': previous.get('version', 0) + 1, 'history': history}
        record['updatedAt'] = now
        if context_changed:
            for revision in record['revisions']:
                revision['cutApproval'] = None
        self._write(record)
        return record

    def manual_delivery(self, identity, body):
        record = self._read(identity)
        if record['project'] != 'marathon':
            raise CreationError(422, 'Manual delivery reports apply only to Marathon.')
        if not isinstance(body, dict):
            raise CreationError(422, 'Manual delivery report must be an object.')
        record.setdefault('manualDeliveries', [])
        revision_id = body.get('expectedRevisionId')
        if revision_id != record['currentRevisionId']:
            raise CreationError(409, 'The production changed. Reload before recording delivery.')
        revision = next((r for r in record['revisions'] if r['id'] == revision_id), None)
        if not revision or (revision.get('cutApproval') or {}).get('revisionId') != revision_id:
            raise CreationError(409, 'Approve the current cut before recording manual delivery.')
        existing = next((d for d in record['manualDeliveries'] if d['revisionId'] == revision_id), None)
        if existing:
            return record
        url = body.get('url')
        if url is not None:
            parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme not in {'http', 'https'} or not parsed.netloc or len(url) > 2000:
                raise CreationError(422, 'Delivery link must be an HTTP or HTTPS URL.')
        record['manualDeliveries'].append({'revisionId': revision_id, 'reportedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'url': url})
        record['updatedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        self._write(record)
        return record

    def decide(self, identity, body):
        record = self._read(identity)
        if not isinstance(body, dict) or body.get('expectedRevisionId') != record['currentRevisionId']:
            raise CreationError(409, 'The production changed. Reload before deciding.')
        if record['project'] == 'explainers' and body.get('expectedResearchVersion') != record['research'].get('version', 0):
            raise CreationError(409, 'The research context changed. Reload before deciding.')
        revision = next((r for r in record['revisions'] if r['id'] == record['currentRevisionId']), None)
        if record['project'] == 'originals':
            raise CreationError(423, 'Originals production is on hold; the owner must authorize a run and cost estimate.')
        if record['project'] == 'explainers' and record['research'].get('status') != 'accepted':
            raise CreationError(423, 'Accept the real research decision before approving a cut.')
        if not revision:
            raise CreationError(409, 'There is no current cut to approve.')
        decision = body.get('decision')
        if not isinstance(decision, str) or decision not in {'approve-cut', 'request-revision'}:
            raise CreationError(422, 'Choose approve-cut or request-revision.')
        feedback = body.get('feedback')
        if feedback is not None and (not isinstance(feedback, list) or len(feedback) > 100 or any(not isinstance(x, dict) or not isinstance(x.get('text'), str) or len(x['text']) > 2000 for x in feedback)):
            raise CreationError(422, 'Feedback must be a list of short text notes.')
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        revision['cutApproval'] = {'revisionId': revision['id'], 'approvedAt': now, 'researchVersion': record['research'].get('version', 0)} if decision == 'approve-cut' else None
        record['decisions'].append({'revisionId': revision['id'], 'decision': decision, 'feedback': feedback, 'at': now})
        record['updatedAt'] = now
        self._write(record)
        return record

    @staticmethod
    def _container_ok(path, extension):
        with open(path, 'rb') as stream:
            header = stream.read(16)
        if extension == '.mp4':
            return len(header) >= 8 and header[4:8] == b'ftyp'
        if extension == '.webm':
            return header.startswith(b'\x1aE\xdf\xa3')
        return extension == '.mov' and len(header) >= 8 and header[4:8] in {b'ftyp', b'moov', b'mdat', b'wide'}
