"""
$0 end-to-end smoke tests for both story engine routes, through the headless CLI
(`python -m src.cli --headless ...`). Every paid or networked call is stubbed;
smoke_support blocks sockets so a missed stub fails loudly.

Run from engines/story:  .venv/bin/python -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import smoke_support as sx  # noqa: F401  (must come before any src import)

from tenacity import wait_none

from src import cli
from src.config import Config
import ffmpeg

from src.render_json import TMDB_NOTICE, has_audio_stream, mp4_faststart, probe_video

FIXTURE_PROJECT = sx.ENGINE_DIR / "output" / "projects" / "Galactic_Garage"


def _config_dirs(root: Path) -> dict:
    out = root / "output"
    return {
        "OUTPUT_DIR": out,
        "TEMP_DIR": out / "temp",
        "FINAL_DIR": out / "final",
        "LOGS_DIR": out / "pipeline_logs",
        "PROJECTS_DIR": out / "projects",
        "SETTINGS_FILE": out / "settings.json",
        "ASSETS_DIR": root / "assets",
        "GEMINI_API_KEY": sx.DUMMY_KEY,
        "GROQ_API_KEY": sx.DUMMY_KEY,
        "TMDB_API_KEY": sx.DUMMY_KEY,
        "PEXELS_API_KEY": sx.DUMMY_KEY,
        "FAL_KEY": sx.DUMMY_KEY,
    }


def _no_genai_calls(stack: contextlib.ExitStack) -> None:
    """Belt and braces: any google-genai content/video call fails the test."""
    from google.genai import models as genai_models

    def boom(*args, **kwargs):
        raise AssertionError("google-genai call in a $0 smoke test")
    stack.enter_context(mock.patch.object(genai_models.Models, "generate_content", boom))
    stack.enter_context(mock.patch.object(genai_models.Models, "generate_videos", boom))


def _run_cli(argv) -> tuple:
    """Run src.cli.main(argv), capturing its stdout (logs included)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


