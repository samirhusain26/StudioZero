"""Worker agent (src/agent.py) at $0: auth, refusal without a confirmed estimate, budget refusal, cancellation,
the recap review gate (B1), scene decisions, file access and settings. The pipelines are fakes; no network."""
import smoke_support  # noqa: F401  (isolation first: dummy keys, no network, temp settings)

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.agent import Runner, create_app
from src.budget_guard import SpendLedger
from src.config import Config
from src.pipeline import PipelineStatus

TOKEN = "t" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SCRIPT = {
    "title": "Arrival", "genre": "Sci-Fi", "overall_mood": "tense", "lang_code": "en", "selected_voice_id": "Kore",
    "selected_music_file": "sci-fi.mp3", "bpm": 90,
    "scenes": [{"scene_index": i, "narration": f"Scene {i}: ships arrive.", "visual_queries": ["spaceship", "fog", "night sky"],
                "visual_style_modifiers": ["cinematic lighting"], "mood": "tense"} for i in range(6)],
}


class FakeRunner(Runner):
    """Paid steps are counted; each waits for `gate` so tests can cancel mid-run."""
    def __init__(self):
        self.paid = 0
        self.gate = threading.Event()
        self.started = threading.Event()
        self.approved_scripts = []

    def recap(self, project, cancel, approved_script):
        self.approved_scripts.append(approved_script)
        yield PipelineStatus(step=1, message="Fetching movie data...")
        if not approved_script:
            self.paid += 1  # the script LLM call
            yield PipelineStatus(step=1, message="Script generated", data={"script": SCRIPT}, review_gate=True)
            raise AssertionError("must not continue past the review gate")
        yield PipelineStatus(step=1, message="Using the approved script")
        self.paid += 1  # TTS
        yield PipelineStatus(step=2, message="Processing scenes...")
        return ([], None, "final.mp4")

    def series(self, project, cancel, progress):
        for scene in range(1, 7):
            self.started.set()
            self.gate.wait(5)
            if cancel.is_set():
                yield PipelineStatus(step=7, message="[ep1/scene_generator] Cancelled; resume to continue", is_error=True)
                return None
            self.paid += 1
            progress({"type": "cost_update", "message": f"scene {scene}", "data": {"scene": scene}})
            yield PipelineStatus(step=7, message=f"[ep1/scene_generator] scene {scene} done")
        return "done"

    def random_idea(self):
        self.paid += 1
        return {"name": "Idea", "brief": "Brief"}


def wait_until(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class AgentTestCase(unittest.TestCase):
    allow_paid = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = {k: getattr(Config, k) for k in ("OUTPUT_DIR", "PROJECTS_DIR", "FINAL_DIR", "TEMP_DIR", "VIDEO_MAX_BUDGET", "ACTIVE_VIDEO_MODEL")}
        Config.OUTPUT_DIR = root / "output"
        Config.PROJECTS_DIR = Config.OUTPUT_DIR / "projects"
        Config.FINAL_DIR = Config.OUTPUT_DIR / "final"
        Config.TEMP_DIR = Config.OUTPUT_DIR / "temp"
        Config.VIDEO_MAX_BUDGET = 10.0
        Config.ACTIVE_VIDEO_MODEL = "veo-3.1-fast"
        studio = root / "studio"
        (studio / "projects/originals").mkdir(parents=True)
        (studio / "projects/originals/project.json").write_text(json.dumps({"budget": {"monthlyUsd": 0, "perRunApproval": True}}))
        self.runner = FakeRunner()
        self.app = create_app(token=TOKEN, runner=self.runner, allow_paid=self.allow_paid, studio_root=studio)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.runner.gate.set()
        for k, v in self.saved.items():
            setattr(Config, k, v)
        self.tmp.cleanup()

    def call(self, method, path, **kw):
        return self.client.request(method, path, headers={**AUTH, **kw.pop("headers", {})}, **kw)

    def series(self, name="Garage", episodes=1):
        r = self.call("POST", "/studio/projects", json={"route": "series", "name": name, "brief": "A robot fixes ships.", "episodes": episodes})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def confirmed_run(self, pid):
        est = self.call("GET", f"/studio/projects/{pid}/estimate").json()
        return self.call("POST", f"/studio/projects/{pid}/run", json={"confirm": {"token": est["token"], "estimateUsd": est["estimateUsd"]}})


class AuthTests(AgentTestCase):
    def test_every_route_needs_the_token(self):
        pid = self.series()
        for method, path in (("GET", "/studio/health"), ("GET", "/studio/projects"), ("GET", f"/studio/projects/{pid}"),
                             ("POST", f"/studio/projects/{pid}/run"), ("POST", f"/studio/projects/{pid}/cancel"),
                             ("GET", "/studio/settings"), ("PUT", "/studio/settings"), ("GET", "/studio/renders")):
            for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}):
                r = self.client.request(method, path, headers=headers, json={})
                self.assertEqual(r.status_code, 401, (method, path, headers))
                self.assertNotIn(TOKEN, r.text)
        self.assertEqual(self.call("GET", "/studio/health").json()["engine"], "story")

    def test_no_token_configured_locks_everything(self):
        client = TestClient(create_app(token=None, runner=self.runner, allow_paid=True))
        self.assertEqual(client.get("/studio/health", headers={"Authorization": "Bearer "}).status_code, 401)
        self.assertEqual(client.get("/studio/health").status_code, 401)

    def test_no_docs_or_openapi(self):
        for path in ("/docs", "/openapi.json", "/redoc"):
            self.assertEqual(self.call("GET", path).status_code, 404)

    def test_keys_are_reported_as_present_never_as_values(self):
        body = self.call("GET", "/studio/health").text + self.call("GET", "/studio/settings").text
        self.assertNotIn(smoke_support.DUMMY_KEY, body)
        self.assertEqual(self.call("GET", "/studio/health").json()["keys"]["gemini"], True)


