"""Small, durable publisher for Raspberry Pi. No dependencies; network disabled in dry runs.

Publication adapters must return a remote receipt, never merely HTTP success.
Crash after dispatch is intentionally uncertain: reconciliation precedes any retry.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import traceback
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
PLATFORMS = {"facebook", "instagram", "threads", "x", "youtube", "tiktok"}
REVIEW = ("uncertain", "dispatching", "blocked", "failed")
# Set by main() for monitored.py: the last health report, which carries only fixed categories.
LAST_REPORT = {}


def iso(now):
    return now.astimezone(UTC).isoformat()


def aware(value):
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else None


def fingerprint(config):
    scope = {k: config[k] for k in ("timezone", "schedule", "format", "channels", "media", "bufferOrganizationId")}
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def validate(config, live=False):
    if set(config["channels"]) not in (PLATFORMS, PLATFORMS | {"bluesky"}):
        raise ValueError("Six core channels and optional Bluesky entry required")
    enabled = [c for c in config["channels"].values() if c["enabled"]]
    if sum(c["route"] == "buffer" for c in enabled) > 3:
        raise ValueError("Buffer Free permits at most three channels")
    if not 1 <= config["queueDays"] <= 7:
        raise ValueError("Rolling queue must be 1–7 days")
    if config["media"]["maxFileBytes"] > 24_000_000:
        raise ValueError("Media must stay below the free Pages file ceiling")
    if not enabled:
        return
    ZoneInfo(config["timezone"])
    dt.time.fromisoformat(config["schedule"]["time"])
    if not config["schedule"]["weekdays"] or any(d not in range(7) for d in config["schedule"]["weekdays"]):
        raise ValueError("Invalid posting weekdays")
    if config["format"] not in ("chained", "self-contained", "comparison"):
        raise ValueError("Unknown format")
    for platform, c in config["channels"].items():
        if not c["enabled"]:
            continue
        previous_ids = c.get('previousAccountIds', [])
        if (not isinstance(previous_ids, list)
                or any(not isinstance(value, str) or not value.strip() for value in previous_ids)
                or len(set(previous_ids)) != len(previous_ids)
                or c.get('accountId') in previous_ids):
            raise ValueError('Invalid previous account identifiers')
        if platform == "tiktok" and c["route"] != "buffer":
            raise ValueError("TikTok requires the verified Buffer route")
        if platform == 'bluesky' and c['route'] != 'bluesky':
            raise ValueError('Bluesky requires the verified direct video route')
        if platform == 'facebook' and c['route'] != 'facebook':
            raise ValueError('Facebook requires the verified Page Reels route')
        if c["route"] != "buffer" and not (platform in ('threads', 'instagram') and c["route"] == platform and (platform != 'threads' or c.get("threadsFormat") in ("native_poll", "video"))) and not (platform in ('bluesky', 'facebook') and c['route'] == platform):
            raise ValueError("Direct Meta adapters remain disabled pending eligibility review")
        if not all(c.get(k) for k in ("accountId", "profileUrl", "identityVerified", "publishingVerified")):
            raise ValueError("Account identity and publishing eligibility must be verified")
    if live:
        approval = config.get("approval") or {}
        if approval.get("scopeHash") != fingerprint(config) or not approval.get("approvedAt"):
            raise ValueError("Explicit approval for this exact scope is missing")
        if not approval.get("deploymentApproved") or not approval.get("zeroSpendVerified"):
            raise ValueError("Deployment and zero-spend controls not approved/verified")
        if not approval.get("monitoringVerified") or not approval.get("mediaDeliveryVerified"):
            raise ValueError("External outage alert and public media delivery must be verified")


class Ledger:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, platform TEXT NOT NULL, account TEXT NOT NULL,
                slot TEXT NOT NULL, episode TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready', attempts INTEGER NOT NULL DEFAULT 0,
                retry_at REAL NOT NULL DEFAULT 0, remote_id TEXT, permalink TEXT,
                published_at TEXT, error TEXT, dispatched_at TEXT,
                UNIQUE(platform, account, slot), UNIQUE(platform, account, episode)
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, job TEXT, kind TEXT, at TEXT, detail TEXT
            );
            CREATE TABLE IF NOT EXISTS calls (at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS health (id INTEGER PRIMARY KEY CHECK(id=1), checked_at TEXT);
        """)
        # run: the tick that wrote the event; info: JSON of ids, counters and exception names, never response text.
        columns = {r["name"] for r in self.db.execute("PRAGMA table_info(events)")}
        with self.db:
            for column in ("run", "info"):
                if column not in columns:
                    self.db.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
        self.run = None

    def event(self, job, kind, detail="", info=None):
        self.db.execute("INSERT INTO events(job,kind,at,detail,run,info) VALUES(?,?,?,?,?,?)",
                        (job, kind, iso(dt.datetime.now(UTC)), detail, self.run,
                         json.dumps(info, sort_keys=True) if info else None))

    def enqueue(self, platform, account, slot, payload):
        # Payload is an immutable reviewed snapshot. No regeneration after uncertain sends.
        key = hashlib.sha256(f"{platform}|{account}|{slot}".encode()).hexdigest()[:24]
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO jobs(id,platform,account,slot,episode,payload) VALUES(?,?,?,?,?,?)",
                            (key, platform, account, slot, payload["episode"]["id"], json.dumps(payload, sort_keys=True)))
        return key

    def update(self, key, status, info=None, **values):
        allowed = {"attempts", "retry_at", "remote_id", "permalink", "published_at", "error", "dispatched_at"}
        if not set(values) <= allowed:
            raise ValueError("Unknown ledger field")
        info = {**{k: values[k] for k in ("attempts", "remote_id", "retry_at") if values.get(k) is not None}, **(info or {})}
        with self.db:
            sets = ["status=?"] + [f"{k}=?" for k in values]
            self.db.execute(f"UPDATE jobs SET {','.join(sets)} WHERE id=?", [status, *values.values(), key])
            self.event(key, status, values.get("error", ""), info)

    def set_payload(self, key, payload):
        with self.db:
            self.db.execute("UPDATE jobs SET payload=? WHERE id=? AND status='ready'", (json.dumps(payload,sort_keys=True),key))

    def consume_call(self, now):
        # Shared conservative margin under Buffer's 100/250/3000 limits.
        with self.db:
            for seconds, limit in ((900, 80), (86400, 200), (2592000, 2400)):
                count = self.db.execute("SELECT count(*) FROM calls WHERE at>?", (now-seconds,)).fetchone()[0]
                if count >= limit:
                    raise RuntimeError("local_api_budget_exhausted")
            self.db.execute("INSERT INTO calls VALUES(?)", (now,))
            self.db.execute("DELETE FROM calls WHERE at<?", (now-2592000,))


