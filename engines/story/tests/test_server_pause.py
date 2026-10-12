"""
Review B2, partial fix in the old dashboard ($0): after Pause the worker stops consuming
the pipeline generator (no further steps run), a new /run is refused while the old
thread is still finishing its step, and the old thread never drops the new run's queue.
"""

import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import smoke_support as sx  # noqa: F401  (must come before any src import)

from fastapi import HTTPException

import src.server as server
from src.pipeline import PipelineStatus


class PauseStopsWorkTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: self.loop.call_soon_threadsafe(self.loop.stop))
        self.project = SimpleNamespace(id="p1", name="P", mode="animation-series", params={}, step_data={},
                                       status="running", error=None, current_step=None)
        for name, value in (("get_project", lambda pid: self.project), ("update_project", lambda p: None),
                            ("get_project_dir", lambda pid: sx.TMP_ROOT / "p1")):
            patcher = mock.patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(server._active_runs.clear)
        self.addCleanup(server._active_threads.clear)

    def test_worker_stops_consuming_after_pause(self):
        produced = []
        queue = asyncio.Queue()
        newer_queue = asyncio.Queue()
        server._active_runs["p1"] = queue

        def fake_pipeline(**kwargs):
            produced.append("writer")
            yield PipelineStatus(step=1, message="writer done")
            server._active_runs.pop("p1")             # Pause pressed during the next step
            server._active_runs["p1"] = newer_queue   # ...and a new run registered
            produced.append("screenwriter")
            yield PipelineStatus(step=2, message="screenwriter done")
            produced.append("casting")                # must never run
            yield PipelineStatus(step=3, message="casting done")

        with mock.patch("src.animation_pipeline.run_animation_pipeline", fake_pipeline):
            server._execute_pipeline(self.project, queue, self.loop)
        self.assertEqual(produced, ["writer", "screenwriter"])
        self.assertIs(server._active_runs.get("p1"), newer_queue)

    def test_run_refused_while_previous_thread_alive(self):
        release = threading.Event()
        old = threading.Thread(target=release.wait, daemon=True)
        old.start()
        self.addCleanup(release.set)
        server._active_threads["p1"] = old
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(server.api_run_pipeline("p1"))
        self.assertEqual(cm.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