class PaidRefusalTests(AgentTestCase):
    def test_run_refused_without_a_confirmed_matching_estimate(self):
        pid = self.series()
        self.assertEqual(self.call("POST", f"/studio/projects/{pid}/run", json={}).status_code, 428)
        est = self.call("GET", f"/studio/projects/{pid}/estimate").json()
        self.assertGreater(est["estimateUsd"], 0)
        self.assertEqual(est["lines"][0]["what"].split()[0], "6")
        for confirm in ({"token": "est-forged000000", "estimateUsd": est["estimateUsd"]}, {"token": est["token"], "estimateUsd": 0}):
            r = self.call("POST", f"/studio/projects/{pid}/run", json={"confirm": confirm})
            self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self.runner.paid, 0)

    def test_budget_refusal_counts_the_ledger(self):
        pid = self.series()
        ledger = SpendLedger(Config.PROJECTS_DIR / pid)
        ledger.record(episode=1, scene_id=1, model_id="veo-3.1-fast", duration_sec=8, cost_usd=9.5)
        r = self.confirmed_run(pid)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Over budget", r.json()["error"])
        self.assertEqual(self.runner.paid, 0)

    def test_random_idea_needs_its_own_confirmation(self):
        self.assertEqual(self.call("POST", "/studio/ideas/random", json={}).status_code, 428)
        r = self.call("POST", "/studio/ideas/random", json={"confirm": {"token": "idea-llm-call", "estimateUsd": 0}})
        self.assertEqual((r.status_code, self.runner.paid), (200, 1))


class PaidOffTests(AgentTestCase):
    allow_paid = False

    def test_paid_work_is_switched_off_by_default(self):
        pid = self.series()
        self.assertEqual(self.confirmed_run(pid).status_code, 403)
        self.assertEqual(self.call("POST", "/studio/ideas/random", json={"confirm": {"token": "idea-llm-call", "estimateUsd": 0}}).status_code, 403)
        self.assertFalse(self.call("GET", f"/studio/projects/{pid}/estimate").json()["paidRunsEnabled"])
        self.assertEqual(self.runner.paid, 0)