@contextlib.contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as handle:
        # Empty file; 0644 so the self-update user (scalar-social-update) can flock it read-only.
        os.chmod(path, 0o644)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def slots(config, now):
    zone = ZoneInfo(config["timezone"])
    local = now.astimezone(zone)
    hour, minute = map(int, config["schedule"]["time"].split(":"))
    for offset in range(config["queueDays"]):
        date = local.date() + dt.timedelta(days=offset)
        if date.weekday() not in config["schedule"]["weekdays"]:
            continue
        value = dt.datetime.combine(date, dt.time(hour, minute), zone)
        # Spring-forward nonexistent wall times are skipped; fall-back uses fold=0 once.
        if value.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != value.replace(tzinfo=None):
            continue
        if value >= local-dt.timedelta(minutes=config["schedule"]["maxLatenessMinutes"]):
            yield iso(value)


def recent_missed(db, now, hours=24):
    """Posts expired for a missed slot in the last `hours`: alerted for a day, then left to the history."""
    since = iso(now-dt.timedelta(hours=hours))
    return db.execute("SELECT count(*) FROM events WHERE kind='expired' AND detail='missed_slot' AND at>?", (since,)).fetchone()[0]


def attention(db):
    """{platform: [statuses needing review]} for the alert text."""
    out = {}
    for row in db.execute(f"SELECT DISTINCT platform,status FROM jobs WHERE status IN ({','.join('?'*len(REVIEW))}) ORDER BY platform,status", REVIEW):
        out.setdefault(row[0], []).append(row[1])
    return out


def crash_info(error):
    """Exception class and innermost frame only: messages can carry response data, so they are never kept."""
    frames = traceback.extract_tb(error.__traceback__)
    where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}:{frames[-1].name}" if frames else "unknown"
    return {"exception": type(error).__name__, "where": where}


