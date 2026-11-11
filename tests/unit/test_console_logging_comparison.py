"""Offline fixtures; no application, capture device, or GPU is opened."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("console_logging_comparison", ROOT / "scripts/acceptance/compare-console-logging.py")
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)
ARTIFACTS = Path("E:/项目/Veyra/tmp/codex-live-5090-20261110/logging-unit")


def log(channel, payload):
    return "2026-11-11T00:00:00.000Z t=1 [INFO ] [" + channel + "] " + payload


def closed(epoch, received, real, state="closed"):
    values = {key: 0 for key in comparison.COUNTERS}
    values.update(captureReceived=received, sourceAccepted=received, realSubmitted=received, realPresented=real)
    return log("frame-flow", f"state={state} session=1 revision=2 epoch={epoch} " + " ".join(f"{k}={v}" for k, v in values.items()))


def source():
    return [log("capture", "Run hr=0x0 actual=2560x1440 nominalFps=60.000"),
            log("metrics", "reset session=1 appliedRevision=2 epoch=1 sourceBase=0")]


def manifest(mode="off"):
    return {"label": "synthetic", "status": "exited", "exit_code": 0,
            "intent": {"warmup_seconds": 0, "duration_seconds": 1, "verbose": mode},
            "identity": {"executable": {"sha256": "same"}, "qml_sources": [], "runtime_inventory": []},
            "profile_at_launch": {"copied": [{"name": "chain-session.v1", "sha256": "same", "bytes": 3}]},
            "environment_overrides": {"VEYRA_VERBOSE_FRAME_LOGS": "1" if mode == "on" else "0", "VEYRA_CAPTURE_PERIODIC_TRACE": "1"}}


class LoggingComparisonTests(unittest.TestCase):
    def test_closed_windows_sum_after_reset_not_active_snapshots(self):
        lines = source() + [closed(1, 9, 8, "active"), closed(1, 10, 9),
            log("metrics", "reset session=1 appliedRevision=2 epoch=2 sourceBase=10"),
            closed(2, 3, 3, "active"), closed(2, 4, 4)]
        result = comparison.analyze_lines(lines, manifest())
        self.assertEqual(result["full_run_counter_totals"]["captureReceived"], 14)
        self.assertEqual(result["full_run_counter_totals"]["realPresented"], 13)
        self.assertEqual(result["closed_metrics_window_count"], 2)

    def test_soft_history_does_not_invent_new_counter_window(self):
        result = comparison.analyze_lines(source() + [closed(1, 3, 2, "active"), closed(5, 10, 9)], manifest())
        self.assertEqual(result["closed_metrics_window_count"], 1)
        self.assertEqual(result["full_run_counter_totals"]["captureReceived"], 10)

    def test_missing_duplicate_or_invalid_closed_counters_rejected(self):
        for rows in ([], [closed(1, 3, 2), closed(1, 3, 2)],
                     [closed(1, 3, 2).replace("captureReceived=3", "captureReceived=unknown")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                comparison.analyze_lines(source() + rows, manifest())

    def test_off_has_no_fabricated_host_window_or_zero_gpu_times(self):
        result = comparison.analyze_lines(source() + [closed(1, 3, 2),
            log("capture-timing", "callbackToPresentReturnP95Ms=2.0 gpuSrP95Ms=0.0")], manifest())
        self.assertEqual(result["selected_host_window"], {"status": "unavailable_no_capture_host_markers", "analysis": None})
        self.assertEqual(result["rolling_snapshot_summary"]["gpuSrP95Ms"]["median"], 0)
        self.assertEqual(result["full_run_detail_crosscheck"]["status"], "unavailable_without_full_frame_detail")

    def test_snapshot_summary_is_not_pooled_frame_percentile(self):
        rows = [log("capture-timing", f"callbackToPresentReturnP95Ms={value}") for value in (1, 9, 5)]
        result = comparison.analyze_lines(source() + rows + [closed(1, 3, 2)], manifest())
        self.assertEqual(result["rolling_snapshot_summary"]["callbackToPresentReturnP95Ms"],
                         {"count": 3, "min": 1, "median": 5, "max": 9})

    def test_new_periodic_marks_are_incremental_and_sum_residual(self):
        rows = [log("engine-stall", "frame=12 totalMs=60 periodicPreludeMs=1 periodicFrameFlowMs=2 periodicSnapshotMs=3 periodicVramQueryMs=40 periodicVramWatchMs=4 periodicCaptureLogsMs=5 periodicLogsMs=0.5")]
        result = comparison.analyze_lines(source() + rows + [closed(1, 3, 2)], manifest())
        stall = result["thresholded_stalls"]
        self.assertEqual(stall["records"][0]["periodic_combined_ms"], 55.5)
        self.assertEqual(stall["dominant_partition_counts"], {"periodicVramQueryMs": 1})

    def test_empty_multiple_sessions_and_multiple_runs_rejected(self):
        for lines in ([], source() + [closed(1, 3, 2).replace("session=1", "session=2")],
                      source() + source() + [closed(1, 3, 2)]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                comparison.analyze_lines(lines, manifest())

    def with_manifests(self, second_status="exited", second_exe="same"):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ARTIFACTS)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        records = []
        for number, mode in enumerate(("on", "off"), 1):
            run = root / str(number)
            run.mkdir()
            value = manifest(mode)
            value["cwd"] = str(run)
            if number == 2:
                value["status"] = second_status
                value["identity"]["executable"]["sha256"] = second_exe
            path = run / "run.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            (run / "engine.log").write_text("\n".join(source() + [closed(1, 3, 2)]), encoding="utf-8")
            records.append({"trial": number, "verbose": mode, "manifest": str(path), "status": "exited", "exit_code": 0})
        path = root / "trials.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def test_refuse_active_manifest_before_any_raw_read(self):
        path = self.with_manifests(second_status="running")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("raw log read prematurely")):
            with self.assertRaisesRegex(ValueError, "active"):
                comparison.compare(path, 2)

    def test_binary_mismatch_refused_before_any_raw_read(self):
        path = self.with_manifests(second_exe="different")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("raw log read prematurely")):
            with self.assertRaisesRegex(ValueError, "identity differs"):
                comparison.compare(path, 2)

    def test_complete_comparison_and_missing_console_are_explicit(self):
        result = comparison.compare(self.with_manifests(), 2)
        self.assertEqual(len(result["trials"]), 2)
        self.assertIsNone(result["trials"][0]["log_bytes"]["console"])
        self.assertIn("unavailable", comparison.markdown(result))

    def test_partial_host_window_is_reported_in_json_and_markdown(self):
        lines = source() + [closed(1, 3, 2),
            log("capture-ingress-sample", "source=1 arrival=1000000 copied=1001000")]
        result = comparison.analyze_lines(lines, manifest("on"))
        self.assertEqual(result["selected_host_window"]["status"], "incomplete_requested_window")
        self.assertFalse(result["selected_host_window"]["host_log_extends_through_requested_window"])
        result.update(trial=1, verbose="on", log_bytes={"engine": 1, "console": 1})
        self.assertIn("incomplete_requested_window /partial", comparison.markdown({"trials": [result], "limitations": []}))

    def test_zero_count_real_age_does_not_crash_markdown(self):
        result = comparison.analyze_lines(source() + [closed(1, 3, 2),
            log("capture-ingress-sample", "source=1 arrival=1000000 copied=1001000")], manifest("on"))
        result["selected_host_window"]["analysis"]["metrics"]["real_b_callback_to_present_return_ms"] = {"count": 0}
        result.update(trial=1, verbose="on", log_bytes={"engine": 1, "console": 1})
        output = comparison.markdown({"trials": [result], "limitations": []})
        self.assertIn("unavailable", output)


if __name__ == "__main__":
    unittest.main()
