"""Buffer GraphQL adapter. Free plan, automatic video publishing only.

Only categories leave this module on failures; remote error text can contain secrets.
See https://developers.buffer.com/reference.html . Live contract tests still required.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

FIELDS = "id status externalLink sentAt schedulingType channelId text"
# Documented shape (developers.buffer.com/examples/create-threaded-post.html): metadata.twitter.thread
# lists every post incl. the first; top-level text equals item 1. Media on item 1 is not yet live-tested.
X_THREAD_VERIFIED = False


class PublishError(Exception):
    def __init__(self, category, retry_after=3600):
        super().__init__(category)
        self.category = category
        self.retry_after = retry_after


def credential_permissions_ok(path, metadata):
    mode = stat.S_IMODE(metadata.st_mode)
    # systemd may use a root-owned 0440 file whose ACL grants only this service
    # access. The group bit is the ACL mask, not a grant to every group member.
    systemd_acl = (mode == 0o440 and metadata.st_uid == 0 and metadata.st_gid == 0
                   and str(path.resolve()).startswith('/run/credentials/'))
    return not (mode & 0o077) or systemd_acl


def secret():
    # Pi systemd LoadCredential creates a read-only, private runtime credential.
    root = os.environ.get("CREDENTIALS_DIRECTORY")
    if not root:
        raise PublishError("authorization")
    path = Path(root)/"BUFFER_API_KEY"
    if not credential_permissions_ok(path, path.stat()):
        raise PublishError("authorization")
    value = path.read_text().strip()
    if not value:
        raise PublishError("authorization")
    return value


def request(query, variables, token):
    req = urllib.request.Request("https://api.buffer.com", data=json.dumps({"query":query,"variables":variables}).encode(),
                                 headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            value = error.headers.get("Retry-After", "3600")
            try:
                seconds = max(1, int(value))
            except ValueError:
                seconds = 3600
            raise PublishError("rate_limit", seconds) from None
        if error.code in (401,403):
            raise PublishError("authorization") from None
        if error.code == 400:
            try:
                invalid = json.load(error)
                errors = invalid.get('errors', [])
                # GraphQL rejects validation/variable-coercion failures before
                # executing a mutation. No response text leaves the adapter.
                if errors and not invalid.get('data') and all(
                    not e.get('path') and (e.get('extensions',{}).get('code') == 'GRAPHQL_VALIDATION_FAILED'
                    or e.get('message','').startswith('Variable ') and 'got invalid value' in e.get('message',''))
                    for e in errors):
                    raise PublishError('rejected') from None
            except (ValueError, OSError):
                pass
        # A 5xx may follow a successful remote mutation: never retry blindly.
        raise PublishError("uncertain") from None
    except (OSError, ValueError):
        raise PublishError("uncertain") from None
    if body.get("errors"):
        codes = {e.get("extensions",{}).get("code") for e in body["errors"]}
        if codes & {"UNAUTHENTICATED", "FORBIDDEN", "UNAUTHORIZED"}:
            raise PublishError("authorization")
        if "RATE_LIMIT_EXCEEDED" in codes:
            raise PublishError("rate_limit")
        raise PublishError("uncertain")
    return body["data"]


def verify_media(payload, config):
    media = payload["media"]
    url = urllib.parse.urlsplit(media["url"])
    base = urllib.parse.urlsplit(config["media"]["baseUrl"] or "")
    if (url.scheme != "https" or not url.hostname or url.hostname != base.hostname
            or url.username or url.password or url.query or url.fragment
            or not url.path.endswith(".mp4")):
        raise PublishError("media")
    if not media.get("sha256") or not media.get("rightsReviewed"):
        raise PublishError("media")
    try:
        req = urllib.request.Request(media["url"], headers={"Accept":"video/mp4", "User-Agent":"ScalarMediaVerifier/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            final = urllib.parse.urlsplit(response.url)
            if final.scheme != 'https' or final.hostname != base.hostname or response.headers.get_content_type() != "video/mp4":
                raise PublishError("media")
            hasher = hashlib.sha256()
            size = 0
            while chunk := response.read(65536):
                size += len(chunk)
                if size > config["media"]["maxFileBytes"]:
                    raise PublishError("media")
                hasher.update(chunk)
            if not size or hasher.hexdigest() != media["sha256"]:
                raise PublishError("media")
    except (OSError, ValueError):
        raise PublishError("media") from None


class BufferAdapter:
    def __init__(self, ledger, config, transport=request, token_loader=secret):
        self.ledger = ledger
        self.config = config
        self.transport = transport
        self.token_loader = token_loader

    def call(self, query, variables):
        try:
            self.ledger.consume_call(time.time())
        except RuntimeError:
            raise PublishError("budget") from None
        return self.transport(query, variables, self.token_loader())

    def publish(self, job, payload):
        thread = payload.get("thread")
        # No Buffer route carries a separate companion job; X item 2 travels inside the parent.
        if payload.get("companion") or thread and (not X_THREAD_VERIFIED or job["platform"] != "x"
                or not isinstance(thread, list) or any(not isinstance(t, str) or not t.strip() for t in thread)):
            raise PublishError("rejected")
        verify_media(payload, self.config)
        # Query exact connected identity before each mutation; never trust the display name.
        channel = self.call("query($id:ChannelId!){channel(input:{id:$id}){id name service serviceId externalLink isDisconnected isLocked}}", {"id":job["account"]})["channel"]
        expected = self.config["channels"][job["platform"]]
        normalize = lambda value: (value or "").rstrip("/").lower()
        service = "twitter" if job["platform"] == "x" else job["platform"]
        urls = expected.get("allowedProfileUrls",[expected["profileUrl"]])
        provider_match = expected.get("providerAccountId") and channel["serviceId"] == expected["providerAccountId"]
        url_match = normalize(channel["externalLink"]) in {normalize(u) for u in urls}
        if (channel["id"] != job["account"] or channel["isDisconnected"] or channel["isLocked"]
                or channel["service"] != service or not (provider_match or url_match)):
            raise PublishError("authorization")
        post = {"channelId":job["account"],"text":payload["caption"],"assets":[{"video":{"url":payload["media"]["url"]}}],
                "mode":"shareNow","schedulingType":"automatic","needsApproval":False,"saveToDraft":False,
                "metadata":payload.get("metadata",{}),"source":"scalar-social"}
        if thread:
            post["metadata"] = {**(post["metadata"] or {}), "twitter":{"thread":[{"text":payload["caption"],"assets":post["assets"]}]+[{"text":t} for t in thread]}}
        data = self.call("mutation($input:CreatePostInput!){createPost(input:$input){__typename ... on PostActionSuccess{post{"+FIELDS+"}}}}", {"input":post})["createPost"]
        if data["__typename"] != "PostActionSuccess":
            # No retry for union errors; schema/format/permission must be reviewed.
            raise PublishError("rejected")
        result = data["post"]
        if result.get("schedulingType") != "automatic" or result["channelId"] != job["account"]:
            raise PublishError("uncertain")
        return {"remoteId":result["id"]}

    def reconcile(self, job, payload):
        remote_id = job["remote_id"]
        if remote_id:
            post = self.call("query($input:PostInput!){post(input:$input){"+FIELDS+"}}", {"input":{"id":remote_id}})["post"]
        else:
            # Search exact caption on exact channel; paginate only in bounded small batches.
            # Missing receipt never becomes permission to recreate an uncertain post.
            query = "query($input:PostsInput!,$after:String){posts(input:$input,first:50,after:$after){edges{node{"+FIELDS+"}} pageInfo{hasNextPage endCursor}}}"
            after = None
            matches = []
            for _ in range(4):
                data = self.call(query, {"input":{"organizationId":self.config["bufferOrganizationId"],"filter":{"channelIds":[job["account"]],"startDate":job["dispatched_at"]}},"after":after})["posts"]
                matches += [e["node"] for e in data.get("edges",[]) if e["node"]["text"] == payload["caption"]]
                if not data["pageInfo"]["hasNextPage"]:
                    break
                after = data["pageInfo"]["endCursor"]
            if len(matches) != 1:
                return {"status":"uncertain"}
            post = matches[0]
        if post["channelId"] != job["account"] or post["text"] != payload["caption"]:
            return {"status":"uncertain"}
        if post["status"] == "error":
            return {"status":"failed"}
        # Buffer 'sent' by itself is not sufficient; require automatic + network permalink.
        link = urllib.parse.urlsplit(post.get("externalLink") or "")
        domains = {"x":{"x.com","twitter.com","www.twitter.com"},"youtube":{"youtube.com","www.youtube.com","youtu.be"},
                   "instagram":{"instagram.com","www.instagram.com"},"facebook":{"facebook.com","www.facebook.com"},
                   "threads":{"threads.com","www.threads.com","threads.net","www.threads.net"},
                   "tiktok":{"tiktok.com","www.tiktok.com"}}
        if job['platform'] == 'tiktok':
            expected = urllib.parse.urlsplit(self.config['channels']['tiktok']['profileUrl'])
            video_path = re.fullmatch(r'/(@[^/]+)/video/[0-9]+/?', link.path)
            if (not video_path or '/'+video_path[1].lower() != expected.path.rstrip('/').lower()
                    or link.username or link.password or link.query or link.fragment):
                return {'status': 'uncertain'}
        if (post["status"] == "sent" and post.get("sentAt") and post.get("schedulingType") == "automatic"
                and link.scheme == "https" and link.hostname in domains[job["platform"]]):
            # The ledger records provider confirmation; first launch additionally needs browser proof.
            return {"status":"confirmed","remoteId":post["id"],"permalink":post["externalLink"],"publishedAt":post["sentAt"]}
        return {"status":"uncertain"}
