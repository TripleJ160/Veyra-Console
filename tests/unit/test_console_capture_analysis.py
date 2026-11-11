"""Synthetic log-contract regression tests. No capture or performance claims."""
import importlib.util
import json
from pathlib import Path
import re
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/acceptance/analyze-console-capture.py"
SPEC = importlib.util.spec_from_file_location("console_capture_analysis", SCRIPT)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


def log(channel, **fields):
    return "2026-11-10T00:00:00Z t=123 [INFO ] [" + channel + "] " + " ".join(f"{key}={value}" for key, value in fields.items())


def frame(source=1, arrival=1_000_000, epoch=1, revision=1):
    common = dict(source=source, arrival=arrival)
    return [
        log("capture-ingress-sample", **common, copied=arrival + 1000),
        log("capture-read-sample", **common, read=arrival + 2000, width=1920, height=1080, format=23),
        log("capture-graph-sample", **common, epoch=epoch, revision=revision,
            start=arrival + 3000, submitted=arrival + 4000, slotWaitMs=.02),
        log("capture-present-sample", **common, epoch=epoch, revision=revision,
            generated=0, subframe=0, arrivalA=0, ready=arrival + 8000,
            begin=arrival + 9000, end=arrival + 10000),
        log("pacing-sample", arrival=arrival, begin=arrival + 9000, end=arrival + 10001,
            generated=0, queue=1, lateMs=.25),
        log("gpu-timestamp", frame=source, epoch=epoch, revision=revision, stage=1,
            begin=8_000_000_000, end=8_000_001_000, frequency=1_000_000, ms=1),
    ]