class RunTests(AgentTestCase):
    def test_cancel_stops_before_the_next_paid_scene(self):
        pid = self.series()
        self.assertEqual(self.confirmed_run(pid).status_code, 200)
        self.assertTrue(self.runner.started.wait(5))
        self.assertEqual(self.confirmed_run(pid).status_code, 409)  # one run at a time
        r = self.call("POST", f"/studio/projects/{pid}/cancel")
        self.assertTrue(r.json()["cancelling"])
        self.runner.gate.set()
        self.assertTrue(wait_until(lambda: self.call("GET", f"/studio/projects/{pid}").json()["status"] == "paused"))
        self.assertEqual(self.runner.paid, 0)
        events = self.call("GET", f"/studio/projects/{pid}/events?since=0").json()
        self.assertIn("Cancel requested: stopping before the next paid step", [e["message"] for e in events["events"]])
        self.assertFalse(events["running"])
        # A later confirmed run continues (the fake renders all six scenes when not cancelled).
        self.assertEqual(self.confirmed_run(pid).status_code, 200)
        self.assertTrue(wait_until(lambda: self.call("GET", f"/studio/projects/{pid}").json()["status"] == "completed"))
        self.assertEqual(self.runner.paid, 6)
        later = self.call("GET", f"/studio/projects/{pid}/events?since={events['last']}").json()["events"]
        self.assertTrue(all(e["seq"] > events["last"] for e in later))
        self.assertIn("scene 6", [e["message"] for e in later])

    def test_recap_review_gate_uses_the_approved_script(self):
        r = self.call("POST", "/studio/projects", json={"route": "recap", "name": "Arrival"})
        pid = r.json()["id"]
        est = self.call("GET", f"/studio/projects/{pid}/estimate").json()
        self.assertEqual(est["estimateUsd"], 0)
        self.assertIn("Gemini script (LLM)", est["unpriced"])
        self.assertEqual(self.confirmed_run(pid).status_code, 200)
        self.assertTrue(wait_until(lambda: self.call("GET", f"/studio/projects/{pid}").json()["status"] == "review"))
        self.assertEqual(self.confirmed_run(pid).status_code, 409)  # approve first
        edited = {**SCRIPT, "title": "Arrival (edited)"}
        self.assertEqual(self.call("PUT", f"/studio/projects/{pid}/script", json={"script": edited}).status_code, 200)
        self.assertEqual(self.call("PUT", f"/studio/projects/{pid}/script", json={"script": {"nope": 1}}).status_code, 422)
        self.assertEqual(self.call("POST", f"/studio/projects/{pid}/approve-script").status_code, 200)
        self.assertEqual(self.confirmed_run(pid).status_code, 200)
        self.assertTrue(wait_until(lambda: self.call("GET", f"/studio/projects/{pid}").json()["status"] == "completed"))
        self.assertEqual(self.runner.approved_scripts[0], None)
        self.assertEqual(self.runner.approved_scripts[1]["title"], "Arrival (edited)")
        self.assertEqual(self.runner.paid, 2)  # one script, one narration: never regenerated (B1)