@unittest.skipUnless(sx.FFMPEG_SOURCE, "no working ffmpeg (system or Remotion-bundled)")
class HeadlessCliArgsTest(unittest.TestCase):
    def test_headless_requires_route_and_title(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["--headless"])
        self.assertEqual(cm.exception.code, 2)

    def test_series_requires_brief(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(["--headless", "--route", "series", "--title", "X"])


@unittest.skipUnless(sx.FFMPEG_SOURCE, "no working ffmpeg (system or Remotion-bundled)")
class RecapSmokeTest(unittest.TestCase):
    """recap: TMDB/Wikipedia, LLM, TTS, Pexels and Whisper stubbed; ffmpeg runs for real."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="recap-"))
        # The old untracked music folder must never be used (licence unknown)
        sx.make_tone_wav(cls.root / "assets" / "music" / "smoke_bed.wav", seconds=3.0)
        catalog = sx.make_music_catalog(cls.root)

        from src.moviedbapi import MovieDBClient
        from src.narrative import StoryGenerator
        from src.renderer import VideoRenderer
        import src.pipeline as pipeline

        cls.stack = contextlib.ExitStack()
        s = cls.stack
        for name, value in _config_dirs(cls.root).items():
            s.enter_context(mock.patch.object(Config, name, value))
        s.enter_context(mock.patch.object(Config, "MUSIC_CATALOG", catalog))
        s.enter_context(mock.patch.object(Config, "RECAP_MUSIC", "catalog"))
        s.enter_context(mock.patch.object(MovieDBClient, "search_movie", sx.fake_search_movie))
        s.enter_context(mock.patch.object(MovieDBClient, "get_movie_details", sx.fake_get_movie_details))
        s.enter_context(mock.patch.object(MovieDBClient, "get_tmdb_metadata", sx.fake_get_tmdb_metadata))
        s.enter_context(mock.patch.object(MovieDBClient, "download_poster", sx.fake_download_poster))
        s.enter_context(mock.patch.object(StoryGenerator, "generate_script", sx.fake_generate_script))
        s.enter_context(mock.patch.object(pipeline, "generate_audio", sx.fake_generate_audio))
        s.enter_context(mock.patch.object(pipeline, "download_video", sx.fake_download_video))
        s.enter_context(mock.patch.object(pipeline, "whisper_transcribe", sx.fake_whisper_transcribe))
        s.enter_context(mock.patch.object(pipeline, "_preload_whisper_model", lambda: None))
        if not sx.FULL_RENDERER:
            # Test-only: this ffmpeg cannot run the renderer's filter graph (see RealRendererTest)
            s.enter_context(mock.patch.object(VideoRenderer, "render_from_scenes", sx.standin_render_from_scenes))
        _no_genai_calls(s)

        cls.code, cls.log = _run_cli(["--headless", "--route", "recap", "--title", sx.SMOKE_TITLE])
        safe = Config.safe_title(sx.SMOKE_TITLE)
        cls.folder = cls.root / "output" / "final" / safe
        cls.video = cls.folder / f"{safe}.mp4"
        cls.render_json = cls.folder / "render.json"

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def test_run_succeeds_offline(self):
        self.assertEqual(self.code, 0, self.log[-3000:])
        self.assertEqual(sx.NETWORK_ATTEMPTS, [])
        self.assertTrue(self.video.exists())

    def test_video_meets_the_contract_media_rules(self):
        v = probe_video(self.video)
        self.assertEqual((v["width"], v["height"]), (1080, 1920))
        self.assertEqual(v["videoCodec"], "h264")
        self.assertEqual(v["audioCodec"], "aac")
        self.assertGreater(v["durationSeconds"], 3.0)
        audio = next(st for st in ffmpeg.probe(str(self.video))["streams"] if st["codec_type"] == "audio")
        self.assertEqual((int(audio["sample_rate"]), int(audio["channels"])), (48000, 2))
        self.assertTrue(mp4_faststart(self.video))
        self.assertLessEqual(self.video.stat().st_size, 24_000_000)

    def test_render_json_passes_checker(self):
        if not sx.node_available():
            self.skipTest("node or tools/render-json.mjs not available")
        result = sx.check_render_json(self.render_json)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_render_json_content(self):
        doc = json.loads(self.render_json.read_text())
        self.assertEqual((doc["engine"], doc["route"], doc["kitVersion"], doc["project"]),
                         ("story", "recap", "story-1", "originals"))
        self.assertEqual(doc["episodeId"], "originals-recap-smoke-test-film-2001")
        self.assertEqual(doc["video"]["file"], self.video.name)
        self.assertEqual(doc["cover"]["file"], "cover.jpg")
        self.assertTrue((self.folder / "cover.jpg").exists())
        self.assertTrue((self.folder / doc["job"]["script"]).exists())
        # Priced from the recap's spend ledger: the script call and every narration call
        ledger = json.loads((self.root / "output" / "temp" / Config.safe_title(sx.SMOKE_TITLE) / "spend_ledger.json").read_text())
        kinds = {e["kind"] for e in ledger["entries"]}
        self.assertEqual(kinds, {"llm", "tts"})
        self.assertGreater(doc["costUsd"], 0)
        self.assertAlmostEqual(doc["costUsd"], round(sum(e["costUsd"] for e in ledger["entries"]), 4))
        self.assertTrue(doc["costEstimated"])
        self.assertEqual(set(doc["job"]["costByKind"]), {"llm", "tts"})
        self.assertEqual(
            {(m["role"], m["id"]) for m in doc["models"]},
            {("llm", Config.GEMINI_MODEL_NAME), ("tts", Config.TTS_MODEL), ("asr", "openai-whisper-base")},
        )
        by_license = {}
        for c in doc["credits"]:
            by_license.setdefault(c["license"], []).append(c)
        self.assertNotIn("unknown", by_license)  # contract v2 refuses unknown licences
        pexels = by_license["Pexels"]
        self.assertEqual(len(pexels), 3)  # scene 2 took generic Pexels footage, still credited
        self.assertTrue(all(c["sourceUrl"].startswith("https://www.pexels.com/") and c["creator"] for c in pexels))
        music = by_license["CC0-1.0"]
        self.assertEqual([(c["kind"], c["creator"], c["sourceUrl"]) for c in music],
                         [("music", "Test Artist", "https://opengameart.org/content/smoke-bed")])
        self.assertEqual(doc["job"]["music"], "test-smoke-bed")
        if doc["job"]["subtitlesBurned"]:
            self.assertEqual(by_license["OFL-1.1"][0]["kind"], "font")
        wiki = by_license["Wikipedia-CC-BY-SA"][0]
        self.assertEqual(wiki["sourceUrl"], "https://en.wikipedia.org/wiki/Smoke_Test_Film")
        posters = [c for c in by_license["TMDB"] if c["kind"] == "poster"]
        self.assertEqual(len(posters), 1)
        self.assertIn(TMDB_NOTICE, posters[0]["attribution"])
        self.assertEqual(doc["disclosure"]["aiKinds"], ["script", "voice"])
        self.assertFalse(doc["disclosure"]["realisticSynthetic"])

    def test_z_stages_packages_and_validates_as_contract_v2(self):
        """The recap becomes a contract v2 Originals batch the validator accepts (media checks included)."""
        if not sx.node_available():
            self.skipTest("node not available")
        result = sx.stage_package_validate(self.folder, Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="lib-")), "2026-10-o901", 901)
        self.assertEqual(result["stage"].returncode, 0, result["stage"].stdout + result["stage"].stderr)
        self.assertIn('"episodeId":"originals-movie-recap-901"', result["stage"].stdout)
        self.assertEqual(result["package"].returncode, 0, result["package"].stdout + result["package"].stderr)
        batch = result["batch"]
        self.assertEqual((batch["schemaVersion"], batch["project"]), (2, "originals"))
        ep = batch["episodes"][0]
        self.assertEqual(ep["episodeId"], "originals-movie-recap-901")
        self.assertEqual(ep["contentId"], "originals:movie-recap:smoke-test-film-2001")
        self.assertGreater(ep["render"]["costUsd"], 0)
        self.assertIsNone(ep["publication"]["captions"]["x"])  # TMDB + Wikipedia attribution do not fit X
        self.assertIn(TMDB_NOTICE, ep["publication"]["captions"]["instagram"])
        # Staging again is a no-op
        again = sx.run_node("tools/stage-story.mjs", "--batch=2026-10-o901", f"--dir={result['batchDir']}", str(self.folder))
        self.assertIn('"staged":false', again.stdout)


@unittest.skipUnless(sx.FFMPEG_SOURCE, "no working ffmpeg (system or Remotion-bundled)")
@unittest.skipUnless(sx.FULL_RENDERER, f"recap renderer filter graph not exercised: {sx.describe_ffmpeg()}")
class RealRendererTest(unittest.TestCase):
    """VideoRenderer.render_from_scenes for real, when the local ffmpeg has its filters."""

    def test_render_from_scenes(self):
        from src.pipeline import SceneAssets, _create_silent_audio
        from src.renderer import VideoRenderer
        from src.subtitles import generate_karaoke_subtitles
        root = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="renderer-"))
        assets = []
        for i in range(2):
            audio = _create_silent_audio(str(root / f"a{i}.wav"), 1.0)
            assets.append(SceneAssets(i, "x", ["q"], audio, 1.0, sx.make_clip(root / f"v{i}.mp4", 1.0), {}))
        poster = sx.make_image(root / "poster.jpg")
        assets.append(SceneAssets(2, "end", ["poster"], _create_silent_audio(str(root / "a2.wav"), 1.0), 1.0, "", {},
                                  poster_path=poster, is_ending_scene=True))
        subs = str(root / "subs.ass")
        generate_karaoke_subtitles(sx.fake_whisper_transcribe(assets[0].audio_path), subs, words_per_line=4)
        out = root / "out.mp4"
        VideoRenderer().render_from_scenes(assets, str(out), subtitle_path=subs,
                                           background_music_path=sx.make_tone_wav(root / "m.wav", 2.0))
        v = probe_video(out)
        self.assertEqual((v["width"], v["height"], v["audioCodec"]), (1080, 1920, "aac"))


class FakeVideoProviders:
    """
    Scripted stand-ins for UnifiedVideoClient's network primitives (one request each).

    Plan for Galactic_Garage episode 1 (active model wan-2.5, tier cheapest):
      scene 1  wan-2.5 ok
      scene 2  wan-2.5 billed then fails while waiting -> veo-3.1-lite rejects (400, not billed)
               -> kling-2.5-turbo-pro ok (fallback: the tier cheapest first)
      scene 3  kling submit refused once (never started) -> retried submit -> ok
      scene 4  kling download reset once -> download retried, no new submit -> ok
      scene 5  kling and wan-2.5 reject the request (not billed) -> veo-3.1-lite ok, WITH audio
    The fal models here have no audio, Veo clips have one: the B3 mix the editor must keep.
    """

    def __init__(self, prompts_to_scene: dict):
        self.prompts = prompts_to_scene
        self.submits = []        # (model_id, scene)
        self.waits = []
        self.downloads = []
        self.refused_once = False
        self.reset_once = False
        self.jobs = {}

    def _scene(self, prompt: str) -> int:
        for known, scene in self.prompts.items():
            if prompt.startswith(known[:120]):
                return scene
        raise AssertionError("unknown prompt")

    # fal.ai
    def fal_upload(self, client, path):
        return f"https://fal.invalid/uploads/{Path(path).name}"

    def fal_submit(self, client, endpoint, arguments):
        from src.video_client import VideoGenerationError  # noqa: F401
        model, scene = client.model_id, self._scene(arguments["prompt"])
        if model == "kling-2.5-turbo-pro" and scene == 3 and not self.refused_once:
            self.refused_once = True
            raise ConnectionRefusedError("refused (fake)")
        if scene == 5 and model in ("kling-2.5-turbo-pro", "wan-2.5"):
            raise RuntimeError("422 request rejected (fake)")
        self.submits.append((model, scene))
        request_id = f"req-{len(self.submits)}"
        self.jobs[request_id] = (model, scene)
        return request_id

    def fal_wait(self, client, endpoint, request_id):
        from src.video_client import VideoGenerationError
        model, scene = self.jobs[request_id]
        self.waits.append((model, scene))
        if model == "wan-2.5" and scene == 2:
            raise VideoGenerationError("generation failed (fake)")
        return {"video": {"url": f"https://fal.invalid/{request_id}.mp4"}}

    def fal_download(self, client, url, output_path):
        scene = int(Path(output_path).stem.split("_")[1])
        self.downloads.append((client.model_id, scene))
        if scene == 4 and not self.reset_once:
            self.reset_once = True
            raise ConnectionResetError("reset (fake)")
        sx.make_clip(output_path, seconds=1.5, audio=False)

    # Gemini API (Veo)
    def gemini_submit(self, client, kwargs):
        scene = self._scene(kwargs["prompt"])
        if scene == 2:
            error = RuntimeError("400 invalid argument (fake, not billed)")
            error.code = 400
            raise error
        self.submits.append((client.model_id, scene))
        raw = mock.Mock(video_bytes=None, uri="https://generativelanguage.invalid/v.mp4")
        video = mock.Mock(video=raw)
        return mock.Mock(done=True, error=None, response=mock.Mock(generated_videos=[video]))

    def gemini_wait(self, client, operation, on_poll=None):
        return operation

    def gemini_download(self, client, raw, out):
        sx.make_clip(out, seconds=1.5, audio=True)

    def patches(self, stack: contextlib.ExitStack) -> None:
        from src.video_client import UnifiedVideoClient
        fake = self
        for name in ("fal_upload", "fal_submit", "fal_wait", "fal_download",
                     "gemini_submit", "gemini_wait", "gemini_download"):
            method = getattr(fake, name)
            stack.enter_context(mock.patch.object(
                UnifiedVideoClient, f"_{name}",
                lambda client, *a, _m=method, **k: _m(client, *a, **k),
            ))


@unittest.skipUnless(sx.FFMPEG_SOURCE, "no working ffmpeg (system or Remotion-bundled)")
@unittest.skipUnless(FIXTURE_PROJECT.exists(),
                     f"fixture project {FIXTURE_PROJECT.relative_to(sx.ENGINE_DIR)} is absent "
                     "(local, gitignored data): series smoke test skipped")
class SeriesSmokeTest(unittest.TestCase):
    """series: a copy of Galactic_Garage with episode 1's clips and final reset."""

    @classmethod
    def _copy_fixture(cls, dst: Path) -> None:
        def ignore(directory, names):
            d = Path(directory)
            if d.name == "clips" and d.parent.name == "episode_1":
                return set(names)
            if d.name == "episode_1":
                return {"final.mp4", "render.json", "cover.jpg"} & set(names)
            if d == FIXTURE_PROJECT:
                return {"spend_ledger.json"} & set(names)
            return set()
        shutil.copytree(FIXTURE_PROJECT, dst, ignore=ignore)
        state_file = dst / "pipeline_state.json"
        state = json.loads(state_file.read_text())
        for step in ("scene_generator", "editor"):
            st = state["episodes"]["1"]["steps"][step]
            st.update(completed=False, completed_at=None, error=None, artifact_paths=[])
        state_file.write_text(json.dumps(state, indent=2))

    @classmethod
    def setUpClass(cls):
        from src.steps import director, scene_generator, set_designer
        import src.video_client as video_client

        cls.root = Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="series-"))
        cls.project = cls.root / "projects" / "Galactic_Garage"
        cls._copy_fixture(cls.project)
        cls.episode_dir = cls.project / "episodes" / "episode_1"
        shots = director.load_director_shots(cls.episode_dir)
        cls.fake = FakeVideoProviders({s.veo_prompt: s.scene_id for s in shots.shots})

        cls.stack = contextlib.ExitStack()
        s = cls.stack
        for name, value in _config_dirs(cls.root).items():
            s.enter_context(mock.patch.object(Config, name, value))
        s.enter_context(mock.patch.object(Config, "ACTIVE_VIDEO_MODEL", "wan-2.5"))
        s.enter_context(mock.patch.object(Config, "ACTIVE_VIDEO_TIER", "cheapest"))
        s.enter_context(mock.patch.object(Config, "VIDEO_MAX_BUDGET", 10.0))
        s.enter_context(mock.patch.object(Config, "VIDEO_AUTO_DOWNGRADE", True))
        s.enter_context(mock.patch.object(scene_generator, "_RATE_LIMIT_FAL", 0))
        s.enter_context(mock.patch.object(video_client, "_RETRY_WAIT", wait_none()))

        def no_image_generation(*args, **kwargs):
            raise AssertionError("set_designer image generation in a $0 smoke test")
        s.enter_context(mock.patch.object(set_designer, "_generate_scene_start", no_image_generation))
        _no_genai_calls(s)
        cls.fake.patches(s)

        cls.argv = ["--headless", "--route", "series", "--title", "Galactic Garage",
                    "--brief", "Alien mechanics fix spaceships", "--episodes", "1",
                    "--project-dir", str(cls.project)]
        cls.code, cls.log = _run_cli(cls.argv)
        cls.render_json = cls.episode_dir / "render.json"

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def _ledger(self):
        return json.loads((self.project / "spend_ledger.json").read_text())["entries"]

    def test_1_run_succeeds_offline(self):
        self.assertEqual(self.code, 0, self.log[-3000:])
        self.assertEqual(sx.NETWORK_ATTEMPTS, [])
        self.assertTrue((self.episode_dir / "final.mp4").exists())
        self.assertEqual(sorted(p.name for p in (self.episode_dir / "clips").glob("scene_*.mp4")),
                         [f"scene_{i}.mp4" for i in range(1, 6)])

    def test_2_retries_never_resubmit(self):
        # B6: scene 3's refused submit was retried; scene 4's download was retried without a new submit
        self.assertTrue(self.fake.refused_once and self.fake.reset_once)
        self.assertEqual(self.fake.submits, [
            ("wan-2.5", 1), ("wan-2.5", 2), ("kling-2.5-turbo-pro", 2),
            ("kling-2.5-turbo-pro", 3), ("kling-2.5-turbo-pro", 4), ("veo-3.1-lite", 5),
        ])
        self.assertEqual(self.fake.downloads.count(("kling-2.5-turbo-pro", 4)), 2)

    def test_3_ledger_records_actual_models_and_billed_failures(self):
        rows = [(e["sceneId"], e["modelId"], e["status"], e["costUsd"]) for e in self._ledger()]
        self.assertEqual(rows, [
            (1, "wan-2.5", "ok", 0.25),
            (2, "wan-2.5", "failed", 0.25),           # billed although it produced nothing
            (2, "kling-2.5-turbo-pro", "ok", 0.35),   # fallback: current model first, then cheapest first
            (3, "kling-2.5-turbo-pro", "ok", 0.35),   # each shot at the model's clip length (5 s)
            (4, "kling-2.5-turbo-pro", "ok", 0.35),
            (5, "veo-3.1-lite", "ok", 0.4),           # Veo always renders 8 s
        ])

    def test_4_render_json_passes_checker(self):
        if not sx.node_available():
            self.skipTest("node or tools/render-json.mjs not available")
        result = sx.check_render_json(self.render_json)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_5_render_json_content(self):
        doc = json.loads(self.render_json.read_text())
        self.assertEqual((doc["engine"], doc["route"], doc["episodeId"]),
                         ("story", "series", "originals-series-galactic-garage-ep1"))
        self.assertEqual(doc["video"]["file"], "final.mp4")
        self.assertTrue((self.episode_dir / "cover.jpg").exists())
        self.assertAlmostEqual(doc["costUsd"], 1.95, places=4)
        self.assertTrue(doc["costEstimated"])
        self.assertEqual([m["id"] for m in doc["models"] if m["role"] == "video"],
                         ["wan-2.5", "kling-2.5-turbo-pro", "veo-3.1-lite"])
        self.assertEqual({m["role"] for m in doc["models"]}, {"llm", "image", "video"})
        self.assertEqual([c["modelId"] for c in doc["job"]["clips"]],
                         ["wan-2.5", "kling-2.5-turbo-pro", "kling-2.5-turbo-pro", "kling-2.5-turbo-pro", "veo-3.1-lite"])
        self.assertEqual([c["hasAudio"] for c in doc["job"]["clips"]], [False] * 4 + [True])
        self.assertTrue(all(c["license"] == "generated" for c in doc["credits"]))
        self.assertFalse(doc["disclosure"]["realisticSynthetic"])  # 3D Pixar-style cartoon
        self.assertEqual(doc["disclosure"]["aiKinds"], ["script", "image", "video", "voice"])  # clip 5's native audio
        self.assertEqual(doc["job"]["audio"], {"policy": "native", "clipsWithNativeAudio": 1, "clips": 5})

    def test_6_resume_spends_nothing(self):
        submits_before = list(self.fake.submits)
        ledger_before = self._ledger()
        code, log = _run_cli(self.argv)
        self.assertEqual(code, 0, log[-3000:])
        self.assertEqual(self.fake.submits, submits_before)
        self.assertEqual(self._ledger(), ledger_before)
        self.assertEqual(sx.NETWORK_ATTEMPTS, [])

    def test_7_b3_mixed_clips_keep_audio_and_size(self):
        """Review B3: clips 1-4 are silent 360x640, clip 5 (Veo) has audio: the final keeps it, at 1080x1920."""
        final = self.episode_dir / "final.mp4"
        self.assertTrue(has_audio_stream(final))
        v = probe_video(final)
        self.assertEqual((v["width"], v["height"], v["fps"], v["audioCodec"]), (1080, 1920, "30/1", "aac"))
        audio = next(st for st in ffmpeg.probe(str(final))["streams"] if st["codec_type"] == "audio")
        self.assertEqual((int(audio["sample_rate"]), int(audio["channels"])), (48000, 2))
        self.assertTrue(mp4_faststart(final))
        # 5 clips of 1.5 s, each trimmed by 0.2 s
        self.assertAlmostEqual(v["durationSeconds"], 5 * 1.3, delta=0.3)

    def test_8_stages_packages_and_validates_as_contract_v2(self):
        if not sx.node_available():
            self.skipTest("node not available")
        result = sx.stage_package_validate(self.episode_dir, Path(tempfile.mkdtemp(dir=sx.TMP_ROOT, prefix="lib-")), "2026-10-o902", 901)
        self.assertEqual(result["stage"].returncode, 0, result["stage"].stdout + result["stage"].stderr)
        self.assertEqual(result["package"].returncode, 0, result["package"].stdout + result["package"].stderr)
        ep = result["batch"]["episodes"][0]
        self.assertEqual(ep["episodeId"], "originals-animated-short-901")
        self.assertEqual(ep["contentId"], "originals:animated-short:galactic-garage-ep1")
        self.assertEqual(ep["projectData"]["series"], {"seriesId": "galactic-garage", "episode": 1})
        self.assertTrue(ep["disclosure"]["aiGenerated"])
        # No attribution licences in a series: every platform posts, X included
        self.assertTrue(all(ep["publication"]["captions"].values()))

if __name__ == "__main__":
    unittest.main()
