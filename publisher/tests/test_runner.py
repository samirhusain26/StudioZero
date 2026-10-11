import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"publisher/app"))
from runner import Ledger, UTC, fingerprint, lock, run_jobs, slots, validate
from buffer_adapter import BufferAdapter, PublishError


class Fake:
    def __init__(self, error=None, status="confirmed"):
        self.calls = []
        self.error = error
        self.status = status

    def publish(self, job, payload):
        self.calls.append("publish")
        if self.error:
            raise self.error
        return {"remoteId":"remote-1"}

    def reconcile(self, job, payload):
        self.calls.append("reconcile")
        return {"status":self.status,"remoteId":"remote-1","permalink":"https://x.com/test/status/1","publishedAt":"2026-10-05T12:01:00+00:00"}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/"state.sqlite")
        self.config = json.loads((ROOT/"publisher/config.example.json").read_text())
        self.config.update(paused=False, timezone="America/New_York")
        self.config["schedule"]["time"] = "08:00"
        self.config["channels"]["x"].update(enabled=True, accountId="x-1",identityVerified=True,publishingVerified=True)
        self.now = dt.datetime(2026,10,5,12,tzinfo=UTC)
        self.payload = {"episode":{"id":"ep01"},"caption":"test","media":{"url":"https://test.pages.dev/a.mp4"}}
        self.key = self.ledger.enqueue("x","x-1",self.now.isoformat(),self.payload)

    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()

    def row(self):
        return self.ledger.db.execute("SELECT * FROM jobs WHERE id=?",(self.key,)).fetchone()

    def test_success_is_accepted_then_confirmed(self):
        adapter = Fake()
        run_jobs(self.ledger,self.config,adapter,self.now)
        self.assertEqual(self.row()["status"],"accepted")
        run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(minutes=6))
        self.assertEqual(self.row()["status"],"confirmed")
        run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(minutes=7))
        self.assertEqual(adapter.calls,["publish","reconcile"])

    def test_publish_sees_committed_dispatch_intent(self):
        seen = []
        adapter = Fake()
        adapter.publish = lambda job, payload: seen.append(dict(job)) or {"remoteId":"remote-1"}
        run_jobs(self.ledger,self.config,adapter,self.now)
        self.assertEqual(seen[0]["dispatched_at"],self.now.isoformat())
        self.assertEqual((seen[0]["status"],seen[0]["attempts"]),("dispatching",1))

    def test_unexpected_exception_keeps_type_and_location_only(self):
        adapter = Fake()
        adapter.publish = lambda job, payload: {}["remoteId"]
        with contextlib.redirect_stderr(io.StringIO()) as err:
            run_jobs(self.ledger,self.config,adapter,self.now)
        self.assertEqual(self.row()["status"],"uncertain")
        event = self.ledger.db.execute("SELECT detail,info FROM events WHERE job=? ORDER BY seq DESC LIMIT 1",(self.key,)).fetchone()
        info = json.loads(event["info"])
        self.assertEqual((event["detail"],info["exception"]),("uncertain_response","KeyError"))
        self.assertRegex(info["where"],r"^test_runner\.py:\d+:<lambda>$")
        self.assertIn(f"job={self.key} platform=x KeyError at test_runner.py:", err.getvalue())

    def test_events_record_run_and_attempt(self):
        self.ledger.run = "run-1"
        run_jobs(self.ledger,self.config,Fake(),self.now)
        rows = self.ledger.db.execute("SELECT kind,run,info FROM events WHERE job=? ORDER BY seq",(self.key,)).fetchall()
        self.assertEqual([r["kind"] for r in rows],["dispatching","accepted"])
        self.assertTrue(all(r["run"]=="run-1" for r in rows))
        self.assertEqual(json.loads(rows[0]["info"])["attempts"],1)
        self.assertEqual(json.loads(rows[1]["info"])["remote_id"],"remote-1")

    def test_uncertain_never_republishes(self):
        adapter = Fake(error=TimeoutError(),status="uncertain")
        run_jobs(self.ledger,self.config,adapter,self.now)
        self.assertEqual(self.row()["status"],"uncertain")
        run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(hours=2))
        self.assertEqual(adapter.calls,["publish","reconcile"])

    def test_crash_intent_reconciles(self):
        self.ledger.update(self.key,"dispatching")
        adapter = Fake()
        run_jobs(self.ledger,self.config,adapter,self.now)
        self.assertEqual(adapter.calls,["reconcile"])

    def test_pause_prevents_network(self):
        adapter = Fake()
        run_jobs(self.ledger,self.config,adapter,self.now,pause=lambda:True)
        self.assertEqual(adapter.calls,[])

    def test_duplicate_slot_and_episode(self):
        self.ledger.enqueue("x","x-1",self.now.isoformat(),self.payload)
        self.ledger.enqueue("x","x-1",(self.now+dt.timedelta(days=1)).isoformat(),self.payload)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM jobs").fetchone()[0],1)

    def test_missed_day_not_backfilled(self):
        adapter = Fake()
        run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(days=1))
        self.assertEqual(self.row()["status"],"expired")
        self.assertEqual(adapter.calls,[])

    def test_rate_limit_retry_after_and_bounded_attempts(self):
        adapter = Fake(error=PublishError("rate_limit",3600))
        for n in range(4):
            run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(hours=n))
        self.assertLessEqual(len(adapter.calls),3)
        self.assertNotEqual(self.row()["status"],"confirmed")

    def test_authorization_blocks(self):
        run_jobs(self.ledger,self.config,Fake(error=PublishError("authorization")),self.now)
        self.assertEqual(self.row()["status"],"blocked")

    def test_free_plan_cannot_enable_four(self):
        for p in ("instagram","youtube","threads"):
            self.config["channels"][p].update(enabled=True,route="buffer")
        with self.assertRaises(ValueError): validate(self.config)

    def test_tiktok_requires_verified_buffer_account(self):
        self.config["channels"]["x"]["enabled"] = False
        self.config["channels"]["tiktok"].update(enabled=True,route="buffer")
        with self.assertRaises(ValueError): validate(self.config)
        self.config["channels"]["tiktok"].update(accountId="123",identityVerified=True,publishingVerified=True)
        validate(self.config)

    def test_instagram_direct_route_and_buffer_route_are_both_supported(self):
        self.config["channels"]["instagram"].update(enabled=True,route="instagram",accountId="17841400000000001",
            identityVerified=True,publishingVerified=True)
        validate(self.config)
        self.config["channels"]["instagram"]["route"] = "buffer"
        self.config["channels"]["instagram"]["accountId"] = "buffer-channel"
        validate(self.config)

    def test_exact_approval_scope(self):
        self.config["approval"]={"scopeHash":fingerprint(self.config),"approvedAt":"2026-10-05","deploymentApproved":True,"zeroSpendVerified":True,"monitoringVerified":True,"mediaDeliveryVerified":True}
        validate(self.config,live=True)
        self.config["schedule"]["time"]="09:00"
        with self.assertRaises(ValueError): validate(self.config,live=True)

    def test_monitoring_and_media_required_before_launch(self):
        self.config['approval']={'scopeHash':fingerprint(self.config),'approvedAt':'2026-10-05','deploymentApproved':True,'zeroSpendVerified':True}
        with self.assertRaises(ValueError): validate(self.config,live=True)

    def test_dst_local_eight_am(self):
        self.config["queueDays"]=2
        winter = list(slots(self.config,dt.datetime(2026,11,1,5,tzinfo=UTC)))
        self.assertTrue(winter[0].startswith("2026-11-01T13:00"))
        summer = list(slots(self.config,self.now))
        self.assertTrue(summer[0].startswith("2026-10-05T12:00"))

    def test_lock_competing_process(self):
        with lock(Path(self.tmp.name)/"lock"):
            with self.assertRaises(BlockingIOError):
                with lock(Path(self.tmp.name)/"lock"): pass

    def test_budget_stops(self):
        for _ in range(80): self.ledger.consume_call(self.now.timestamp())
        with self.assertRaises(RuntimeError): self.ledger.consume_call(self.now.timestamp())

    def test_out_of_order_holds_next(self):
        self.ledger.update(self.key,"uncertain",retry_at=self.now.timestamp()+9999)
        p={**self.payload,"episode":{"id":"ep02"}}
        self.ledger.enqueue("x","x-1",(self.now+dt.timedelta(minutes=1)).isoformat(),p)
        adapter=Fake()
        run_jobs(self.ledger,self.config,adapter,self.now+dt.timedelta(minutes=2))
        self.assertEqual(adapter.calls,[])

    def test_reconciliation_requires_network_permalink(self):
        def transport(q,v,t):
            return {"post":{"id":"remote-1","status":"sent","sentAt":self.now.isoformat(),"externalLink":None,
                            "schedulingType":"automatic","channelId":"x-1","text":"test"}}
        adapter=BufferAdapter(self.ledger,self.config,transport,lambda:"not-a-secret-test")
        job=dict(self.row());job["remote_id"]="remote-1"
        self.assertEqual(adapter.reconcile(job,self.payload),{"status":"uncertain"})


if __name__ == "__main__": unittest.main()