class SceneAndFileTests(AgentTestCase):
    def failed(self, pid):
        from src.project_manager import get_project, update_project
        p = get_project(pid)
        p.status = "scene_failed"
        p.step_data["failed_scene"] = {"episode_number": 1, "scene_id": 3, "veo_prompt": "a ship", "error_detail": "provider said no"}
        update_project(p)

    def test_scene_decisions_write_markers_and_are_per_project(self):
        pid = self.series()
        self.failed(pid)
        self.assertEqual(self.call("GET", f"/studio/projects/{pid}").json()["failedScene"]["scene"], 3)
        self.assertEqual(self.call("POST", f"/studio/projects/{pid}/scene", json={"action": "edit"}).status_code, 422)
        r = self.call("POST", f"/studio/projects/{pid}/scene", json={"action": "edit", "prompt": "a calmer ship"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("estimate", r.json())
        clips = Config.PROJECTS_DIR / pid / "episodes/episode_1/clips"
        self.assertEqual((clips / "scene_3_override.txt").read_text(), "a calmer ship")
        self.assertEqual(self.runner.paid, 0)
        self.failed(pid)
        self.call("POST", f"/studio/projects/{pid}/scene", json={"action": "change_model", "modelId": "wan-2.5"})
        self.assertEqual(self.call("GET", f"/studio/projects/{pid}").json()["videoModel"], "wan-2.5")
        self.assertEqual(Config.ACTIVE_VIDEO_MODEL, "veo-3.1-fast")  # the global setting is untouched
        self.failed(pid)
        self.call("POST", f"/studio/projects/{pid}/scene", json={"action": "skip"})
        self.assertTrue((clips / "scene_3.skip").exists())
        self.assertEqual(self.call("POST", f"/studio/projects/{pid}/scene", json={"action": "retry"}).status_code, 409)

    def test_files_stay_inside_the_project(self):
        pid = self.series()
        base = Config.PROJECTS_DIR / pid
        (base / "story.json").write_text('{"ok": true}')
        (Config.OUTPUT_DIR / "secret.txt").write_text("no")
        self.assertEqual(self.call("GET", f"/studio/projects/{pid}/files/story.json").json(), {"ok": True})
        for path in ("../secret.txt", "..%2Fsecret.txt", "%2e%2e/secret.txt", "spend_ledger.json", "/etc/passwd"):
            self.assertEqual(self.call("GET", f"/studio/projects/{pid}/files/{path}").status_code, 404, path)
        for bad in ("../x", "a b", "a" * 200):
            self.assertEqual(self.call("GET", f"/studio/projects/{bad}").status_code, 404)
        self.assertEqual(self.call("GET", f"/studio/renders/..~secret/video.mp4").status_code, 404)

    def test_delete_needs_the_id(self):
        pid = self.series()
        self.assertEqual(self.call("DELETE", f"/studio/projects/{pid}", json={"confirm": "x"}).status_code, 422)
        self.assertEqual(self.call("DELETE", f"/studio/projects/{pid}", json={"confirm": pid}).status_code, 200)
        self.assertEqual(self.call("GET", f"/studio/projects/{pid}").status_code, 404)


class SettingsTests(AgentTestCase):
    def test_models_apply_without_restart_and_keys_are_never_written(self):
        r = self.call("PUT", "/studio/settings", json={"llm_model": "gemini-2.5-pro", "active_model": "wan-2.5", "max_budget": 3})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((Config.GEMINI_MODEL_NAME, Config.ACTIVE_VIDEO_MODEL, Config.VIDEO_MAX_BUDGET), ("gemini-2.5-pro", "wan-2.5", 3.0))
        saved = json.loads(Path(smoke_support.os.environ["STORY_SETTINGS_FILE"]).read_text())
        self.assertNotIn("credentials", saved)
        for body in ({"llm_model": "gpt-9"}, {"active_model": "nope"}, {"active_tier": "gold"}, {"max_budget": -1}, {"GEMINI_API_KEY": "x"}):
            r = self.call("PUT", "/studio/settings", json=body)
            if "GEMINI_API_KEY" in body:
                self.assertNotIn("GEMINI_API_KEY", json.loads(Path(smoke_support.os.environ["STORY_SETTINGS_FILE"]).read_text()).get("credentials", {}))
            else:
                self.assertEqual(r.status_code, 422, body)
        Path(smoke_support.os.environ["STORY_SETTINGS_FILE"]).unlink()
        Config.reload_settings()


if __name__ == "__main__":
    unittest.main()


class EngineCancelTests(unittest.TestCase):
    def test_real_series_pipeline_stops_before_any_step_and_scene(self):
        from src.animation_pipeline import run_animation_pipeline
        from src.steps import StepCancelled, StepContext
        with tempfile.TemporaryDirectory() as tmp:
            cancel = threading.Event()
            cancel.set()
            gen = run_animation_pipeline("Cancelled", "brief", num_episodes=1, project_dir=Path(tmp), cancel_event=cancel)
            statuses = list(gen)
            self.assertEqual([s.message for s in statuses], ["[writer] Cancelled; resume to continue"])
            state = json.loads((Path(tmp) / "pipeline_state.json").read_text())
            self.assertFalse(state["series_steps"]["writer"]["completed"])
            ctx = StepContext(project_dir=Path(tmp), gemini_client=None, cancel_event=cancel)
            with self.assertRaises(StepCancelled):
                ctx.check_cancelled()


class ArtifactPathTests(unittest.TestCase):
    def test_paths_from_before_a_move_map_into_the_project_and_nothing_escapes(self):
        from src.agent import _inside
        with tempfile.TemporaryDirectory() as tmp:
            base = (Path(tmp) / "projects" / "Show").resolve()
            (base / "characters").mkdir(parents=True)
            (base / "characters" / "a.png").write_bytes(b"x")
            self.assertEqual(_inside(base, "Show", "/old/place/output/projects/Show/characters/a.png"), base / "characters" / "a.png")
            self.assertEqual(_inside(base, "Show", "characters/a.png"), base / "characters" / "a.png")
            self.assertIsNone(_inside(base, "Show", "/etc/passwd"))
            self.assertIsNone(_inside(base, "Show", "/x/Show/../../etc/passwd"))
            self.assertIsNone(_inside(base, "Show", "../outside.png"))


class RedactionTests(unittest.TestCase):
    def test_state_view_has_no_paths_and_events_hide_local_folders(self):
        from src.agent import Job, _state_view
        home = str(Path.home())
        st = {"series_steps": {"writer": {"completed": True, "started_at": "a", "completed_at": "b", "error": None,
                                          "artifact_paths": [f"{home}/x/story.json"]}},
              "episodes": {"1": {"episode_number": 1, "steps": {"set_designer": {"completed": False, "error": f"boom in {home}/y",
                                                                                 "artifact_paths": []}}}}}
        view = _state_view(st)
        self.assertNotIn(home, json.dumps(view))
        self.assertEqual(view["seriesSteps"]["writer"]["artifacts"], 1)
        self.assertEqual(view["episodes"]["1"]["set_designer"]["error"], "boom in ~/y")
        j = Job("p")
        j.add("error", f"failed at {Path(__file__).resolve().parents[1]}/output/z.mp4")
        self.assertEqual(j.since(0)[0]["message"], "failed at …/output/z.mp4")
