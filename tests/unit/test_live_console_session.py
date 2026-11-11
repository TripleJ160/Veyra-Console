"""Offline runner contracts only: no application, card, GPU or gameplay is used."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("live_console_session", ROOT / "scripts/acceptance/live-console-session.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
ARTIFACTS = Path("E:/项目/Veyra/tmp/codex-live-5090-20261110/runner-unit")


def log(channel, **fields):
    return "2026-11-10T00:00:00.000Z t=1 [INFO ] [" + channel + "] " + " ".join(f"{k}={v}" for k, v in fields.items())


def frame(source=1, epoch=1, batch=1, count=1, admitted="false"):
    return [
        log("capture-timeline", pacing="capture-pair", FG="true"),
        log("frame-batch", source=source, epoch=epoch, revision=1, batch=batch, count=count),
        log("live-fg-admission", revision=1, source=source, admitted=admitted, rejectedPairs=1),
        log("capture-graph-sample", source=source, epoch=epoch, revision=1, arrival=1_000_000, start=1_010_000, submitted=1_020_000),
        log("capture-present-sample", source=source, epoch=epoch, revision=1, batch=batch, generated="false",
            subframe=0, arrival=1_000_000, ready=1_100_000, begin=1_300_000, end=1_310_000),
        log("pacing-sample", arrival=1_000_000, generated="false", begin=1_300_000, end=1_310_000, lateMs=2, queue=1),
    ]


class LiveSessionTests(unittest.TestCase):
    def setUp(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **overrides):
        app, profile = self.root / "app", self.root / "baseline"
        app.mkdir(exist_ok=True)
        profile.mkdir(exist_ok=True)
        exe = app / "veyra_qml_ui.exe"
        exe.write_bytes(b"synthetic executable: never launched")
        runner.write_json(profile / "qml-preferences.v1.json", {"captureColorSpace": 2, "recordFps": 0, "screenshotDir": "old"})
        (profile / "chain-session.v1").write_text("synthetic chain settings", encoding="utf-8")
        (profile / "chain-session.v1.bak").write_text("synthetic backup", encoding="utf-8")
        (profile / "chain-session.v1.field-render.effects").write_text("synthetic serializer sidecar", encoding="utf-8")
        (profile / "capture-preferences.v1").write_text("synthetic capture settings", encoding="utf-8")
        (profile / "clip.mp4").write_bytes(b"do not copy media")
        url = self.root / "url.txt"
        url.write_text("capture2:0123:7:-1::0?fps=60\n", encoding="ascii")
        args = argparse.Namespace(exe=exe, profile_source=profile, capture_url_file=url, output_root=self.root / "runs",
            label="baseline", mode="timing", verbose="on", size="2560x1400", warmup_seconds=10,
            duration_seconds=45, startup_seconds=20, target_fps=60, sequence=None, observation_file=None, hash_runtime=False)
        for key, value in overrides.items():
            setattr(args, key, value)
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.prepare(args)

    def manifest_for(self, lines):
        path = self.prepare(warmup_seconds=0)
        manifest = runner.read_json(path)
        manifest.update(status="exited", exit_code=0)
        runner.write_json(path, manifest)
        (path.parent / "engine.log").write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_profile_chain_and_sidecars_preserved_without_media(self):
        path = self.prepare()
        manifest = runner.read_json(path)
        self.assertEqual((path.parent / "profile/chain-session.v1").read_bytes(), (self.root / "baseline/chain-session.v1").read_bytes())
        self.assertTrue((path.parent / "profile/chain-session.v1.bak").is_file())
        self.assertTrue((path.parent / "profile/chain-session.v1.field-render.effects").is_file())
        self.assertFalse((path.parent / "profile/clip.mp4").exists())
        prefs = runner.read_json(path.parent / "profile/qml-preferences.v1.json")
        self.assertEqual(prefs["captureColorSpace"], 2)
        self.assertEqual(prefs["recordFps"], 0)
        self.assertEqual(prefs["screenshotDir"], "visual/screenshots")
        self.assertEqual(runner.read_json(self.root / "baseline/qml-preferences.v1.json")["screenshotDir"], "old")
        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["observations"], {})

    def test_supported_command_relative_ascii_profile(self):
        command = runner.command_for(Path("E:/Veyra/veyra_qml_ui.exe"), "capture2:abc:1:-1::0", "2560x1400", 75)
        self.assertEqual(command[1:-1], ["--data-dir", "profile", "--page", "min", "--size", "2560x1400", "--exit-after", "75000"])
        self.assertNotIn("--capture", command)
        self.assertNotIn("--record", command)

    def test_executable_alias_is_not_resolved_for_launch(self):
        original = Path.resolve
        executable = self.root / "app/veyra_qml_ui.exe"
        canonical = self.root / "实体/veyra_qml_ui.exe"
        def resolve(path, *args, **kwargs):
            return canonical if path == executable else original(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            path = self.prepare()
        manifest = runner.read_json(path)
        self.assertEqual(manifest["command"][0], str(executable))
        self.assertEqual(manifest["identity"]["executable"]["path"], str(executable))
        self.assertEqual(manifest["identity"]["executable"]["canonical_path"], str(canonical))

    def test_observation_never_inferred_from_intent(self):
        path = self.prepare()
        manifest = runner.read_json(path)
        self.assertIn("capture_url", manifest["intent"])
        self.assertNotIn("negotiated_format", manifest["observations"])
        self.assertIn("unverified", manifest["identity"]["checkout"]["executable_matches_checkout"])

    def test_unique_directories_and_runtime_hash_optional(self):
        first, second = self.prepare(), self.prepare()
        self.assertNotEqual(first, second)
        self.assertFalse(runner.read_json(first)["identity"]["runtime_hashing"])

    def test_time_limit(self):
        with self.assertRaisesRegex(ValueError, "240"):
            self.prepare(duration_seconds=240)

    def test_channel_parser_skips_log_level(self):
        events = runner.extra_events([log("frame-batch", source=1), "unrelated", log("capture-timing", callbackFps=60)])
        self.assertEqual(events["frame-batch"][0]["source"], 1)
        self.assertEqual(events["capture-timing"][0]["callbackFps"], 60)

    def test_rejected_real_only_hold_same_host_clock(self):
        lines = frame()
        report = runner.fallback_observations(lines, runner.ANALYSIS.analyze(lines))
        self.assertEqual(report["sample_count"], 1)
        self.assertEqual(report["ready_to_present_ms"]["p50"], 20)
        self.assertEqual(report["deadline_after_ready_ms"]["p50"], 18)

    def test_vfg_rescue_not_called_skipped(self):
        lines = frame(count=2)
        self.assertEqual(runner.fallback_observations(lines, runner.ANALYSIS.analyze(lines))["sample_count"], 0)

    def test_expired_generated_pair_association(self):
        lines = frame(count=2, admitted="true") + [log("fg-deadline", revision=1, batch=1, subframe=1, expired="true")]
        report = runner.fallback_observations(lines, runner.ANALYSIS.analyze(lines))
        self.assertEqual(report["sample_count"], 1)
        self.assertFalse(report["samples"][0]["rejected_real_only_batch"])
        self.assertEqual(report["samples"][0]["sampled_expired_subframes"], 1)

    def test_missing_epoch_admission_cannot_alias_reset(self):
        lines = frame() + [log("frame-batch", source=1, epoch=2, revision=1, batch=2, count=1)]
        report = runner.fallback_observations(lines, runner.ANALYSIS.analyze(lines))
        self.assertEqual(report["sample_count"], 0)
        self.assertEqual(report["join_issues"]["admission_identity_ambiguous"], 1)

    def test_warmup_filters_fallback(self):
        lines = frame()
        report = runner.fallback_observations(lines, runner.ANALYSIS.analyze(lines, warmup_seconds=2))
        self.assertEqual(report["sample_count"], 0)

    def test_multi_session_rejected_not_guessed_split(self):
        path = self.manifest_for(frame() + [log("frame-flow", session=1), log("frame-flow", session=2)])
        with self.assertRaisesRegex(ValueError, "Multiple source sessions"):
            runner.analyze_manifest(path)

    def test_capture_reopen_rejected(self):
        path = self.manifest_for(frame() + ["[capture] Run hr=0x0 actual=2560x1440 nominalFps=60"] * 2)
        with self.assertRaisesRegex(ValueError, "reopened"):
            runner.analyze_manifest(path)

    def test_explicit_session_ranges_preserve_evidence(self):
        one = frame() + [log("frame-flow", session=1)]
        two = frame(source=2, batch=2) + [log("frame-flow", session=2)]
        path = self.manifest_for(one + two)
        ranges = path.parent / "ranges.json"
        runner.write_json(ranges, {"segments": [
            {"name": "one", "start_line": 1, "end_line": len(one), "boundary_evidence": "synthetic boundary one"},
            {"name": "two", "start_line": len(one)+1, "end_line": len(one)+len(two), "boundary_evidence": "synthetic boundary two"}]})
        with contextlib.redirect_stdout(io.StringIO()):
            result = runner.analyze_manifest(path, ranges)
        self.assertEqual(len(result), 2)
        saved = runner.read_json(path.parent / "analysis/sessions.json")
        self.assertEqual(saved["segments"][0]["parsed_session_ids"], [1])
        self.assertEqual(saved["segments"][1]["parsed_session_ids"], [2])

    def test_overlap_rejected(self):
        path = self.manifest_for(frame())
        ranges = path.parent / "ranges.json"
        runner.write_json(ranges, {"segments": [{"name": "a", "start_line": 1, "end_line": 3, "boundary_evidence": "test"},
                                              {"name": "b", "start_line": 3, "end_line": 6, "boundary_evidence": "test"}]})
        with self.assertRaisesRegex(ValueError, "non-overlapping"):
            runner.analyze_manifest(path, ranges)

    def test_launch_uses_owned_directory_and_logs(self):
        path = self.prepare()
        child = Mock(pid=12345)
        child.wait.return_value = 0
        with patch.object(runner.subprocess, "Popen", return_value=child) as popen, contextlib.redirect_stdout(io.StringIO()):
            report = runner.launch(path)
        self.assertEqual(report["status"], "exited")
        self.assertEqual(popen.call_args.kwargs["cwd"], path.parent)
        self.assertEqual(popen.call_args.kwargs["env"]["VEYRA_LOG_FILE"], "engine.log")
        self.assertTrue((path.parent / "profile-at-launch/chain-session.v1").is_file())
        with self.assertRaisesRegex(ValueError, "only once"):
            runner.launch(path)

    def test_launch_rejects_runtime_or_qml_identity_change(self):
        path = self.prepare()
        (self.root / "app/Main.qml").write_text("import QtQuick", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "QML sources changed"):
            runner.launch(path)

    def test_recording_packet_cadence_not_nominal_rate(self):
        video = self.root / "synthetic.mp4"
        video.write_bytes(b"synthetic file never decoded")
        fake = Mock(returncode=0, stdout=json.dumps({"streams": [{"r_frame_rate": "120/1"}],
            "packets": [{"pts_time": "0"}, {"pts_time": "0.016"}, {"pts_time": "0.050"}]}))
        with patch.object(runner.subprocess, "run", return_value=fake):
            report = runner.inspect_recording(video, self.root / "ffprobe.exe", self.root / "probe.json")
        self.assertEqual(report["mean_picture_cadence_hz"], 40)
        self.assertEqual(report["packet_interval_ms"]["count"], 2)

    def test_similarity_static_has_no_engine_rate_claim(self):
        report = runner.similarity_estimates([bytes([10]*100)]*4, [0, 1/60, 2/60, 3/60])
        self.assertAlmostEqual(report["decoded_picture_hz"], 60)
        self.assertEqual(report["threshold_sweep"][0]["recorded_picture_change_hz"], 0)
        self.assertEqual(report["threshold_sweep"][0]["estimated_repeats"], 3)

    def test_similarity_tracks_accumulated_slow_changes(self):
        report = runner.similarity_estimates([bytes([i]*100) for i in range(5)], [0, .1, .2, .3, .4])
        self.assertEqual(report["threshold_sweep"][-1]["estimated_changes"], 2)

    def test_similarity_rejects_timestamp_mismatch_or_regression(self):
        with self.assertRaisesRegex(ValueError, "counts must match"):
            runner.similarity_estimates([b"a"], [])
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            runner.similarity_estimates([b"a", b"b"], [1, 1])

    def test_empty_similarity_is_unavailable(self):
        report = runner.similarity_estimates([], [])
        self.assertIsNone(report["decoded_picture_hz"])
        self.assertIsNone(report["threshold_sweep"][0]["recorded_picture_change_hz"])

    def test_capture_observation_never_uses_requested_rate_as_cadence(self):
        lines = frame() + ["[capture] Run hr=0x0 actual=2560x1440 nominalFps=60.000", log("capture-timing", callbackFps=59.97)]
        result = runner.capture_observations(runner.extra_events(lines), lines, runner.ANALYSIS.analyze(lines, duration_seconds=45))
        self.assertEqual(result["successful_run_media"][0]["driver_nominal_fps"], 60)
        self.assertEqual(result["transport_callback_fps_unwindowed_summaries"]["p50"], 59.97)
        self.assertFalse(result["window_coverage"]["observed_after_requested_window"])


if __name__ == "__main__":
    unittest.main()