class ConsoleCaptureAnalysisTests(unittest.TestCase):
    def test_stage_mapping_matches_checkout(self):
        header = SCRIPT.parents[2] / "include/veyra/diagnostics/FrameMetrics.h"
        body = re.search(r"enum class GpuStage\s*\{(.*?)\};", header.read_text(encoding="utf-8"), re.S)[1]
        stages = [name.strip() for name in body.split(",") if name.strip() != "Count"]
        self.assertEqual(analysis.GPU_STAGES, stages)

    def test_join_and_separate_clocks(self):
        result = analysis.analyze(frame() + [log("capture-timeline", pacing="capture-pair", FG="true")])
        self.assertAlmostEqual(result["metrics"]["gpu_Sr_ms"]["p50"], 1)
        self.assertAlmostEqual(result["metrics"]["real_submit_to_ready_observed_ms"]["p50"], .4)
        self.assertAlmostEqual(result["metrics"]["mailbox_after_copy_ms"]["p50"], .1)
        self.assertEqual(result["counts"]["observed_present_after_deadline"], 1)
        self.assertEqual(result["coverage"]["observed_formats"], [(1920, 1080, 23)])
        self.assertNotIn("gpu_graph_envelope_ms", result["metrics"])

    def test_capture_ready_late_ms_is_not_deadline_miss(self):
        result = analysis.analyze(frame() + [log("capture-timeline", pacing="capture-ready", FG="false")])
        self.assertEqual(result["coverage"]["deadline_observation_applicability"], "not_applicable_capture_ready")
        self.assertNotIn("observed_present_after_deadline", result["counts"])
        self.assertNotIn("scheduled_deadline_deviation_ms", result["metrics"])
        self.assertEqual(result["metrics"]["raw_logged_deadline_deviation_ms"]["p50"], .25)

    def test_missing_or_mixed_policy_does_not_invent_deadline_validity(self):
        for extra in ([], [log("capture-timeline", pacing="capture-ready", FG="false"), log("capture-timeline", pacing="capture-pair", FG="true")]):
            result = analysis.analyze(frame() + extra)
            self.assertEqual(result["coverage"]["deadline_observation_applicability"], "unavailable_missing_or_mixed_policy_evidence")
            self.assertNotIn("observed_present_after_deadline", result["counts"])

    def test_empty_and_unrelated(self):
        result = analysis.analyze(["unrelated text", "[gpu-timestamp] frame=garbage ms=nan"])
        self.assertEqual(result["metrics"], {})
        self.assertFalse(result["coverage"]["timestamped_capture_records_available"])
        self.assertIn("No timestamped measurements", analysis.markdown([result]))
        json.dumps(result, allow_nan=False)

    def test_out_of_order(self):
        lines = frame() + frame(2, 1_200_000)
        expected = analysis.analyze(lines)
        actual = analysis.analyze(reversed(lines))
        self.assertEqual(actual["metrics"], expected["metrics"])
        self.assertEqual(actual["metrics"]["all_present_interval_ms"]["p50"], 20)

    def test_warmup_and_bounded_window(self):
        lines = frame() + frame(2, 11_000_000) + frame(3, 21_000_000)
        result = analysis.analyze(lines, warmup_seconds=1, duration_seconds=1)
        self.assertEqual(result["counts"]["real_present_records"], 1)
        self.assertEqual(result["counts"]["gpu_matched_records"], 1)

    def test_repeated_gpu_identity_is_rejected(self):
        result = analysis.analyze(frame() + frame(arrival=2_000_000))
        self.assertNotIn("gpu_Sr_ms", result["metrics"])
        self.assertEqual(result["coverage"]["join_issues"]["gpu_graph_ambiguous"], 2)
        self.assertEqual(result["metrics"]["real_submit_to_ready_observed_ms"]["count"], 2)

    def test_explicit_sessions_are_rejected(self):
        first = [line + " session=1" for line in frame()]
        second = [line + " session=2" for line in frame(arrival=2_000_000)]
        with self.assertRaisesRegex(ValueError, 'Multiple source sessions'):
            analysis.analyze(first + second)

    def test_reopen_idle_gap_is_rejected(self):
        lines = frame() + [log('frame-flow', session=1)]
        lines += frame(arrival=1_000_000_000, revision=2) + [log('frame-flow', session=2)]
        with self.assertRaisesRegex(ValueError, 'Multiple source sessions'):
            analysis.analyze(lines)

    def test_pacing_only_does_not_claim_capture_coverage(self):
        result = analysis.analyze([log('pacing-sample', arrival=1_000_000,
                                      begin=1_010_000, end=1_020_000, queue=1)])
        self.assertFalse(result['coverage']['timestamped_capture_records_available'])
        self.assertTrue(result['coverage']['timestamped_host_records_available'])

    def test_reset_splits_intervals(self):
        result = analysis.analyze(frame() + frame(2, 1_200_000, epoch=2))
        self.assertNotIn("all_present_interval_ms", result["metrics"])
        self.assertEqual(result["metrics"]["gpu_Sr_ms"]["count"], 2)

    def test_generated_lineage_and_intervals(self):
        lines = frame() + frame(2, 1_200_000)
        lines += [log("capture-present-sample", source=2, epoch=1, revision=1,
                      arrival=1_200_000, arrivalA=1_000_000, generated=1, subframe=1,
                      ready=1_205_000, begin=1_206_000, end=1_207_000)]
        result = analysis.analyze(lines, target_fps=100)
        self.assertAlmostEqual(result["metrics"]["generated_a_callback_to_present_return_ms"]["p50"], 20.7)
        self.assertAlmostEqual(result["metrics"]["generated_b_callback_to_present_return_ms"]["p50"], .7)
        self.assertEqual(result["metrics"]["all_present_interval_ms"]["count"], 2)
        self.assertEqual(result["metrics"]["real_present_interval_ms"]["count"], 1)
        self.assertNotIn("generated_present_interval_ms", result["metrics"])

    def test_missing_ready_and_gpu(self):
        lines = [line for line in frame() if "gpu-timestamp" not in line]
        lines = [line.replace("ready=1008000", "ready=0") for line in lines]
        result = analysis.analyze(lines)
        self.assertNotIn("real_submit_to_ready_observed_ms", result["metrics"])
        self.assertIn("real_submit_to_ready_observed_ms_unavailable", result["coverage"]["join_issues"])
        self.assertNotIn("gpu_Sr_ms", result["metrics"])

    def test_bad_gpu_and_negative_host_duration(self):
        lines = frame()
        lines[0] = lines[0].replace("copied=1001000", "copied=999999")
        lines[-1] = lines[-1].replace("frequency=1000000", "frequency=0")
        result = analysis.analyze(lines)
        self.assertEqual(result["coverage"]["join_issues"]["gpu_invalid_duration"], 1)
        self.assertEqual(result["coverage"]["join_issues"]["callback_copy_lock_ms_negative_rejected"], 1)

    def test_unknown_stage_and_snapshots(self):
        lines = frame()
        lines[-1] = lines[-1].replace("stage=1", "stage=99")
        lines += [log("fg-drops", revision=1, deadline=3, capacity=2, cap=1)]
        result = analysis.analyze(lines)
        self.assertIn("gpu_unknown_99_ms", result["metrics"])
        self.assertEqual(result["unwindowed_snapshots"]["fg-drops"][0]["deadline"], 3)


if __name__ == "__main__":
    unittest.main()
