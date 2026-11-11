"""Offline comparison of completed verbose-on/off console-capture trials.

Never opens a source. Full-run rolling snapshots are NOT pooled frame samples.
Only verbose logs with host markers can produce the requested steady window.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("console_logging_analysis", Path(__file__).with_name("analyze-console-capture.py"))
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)
CHANNEL = re.compile(r"\[(capture-timing|frame-flow|metrics|engine-stall|capture)\]\s+(.*)")
COUNTERS = ("captureReceived mailboxOverwritten sourceAccepted sourceSkippedBeforeGraph realSubmitted "
            "fgCandidate fgSkippedBeforeEval fgEvaluated fgWarmup fgSkippedForReset fgReduced fgReadyValid "
            "fgInvalid realPresented generatedPresented generatedExpiredAfterEval cancelledBeforePresent "
            "slotWaitCount").split()
PERIODIC = ("periodicPreludeMs periodicFrameFlowMs periodicSnapshotMs periodicVramQueryMs "
            "periodicVramWatchMs periodicCaptureLogsMs periodicLogsMs").split()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def snapshots(values):
    """A summary of reported snapshot values; never call it a frame percentile."""
    return ({"count": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}
            if values else {"count": 0})


def events_from(lines):
    events = defaultdict(list)
    for index, line in enumerate(lines, 1):
        match = CHANNEL.search(line)
        if match:
            fields = {key: ANALYSIS.number(value) for key, value in ANALYSIS.FIELD.findall(match[2])}
            events[match[1]].append({**fields, "line": index, "raw": line})
    return events


def identity(manifest):
    intent = manifest["intent"]
    return {
        "exe_sha256": manifest["identity"]["executable"]["sha256"],
        "qml": manifest["identity"]["qml_sources"],
        "runtime": manifest["identity"]["runtime_inventory"],
        "profile": manifest["profile_at_launch"]["copied"],
        "intent": {key: value for key, value in intent.items() if key not in ("verbose", "url_evidence")},
        "environment": {key: value for key, value in manifest["environment_overrides"].items()
                        if key not in ("TEMP", "TMP", "VEYRA_VERBOSE_FRAME_LOGS")},
        "inherited_diagnostics": manifest.get("inherited_diagnostic_environment", {}),
    }


def load_completed(path, expected_trials):
    """Validate every manifest before touching ANY raw log, including earlier runs."""
    records = read_json(path)
    if not isinstance(records, list) or len(records) != expected_trials:
        raise ValueError("Trial list is incomplete or has an unexpected count")
    loaded, ids, reference = [], set(), None
    for record in records:
        if record.get("status") != "exited" or record.get("exit_code") != 0:
            raise ValueError("All listed trials must have exited successfully before analysis")
        manifest_path = Path(record["manifest"])
        if not manifest_path.is_absolute():
            manifest_path = Path(path).parent / manifest_path
        manifest = read_json(manifest_path)
        if manifest.get("status") != "exited" or manifest.get("exit_code") != 0:
            raise ValueError("Trial manifest is active, incomplete or unsuccessful")
        if record["trial"] in ids:
            raise ValueError("Duplicate trial identity")
        ids.add(record["trial"])
        mode = record["verbose"]
        if mode not in ("on", "off") or manifest["intent"]["verbose"] != mode:
            raise ValueError("Verbose label and manifest disagree")
        if manifest["environment_overrides"].get("VEYRA_VERBOSE_FRAME_LOGS") != ("1" if mode == "on" else "0"):
            raise ValueError("Verbose label and actual environment disagree")
        current = identity(manifest)
        if reference is not None and reference != current:
            raise ValueError("Executable/QML/runtime/profile/intent/environment identity differs between trials")
        reference = current
        loaded.append((record, manifest_path, manifest))
    if {record["verbose"] for record, _, _ in loaded} != {"on", "off"}:
        raise ValueError("Comparison requires both verbose modes")
    return loaded, reference


def analyze_lines(lines, manifest):
    events, parsed = events_from(lines), ANALYSIS.parse(lines)
    sessions = {row["session"] for rows in events.values() for row in rows if ANALYSIS.numeric(row, "session")}
    run_markers = [row for row in events["capture"] if re.search(r"\bRun hr=", row["raw"])]
    if len(sessions) != 1 or len(run_markers) != 1 or "Run hr=0x0 " not in run_markers[0]["raw"]:
        raise ValueError("Expected one observed source session and one successful capture Run")
    closed = [row for row in events["frame-flow"] if row.get("state") == "closed"]
    resets = [row for row in events["metrics"] if "reset session=" in row["raw"]]
    keys = [(row.get("session"), row.get("revision"), row.get("epoch")) for row in closed]
    if not closed or len(closed) != len(resets) or len(keys) != len(set(keys)):
        raise ValueError("Closed metrics-window coverage is missing or ambiguous; totals unavailable")
    totals = {}
    for key in COUNTERS:
        if not all(ANALYSIS.numeric(row, key) and row[key] >= 0 for row in closed):
            raise ValueError("Missing/invalid closed counter: " + key)
        totals[key] = sum(row[key] for row in closed)
    rolling = events["capture-timing"]
    rolling_keys = sorted({key for row in rolling for key in row if key.endswith("P95Ms") or key in ("callbackFps", "readAgeMs")})
    rolling_summary = {key: snapshots([row[key] for row in rolling if ANALYSIS.numeric(row, key)]) for key in rolling_keys}
    stalls = events["engine-stall"]
    # Marks are incremental elapsed spans. In the subdivided binary periodicLogs
    # is only the final residual; sum all seven fields for the old whole bucket.
    for row in stalls:
        row["periodic_combined_ms"] = sum(row.get(key, 0) for key in PERIODIC)
    dominant = Counter(max((key for key in row if key.endswith("Ms") and key != "totalMs"),
                          key=lambda key: row[key], default="unavailable") for row in stalls)
    stall_fields = sorted({key for row in stalls for key in row if key.endswith("Ms") or key == "periodic_combined_ms"})
    stall_summary = {key: snapshots([row[key] for row in stalls if ANALYSIS.numeric(row, key)]) for key in stall_fields}
    intent = manifest["intent"]
    host_markers = [row["arrival"] for row in parsed["capture-ingress-sample"] if ANALYSIS.numeric(row, "arrival") and row["arrival"] > 0]
    selected = {"status": "unavailable_no_capture_host_markers", "analysis": None}
    crosscheck = {"status": "unavailable_without_full_frame_detail"}
    if host_markers:
        timing = ANALYSIS.analyze(lines, manifest["label"], intent["warmup_seconds"], intent["duration_seconds"],
                                  target_fps=intent.get("target_fps"))
        end = timing["window"]["end_host_100ns_exclusive"]
        extends = max(host_markers) >= end
        selected = {"status": "available" if extends else "incomplete_requested_window", "analysis": timing,
                    "host_log_extends_through_requested_window": extends}
        observed = {"realSubmitted": len(parsed["capture-graph-sample"]),
                    "realPresented": sum(row.get("generated") is False for row in parsed["capture-present-sample"]),
                    "generatedPresented": sum(row.get("generated") is True for row in parsed["capture-present-sample"])}
        crosscheck = {"status": "matched" if all(totals[k] == v for k, v in observed.items()) else "incomplete_or_mismatch",
                      "observed_frame_detail_totals": observed}
    return {
        "single_observed_source_session": list(sessions)[0], "capture_run_evidence": run_markers[0],
        "closed_metrics_window_count": len(closed), "closed_window_keys": keys,
        "full_run_counter_totals": totals, "full_run_detail_crosscheck": crosscheck,
        "rolling_snapshot_summary": rolling_summary, "rolling_snapshots": rolling,
        "selected_host_window": selected,
        "thresholded_stalls": {"count": len(stalls), "dominant_partition_counts": dict(dominant),
                               "reported_partition_summary_ms": stall_summary, "records": stalls},
        "errors": [line for line in lines if "[ERROR]" in line or "[FATAL]" in line],
    }


def compare(path, expected_trials=6):
    loaded, shared = load_completed(path, expected_trials)
    results = []
    for record, manifest_path, manifest in loaded:
        directory = Path(manifest["cwd"])
        if list(directory.glob("engine.old*.log")):
            raise ValueError("Rotated raw log; full-run coverage unavailable")
        raw = (directory / "engine.log").read_bytes()
        result = analyze_lines(raw.decode("utf-8-sig", errors="replace").splitlines(), manifest)
        result.update(trial=record["trial"], verbose=record["verbose"], manifest=str(manifest_path),
                      started_utc=manifest.get("started_utc"), ended_utc=manifest.get("ended_utc"),
                      observations=manifest.get("observations", {}), raw_sha256=hashlib.sha256(raw).hexdigest(),
                      log_bytes={"engine": len(raw), "console": (directory / "console.log").stat().st_size
                                 if (directory / "console.log").is_file() else None})
        results.append(result)
    return {"schema_version": 1, "shared_identity": shared, "trials": results,
            "limitations": [
                "Exploratory sequential trials; source pixels, scheduling and user actions are not controlled. No causal logging overhead estimate.",
                "Both modes retain ordinary logs. The periodic trace flag is held fixed. No processing or latency improvement claimed.",
                "Rolling full-run snapshots overlap and may reset. Their median/min/max are summaries of reported statistics, never pooled frame percentiles.",
                "TimingWindow defaults to 1200 samples without an age limit; livePresent/livePresentGpu use one second. Other snapshot fields use their own source windows.",
                "No host-window metrics are invented for verbose-off. UTC log emission time is not correlated to callback host time.",
                "Closed metrics windows reset on settings/hard reset; soft history changes may retain a window. Only one closed snapshot per window is summed, never active snapshots.",
                "Stall records are thresholded at 45ms and include CPU descheduling. Absence of a stall record does not mean a partition took zero time.",
                "Host and GPU clocks stay separate. Present return is software submission, not physical scanout or controller-to-photon latency.",
                "Runtime equality uses the recorded inventory; unhashed DLLs are compared by path/size/mtime, not claimed byte verification.",
            ]}


def markdown(report):
    lines = ["# Exploratory logging comparison", "", "Completed trials; full-process rolling values below are not pooled frame percentiles.", "",
             "| Trial | Verbose | Engine / console bytes | Closed received / real presents / overwritten | Reported age-p95 snapshot median [min,max] ms | Threshold stalls |",
             "|---|---|---:|---:|---:|---:|"]
    for row in report["trials"]:
        stats = row["rolling_snapshot_summary"].get("callbackToPresentReturnP95Ms", {})
        age = (f"{stats['median']:.3f} [{stats['min']:.3f},{stats['max']:.3f}]" if stats.get("count") else "unavailable")
        counts = row["full_run_counter_totals"]
        lines.append(f"| {row['trial']} | {row['verbose']} | {row['log_bytes']['engine']} / {row['log_bytes']['console']} | "
                     f"{counts['captureReceived']} / {counts['realPresented']} / {counts['mailboxOverwritten']} | {age} | {row['thresholded_stalls']['count']} |")
    lines += ["", "Selected host windows (per-frame logging only)", "",
              "| Trial | Availability /host-window coverage | Real age p50 /p95 /p99 ms | Ingress / real presents |", "|---|---|---:|---:|"]
    for row in report["trials"]:
        selected = row["selected_host_window"]
        analysis = selected["analysis"]
        stats = analysis["metrics"].get("real_b_callback_to_present_return_ms", {}) if analysis else {}
        age = " / ".join(f"{stats[k]:.3f}" for k in ("p50", "p95", "p99")) if stats.get("count", 0) > 0 else "unavailable"
        counts = analysis["counts"] if analysis else {}
        coverage = ("complete" if selected["host_log_extends_through_requested_window"] else "partial") if analysis else "unavailable"
        lines.append(f"| {row['trial']} | {selected['status']} /{coverage} | {age} | {counts.get('ingress_records', 'N/A')} / {counts.get('real_present_records', 'N/A')} |")
    lines += ["", "Limitations", ""] + ["- " + item for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-trials", type=int, default=6)
    args = parser.parse_args()
    try:
        result = compare(args.runs, args.expected_trials)
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "comparison.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"status": "analyzed", "trials": len(result["trials"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