def run_jobs(ledger, config, adapter, now, pause=lambda: False, prepare=None):
    if config["paused"] or pause():
        return
    for row in ledger.db.execute("SELECT * FROM jobs ORDER BY slot,id").fetchall():
        if pause():
            return
        channel = config["channels"].get(row["platform"], {})
        if not channel.get("enabled") or row["account"] != channel.get("accountId"):
            continue
        if row["status"] in ("confirmed", "failed", "expired", "blocked"):
            continue
        if row["retry_at"] > now.timestamp():
            continue
        payload = json.loads(row["payload"])
        due = dt.datetime.fromisoformat(row["slot"])
        extra = {}
        companion = payload.get("companion")
        if companion:
            delay = companion.get("delayMinutes", 0)
            if (not isinstance(companion.get("parentEpisode"), str) or not isinstance(delay, int)
                    or isinstance(delay, bool) or delay < 0):
                if row["status"] == "ready":
                    ledger.update(row["id"], "blocked", error="rejected")
                continue
            parent = ledger.db.execute("SELECT * FROM jobs WHERE platform=? AND account=? AND episode=?",
                                       (row["platform"], row["account"], companion["parentEpisode"])).fetchone()
            # A parent that ended without a usable post ends its companions too: final, not "needs review".
            if row["status"] == "ready" and (parent["status"] in ("failed", "expired", "blocked")
                                             or (parent["status"] == "confirmed" and not parent["remote_id"]) if parent
                                             else now-due > dt.timedelta(days=7)):
                ledger.update(row["id"], "expired", error="parent_unavailable")
                continue
            if not parent or parent["status"] != "confirmed":
                continue
            published = aware(parent["published_at"]) or aware(parent["dispatched_at"]) or due
            due = max(due, published+dt.timedelta(minutes=delay))
            # Sent copy only: the ledger keeps the approved snapshot unchanged.
            extra = {"parent": {"remoteId": parent["remote_id"], "permalink": parent["permalink"]}}
        if due > now:
            continue
        # Serial chains: unresolved earlier publication holds later content on this account.
        # Companions are not chain links (their parent gate serializes them), so they never hold later rows.
        pending = ledger.db.execute("SELECT 1 FROM jobs WHERE platform=? AND account=? AND slot<? AND status IN ('dispatching','uncertain','accepted') AND instr(episode,'#')=0",
                                    (row["platform"], row["account"], row["slot"])).fetchone()
        if pending:
            continue
        try:
            if row["status"] in ("dispatching", "uncertain", "accepted"):
                receipt = adapter.reconcile(dict(row), {**payload, **extra})
                if receipt.get("status") == "confirmed":
                    ledger.update(row["id"], "confirmed", remote_id=receipt["remoteId"],
                                  permalink=receipt["permalink"], published_at=receipt["publishedAt"], error=None)
                elif receipt.get("status") == "failed":
                    ledger.update(row["id"], "failed", error="remote_rejected")
                else:
                    # Absence from a bounded feed is never proof that dispatch failed.
                    ledger.update(row["id"], "uncertain", retry_at=now.timestamp()+3600, error="remote_confirmation_pending")
                continue
            if (now-due).total_seconds() > config["schedule"]["maxLatenessMinutes"]*60:
                ledger.update(row["id"], "expired", error="missed_slot")
                continue
            if row["attempts"] >= 3:
                ledger.update(row["id"], "failed", error="retry_limit")
                continue
            if prepare:
                payload = prepare(dict(row), payload)
                ledger.set_payload(row["id"],payload)
            if pause():
                return
            # Commit intent before request; power loss here requires reconciliation on restart.
            ledger.update(row["id"], "dispatching", attempts=row["attempts"]+1, dispatched_at=iso(now))
            # Adapters read the committed intent (Bluesky derives its record key from dispatched_at).
            job = ledger.db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            receipt = adapter.publish(dict(job), {**payload, **extra})
            ledger.update(row["id"], "accepted", remote_id=receipt["remoteId"], error=None,
                          retry_at=now.timestamp()+300)
        except Exception as error:
            # Adapter errors contain only categories, never response bodies/credentials.
            kind = getattr(error, "category", "uncertain")
            retry_at = now.timestamp()+max(300, getattr(error, "retry_after", 3600))
            # Anything that is not a categorized PublishError may be a code bug: keep where it happened.
            info = None if hasattr(error, "category") else crash_info(error)
            if info:
                print(f"run={ledger.run} job={row['id']} platform={row['platform']} {info['exception']} at {info['where']}",
                      file=sys.stderr)
            if kind == "rate_limit":
                status = "uncertain" if row["status"] in ("dispatching", "uncertain", "accepted") else "ready"
                ledger.update(row["id"], status, retry_at=retry_at, error="rate_limit")
            elif kind in ("authorization", "rejected", "budget", "media"):
                ledger.update(row["id"], "blocked", error=kind)
            else:
                ledger.update(row["id"], "uncertain", info, retry_at=retry_at, error="uncertain_response")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "dry-run", "tick", "pause", "scope"))
    parser.add_argument("--config", default="publisher/config.json")
    parser.add_argument("--state", default=os.path.expanduser("~/.local/state/scalar-social"))
    parser.add_argument("--manifest", help="Reviewed rendered queue manifest")
    parser.add_argument("--catalog", help="Reviewed batch clip catalogue")
    args = parser.parse_args()
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    pause_file = state/"PAUSED"
    if args.command == "pause":
        pause_file.touch(mode=0o600)
        print("Paused. Accepted remote requests still require reconciliation/cancellation.")
        return
    config = json.loads(Path(args.config).read_text())
    validate(config, live=args.command == "tick")
    if args.command == "scope":
        print(fingerprint(config))
        return
    with lock(state/"runner.lock"):
        ledger = Ledger(state/"ledger.sqlite3")
        ledger.run = os.urandom(6).hex()
        now = dt.datetime.now(UTC)
        exhausted=[]
        if args.command == "tick" and not config["paused"] and not pause_file.exists():
            if args.manifest:
                raw_manifest = Path(args.manifest).read_bytes()
                if hashlib.sha256(raw_manifest).hexdigest() != (config.get("approval") or {}).get("manifestSha256"):
                    raise ValueError("Queue manifest not approved")
                manifest = json.loads(raw_manifest)
                if manifest.get("scopeHash") != fingerprint(config):
                    raise ValueError("Manifest does not match approved scope")
                for job in manifest["jobs"]:
                    c = config["channels"][job["platform"]]
                    if c["enabled"]:
                        ledger.enqueue(job["platform"], c["accountId"], job["slot"], job["payload"])
            from buffer_adapter import BufferAdapter
            from threads_adapter import ThreadsAdapter, Router
            from bluesky_adapter import BlueskyAdapter
            from facebook_adapter import FacebookAdapter
            from instagram_adapter import InstagramAdapter
            adapter = Router(BufferAdapter(ledger, config), ThreadsAdapter(ledger, config,pause_check=pause_file.exists), BlueskyAdapter(ledger, config,pause_check=pause_file.exists), FacebookAdapter(ledger, config,pause_check=pause_file.exists), InstagramAdapter(ledger, config,pause_check=pause_file.exists))
            if args.catalog:
                from prepare import BatchPreparer
                preparer=BatchPreparer(ledger,config,state,Path(args.catalog))
                preparer.fill(now)
                exhausted=preparer.exhausted
                run_jobs(ledger, config, adapter, now, pause_file.exists, preparer.prepare)
            else:
                run_jobs(ledger, config, adapter, now, pause_file.exists)
        with ledger.db:
            ledger.db.execute("INSERT OR REPLACE INTO health VALUES(1,?)", (iso(now),))
        summary = {r["status"]: r["n"] for r in ledger.db.execute("SELECT status,count(*) AS n FROM jobs GROUP BY status")}
        missed = recent_missed(ledger.db, now)
        ok = not (exhausted or missed or any(summary.get(k) for k in ("uncertain", "blocked", "failed")))
        report = {"checkedAt":iso(now),"run":ledger.run,"ok":ok,"paused":config["paused"] or pause_file.exists(),
                  "channels":{k:{"enabled":v["enabled"],"profileUrl":v["profileUrl"],"reason":v.get("reason")} for k,v in config["channels"].items()},
                  "jobs":summary,"attention":attention(ledger.db),"missedLast24h":missed,
                  "contentExhausted":exhausted,"networkEnabled":args.command=="tick" and not config["paused"] and not pause_file.exists()}
        LAST_REPORT.clear()
        LAST_REPORT.update(report)
        temp = state/"health.tmp"
        temp.write_text(json.dumps(report, indent=2)+"\n")
        temp.replace(state/"health.json")
        print(json.dumps(report, indent=2))
        if not ok:
            sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError):
        print("Runner stopped: configuration, lock, storage or validation failure; inspect local configuration.", file=sys.stderr)
        sys.exit(1)
