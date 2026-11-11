"""Prepare, run and analyze one isolated Veyra console-capture session.

Only `run` opens the source. The URL must come from actual Veyra enumeration /
the capture-ui `open uri` log. Requested settings are never negotiated evidence.
Uses only standard-library Python and the existing offline timing analyzer.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("console_analysis", HERE / "analyze-console-capture.py")
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)
PROFILE_NAMES = {
    "presets.v1", "user-presets.v1", "nr-presets.v1", "ui-session.v1",
    "last-applied.v1", "ui-preferences.v1", "color-looks.v1", "veyra.ini",
    "chain-session.v1", "capture-preferences.v1", "qml-preferences.v1.json",
    "playlist.v1.json", "node-anchors.json",
}
EXTRA_CHANNELS = {
    "capture", "capture-buffer", "capture-decode", "capture-color", "capture-ui",
    "capture-timing", "content-dedup", "content-dedup-frame", "frame-flow", "fg-drops", "fg-deadline",
    "live-fg-admission", "frame-batch", "live-recorder", "ui-record", "image-save", "ui-screenshot",
    "present", "present-sink", "preview-view", "graph-layout", "resolution-plan",
    "display", "hdr", "settings", "qml-window", "capture-reconnect",
    "capture-rejected-real", "capture-fg-fault",
}
CHANNEL = re.compile(r"\[(" + "|".join(sorted(EXTRA_CHANNELS)) + r")\]\s+(.*)")


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def profile_member(path):
    name = path.name
    return (name in PROFILE_NAMES or name.endswith(".json") or
            any(name.startswith(base + ".") for base in PROFILE_NAMES))


def snapshot_profile(source, destination):
    """Do not traverse directories or links, copy media, or promote sidecars."""
    destination.mkdir(parents=True, exist_ok=False)
    copied, excluded = [], []
    for path in sorted(source.iterdir()):
        if not path.is_file() or not profile_member(path):
            excluded.append(path.name)
            continue
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Profile links are not allowed: " + str(path))
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Unexpectedly large profile member: " + str(path))
        before = digest(path)
        shutil.copy2(path, destination / path.name)
        if digest(destination / path.name) != before or digest(path) != before:
            raise ValueError("Profile changed while copying; close its owning app and prepare again: " + str(path))
        copied.append({"name": path.name, "bytes": path.stat().st_size, "sha256": before})
    if not copied:
        raise ValueError("No profile settings found; supply a prepared, non-secret isolated baseline profile")
    return {"copied": copied, "excluded": excluded}


def command_for(exe, capture_url, size, lifetime_seconds):
    # ASCII relative profile path avoids the installed app's observed non-ASCII
    # absolute argument issue. This is a QML release, not the old Win32 CLI.
    return [str(exe), "--data-dir", "profile", "--page", "min", "--size", size,
            "--exit-after", str(round(lifetime_seconds * 1000)), capture_url]


def prepare(args):
    # Preserve an intentional ASCII junction path for the application's argv
    # and runtime lookup. Record canonical identity without launching through it.
    exe, source = Path(os.path.abspath(args.exe)), args.profile_source.resolve()
    if not exe.is_file() or not source.is_dir():
        raise ValueError("Executable and prepared profile directory must exist")
    capture_url = args.capture_url_file.read_text(encoding="utf-8-sig").strip()
    if not capture_url.startswith(("capture:", "capture2:")) or not capture_url.isascii() or any(c.isspace() for c in capture_url):
        raise ValueError("Provide one ASCII capture URL copied from this device's Veyra capture-ui open-uri log")
    lifetime = args.warmup_seconds + args.duration_seconds + args.startup_seconds
    if lifetime > 240:
        raise ValueError("Startup + warmup + duration must be at most 240 seconds")
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", args.label).strip("-")[:60] or "capture"
    run = args.output_root.resolve() / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + label + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    profile = snapshot_profile(source, run / "profile-before")
    shutil.copytree(run / "profile-before", run / "profile")
    for directory in ("temp", "visual/screenshots", "visual/recordings", "analysis"):
        (run / directory).mkdir(parents=True)
    prefs_path = run / "profile/qml-preferences.v1.json"
    prefs = read_json(prefs_path) if prefs_path.exists() else {}
    if not isinstance(prefs, dict):
        raise ValueError("qml-preferences.v1.json is not an object")
    artifact_overrides = {"screenshotDir": "visual/screenshots", "recordDir": "visual/recordings"}
    prefs.update(artifact_overrides)
    write_json(prefs_path, prefs)
    (run / "capture-url.txt").write_text(capture_url + "\n", encoding="ascii")
    identity = {"executable": {"path": str(exe), "canonical_path": str(exe.resolve()), "bytes": exe.stat().st_size, "sha256": digest(exe)},
                "runtime_inventory": [], "runtime_hashing": args.hash_runtime,
                "checkout": {}, "packaged_manifest_files": [], "qml_sources": []}
    for path in sorted(exe.parent.rglob("*.dll")):
        if path.is_symlink():
            continue
        item = {"path": str(path.relative_to(exe.parent)), "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns}
        if args.hash_runtime:
            item["sha256"] = digest(path)
        identity["runtime_inventory"].append(item)
    for path in sorted(exe.parent.rglob("*.qml")):
        if path.is_file() and not path.is_symlink():
            identity["qml_sources"].append({"path": str(path.relative_to(exe.parent)), "sha256": digest(path)})
    for path in sorted(exe.parent.glob("*manifest*.json")):
        identity["packaged_manifest_files"].append({"path": str(path), "sha256": digest(path), "contents": read_json(path)})
    for key, command in (("commit", ["git", "rev-parse", "HEAD"]), ("branch", ["git", "branch", "--show-current"]),
                         ("working_tree", ["git", "status", "--short"])):
        result = subprocess.run(command, cwd=HERE.parents[1], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=10)
        identity["checkout"][key] = result.stdout.strip() if result.returncode == 0 else None
    identity["checkout"]["executable_matches_checkout"] = "unverified; exe hash and source commit are separate identities"
    manifest = {"schema_version": 1, "created_utc": utc(), "status": "prepared", "label": args.label,
                "mode": args.mode, "intent": {"capture_url": capture_url, "url_evidence": str(args.capture_url_file.resolve()),
                    "warmup_seconds": args.warmup_seconds, "duration_seconds": args.duration_seconds,
                    "startup_allowance_seconds": args.startup_seconds, "lifetime_seconds": lifetime,
                    "size_dip": args.size, "target_fps": args.target_fps, "verbose": args.verbose,
                    "sequence": args.sequence or "unconfirmed; no gameplay sequence claimed"},
                "identity": identity, "profile_source": str(source), "profile_snapshot": profile,
                "profile_artifact_path_overrides": artifact_overrides,
                "command": command_for(exe, capture_url, args.size, lifetime),
                "cwd": str(run), "environment_overrides": {"VEYRA_LOG_FILE": "engine.log",
                    "VEYRA_VERBOSE_FRAME_LOGS": "1" if args.verbose == "on" else "0",
                    "TEMP": str(run / "temp"), "TMP": str(run / "temp")},
                "observations": read_json(args.observation_file) if args.observation_file else {},
                "observations_provenance": {"path": str(args.observation_file.resolve()), "sha256": digest(args.observation_file)} if args.observation_file else None,
                "limitations": ["Requested format, size and rate are intent, not negotiated media or rendered geometry.",
                    "No source has been opened by prepare. Only run opens it; release other card owners first.",
                    "No gameplay has been performed or confirmed by this tool.",
                    "One continuous source session per run; do not reconnect, switch sources or change settings during timing.",
                    "Verbose-off retains ordinary application logging. It means frame-detail logging off, not zero logging."]}
    write_json(run / "run.json", manifest)
    print(json.dumps({"manifest": str(run / "run.json"), "status": "prepared", "source_opened": False}))
    return run / "run.json"


def launch(path):
    manifest = read_json(path)
    if manifest["status"] != "prepared":
        raise ValueError("A manifest can be launched only once; prepare a new run")
    run = Path(manifest["cwd"])
    exe = Path(manifest["identity"]["executable"]["path"])
    if digest(exe) != manifest["identity"]["executable"]["sha256"]:
        raise ValueError("Executable changed since preparation")
    qml_now = [{"path": str(p.relative_to(exe.parent)), "sha256": digest(p)}
               for p in sorted(exe.parent.rglob("*.qml")) if p.is_file() and not p.is_symlink()]
    if qml_now != manifest["identity"]["qml_sources"]:
        raise ValueError("QML sources changed since preparation; prepare a new identity snapshot")
    dlls = {str(p.relative_to(exe.parent)): p for p in exe.parent.rglob("*.dll") if not p.is_symlink()}
    if set(dlls) != {item["path"] for item in manifest["identity"]["runtime_inventory"]}:
        raise ValueError("Runtime inventory changed since preparation")
    for item in manifest["identity"]["runtime_inventory"]:
        file = dlls[item["path"]]
        if file.stat().st_size != item["bytes"] or file.stat().st_mtime_ns != item["mtime_ns"] or ("sha256" in item and digest(file) != item["sha256"]):
            raise ValueError("Runtime file changed since preparation: " + item["path"])
    if (run / "engine.log").exists():
        raise ValueError("Run already has an engine log; never append a second process to it")
    env = os.environ.copy()
    inherited = {k: v for k, v in env.items() if k.startswith(("VEYRA_", "QT_", "QML_"))}
    manifest["inherited_diagnostic_environment"] = inherited
    env.update(manifest["environment_overrides"])
    manifest["profile_at_launch"] = snapshot_profile(run / "profile", run / "profile-at-launch")
    manifest["status"], manifest["started_utc"] = "running", utc()
    write_json(path, manifest)
    with (run / "console.log").open("wb") as stream:
        child = subprocess.Popen(manifest["command"], cwd=run, env=env, stdout=stream, stderr=subprocess.STDOUT)
        manifest["pid"] = child.pid
        write_json(path, manifest)
        print(json.dumps({"status": "running", "pid": child.pid, "manifest": str(Path(path).resolve())}), flush=True)
        try:
            code = child.wait(timeout=manifest["intent"]["lifetime_seconds"] + 30)
            manifest.update(status="exited", exit_code=code, ended_utc=utc())
        except subprocess.TimeoutExpired:
            # Do not conceal a hung teardown with a forced kill or fabricate a
            # completed sample. Keep evidence and let the owner resolve it.
            manifest.update(status="teardown_timeout_process_still_running", ended_utc=utc())
    if manifest["status"] == "exited":
        manifest["profile_after"] = snapshot_profile(run / "profile", run / "profile-after")
    write_json(path, manifest)
    print(json.dumps({"status": manifest["status"], "exit_code": manifest.get("exit_code"), "pid": child.pid}))
    return manifest


def extra_events(lines):
    records = defaultdict(list)
    for line_number, line in enumerate(lines, 1):
        # Match known channels rather than letting [INFO ] consume the payload.
        for match in CHANNEL.finditer(line):
            channel = match[1]
            if channel in EXTRA_CHANNELS:
                record = {k: ANALYSIS.number(v) for k, v in ANALYSIS.FIELD.findall(match[2])}
                record.update(line=line_number, raw=line.rstrip())
                records[channel].append(record)
    return records


def fallback_observations(lines, timing):
    """Sampled association, never an inferred counterfactual latency gain."""
    extras, events = extra_events(lines), ANALYSIS.parse(lines)
    issues, samples = defaultdict(int), []
    start, end = timing["window"]["start_host_100ns"], timing["window"]["end_host_100ns_exclusive"]
    def unique(rows, fields, event):
        matches = [row for row in rows if all(key in event and row.get(key) == event[key] for key in fields)]
        return matches[0] if len(matches) == 1 else None
    for present in events["capture-present-sample"]:
        if present.get("generated") or not ANALYSIS.numeric(present, "ready", "begin", "end") or present["ready"] <= 0:
            continue
        if start is not None and present["end"] < start or end is not None and present["end"] >= end:
            continue
        batch = unique(extras["frame-batch"], ("source", "epoch", "revision", "batch"), present)
        if not batch:
            issues["real_present_without_unique_batch"] += 1
            continue
        admission = unique(extras["live-fg-admission"], ("source", "revision"), present)
        if not unique(extras["frame-batch"], ("source", "revision"), present):
            admission = None
            issues["admission_identity_ambiguous"] += 1
        # False admission can still dispatch VFG's faster model. count=1 is
        # required before calling this an observed real-only batch.
        rejected = bool(admission and admission.get("admitted") is False and batch.get("count") == 1)
        expired = [item for item in extras["fg-deadline"] if item.get("batch") == present["batch"] and
                   item.get("revision") == present["revision"] and item.get("expired") is True]
        if not unique(extras["frame-batch"], ("revision", "batch"), present):
            expired = []
            issues["expiry_identity_ambiguous"] += 1
        if not rejected and not expired:
            continue
        pacing = unique(events["pacing-sample"], ("arrival", "begin", "generated"), present)
        if present["begin"] < present["ready"]:
            issues["negative_hold_rejected"] += 1
            continue
        sample = {key: present.get(key) for key in ("source", "epoch", "revision", "batch", "arrival", "ready", "begin", "end")}
        sample.update(real_present_line=present["line"], rejected_real_only_batch=rejected,
                      sampled_expired_subframes=len(expired),
                      ready_observed_to_present_begin_ms=(present["begin"]-present["ready"])/10000,
                      callback_to_present_return_ms=(present["end"]-present["arrival"])/10000 if ANALYSIS.numeric(present, "arrival") and present["arrival"] > 0 else None)
        if pacing and ANALYSIS.numeric(pacing, "lateMs") and timing["coverage"]["deadline_observation_applicability"] == "explicit_scheduled_capture_policy":
            deadline = present["begin"] - pacing["lateMs"] * 10000
            sample["reconstructed_deadline_after_ready_ms"] = max(0, (deadline-present["ready"])/10000)
        samples.append(sample)
    return {"samples": samples, "sample_count": len(samples), "join_issues": dict(issues),
            "ready_to_present_ms": ANALYSIS.distribution([s["ready_observed_to_present_begin_ms"] for s in samples]),
            "deadline_after_ready_ms": ANALYSIS.distribution([s["reconstructed_deadline_after_ready_ms"] for s in samples if "reconstructed_deadline_after_ready_ms" in s]),
            "limitations": ["Admission and expiry records are rate-limited samples, not all pairs. No population rejection rate is inferred.",
                "Admission false alone is not a skipped pair: VFG may use a faster model. Real-only batch count is checked.",
                "Deadline is reconstructed from host begin minus rounded lateMs; GPU ticks are never used.",
                "CPU-observed readiness is an upper bound on actual GPU completion. Ready-to-Present includes other waits.",
                "An observed hold is not proof of removable delay or a safe counterfactual improvement."]}


def capture_observations(extras, lines, timing):
    """Keep driver nominal media rate separate from measured arrival cadence."""
    opened = []
    for event in extras["capture"]:
        match = re.search(r"\bRun hr=0x0 actual=(\d+)x(\d+) nominalFps=([\d.]+)", event["raw"])
        if match:
            opened.append({"width": int(match[1]), "height": int(match[2]), "driver_nominal_fps": float(match[3]), "line": event["line"]})
    events = ANALYSIS.parse(lines)
    host_times = [e[key] for channel, key in (("capture-ingress-sample", "arrival"), ("capture-read-sample", "arrival"),
                  ("capture-graph-sample", "arrival"), ("capture-present-sample", "end"))
                  for e in events[channel] if ANALYSIS.numeric(e, key) and e[key] > 0]
    end = timing["window"]["end_host_100ns_exclusive"]
    callback_rates = [e["callbackFps"] for e in extras["capture-timing"] if ANALYSIS.numeric(e, "callbackFps")]
    return {"successful_run_media": opened, "capture_configuration_evidence": extras["capture"],
        "buffer_evidence": extras["capture-buffer"], "decoder_evidence": extras["capture-decode"],
        "transport_callback_fps_unwindowed_summaries": ANALYSIS.distribution(callback_rates),
        "window_coverage": {"first_host_100ns": min(host_times) if host_times else None,
            "last_host_100ns": max(host_times) if host_times else None,
            "observed_after_requested_window": max(host_times) >= end if host_times and end is not None else None},
        "limitations": ["Run success establishes this application's accepted USB media extent and nominal rate, not HDMI input.",
            "Pixel subtype, range and transfer require the preserved connection/configuration evidence; never infer them from requested URL.",
            "Ordinary callbackFps summaries are rolling unwindowed samples, not unique-picture rate or p95 across frames.",
            "Reaching the requested window end does not prove complete events within it."]}


def analyze_manifest(path, segments_file=None):
    manifest = read_json(path)
    run, log = Path(manifest["cwd"]), Path(manifest["cwd"]) / "engine.log"
    if manifest["status"] != "exited":
        raise ValueError("Analyze only after this owned process has exited cleanly; incomplete live log is not a completed session")
    if (run / "engine.old.log").exists():
        raise ValueError("Log rotated; preserve and explicitly reconstruct ordered evidence before analysis")
    lines = log.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if segments_file:
        segments = read_json(segments_file)["segments"]
    else:
        segments = [{"name": "source-session", "start_line": 1, "end_line": len(lines),
                     "boundary_evidence": "fresh owned process with one positional source; no automatic split"}]
    results, split_manifest, previous_end = [], [], 0
    for segment in segments:
        a, b = segment["start_line"], segment["end_line"]
        if not isinstance(a, int) or not isinstance(b, int) or a < 1 or b < a or b > len(lines) or a <= previous_end or not segment.get("boundary_evidence"):
            raise ValueError("Segments need ordered non-overlapping inclusive line ranges and boundary_evidence")
        previous_end = b
        subset = lines[a-1:b]
        extra = extra_events(subset)
        run_markers = [e for e in extra["capture"] if re.search(r"\bRun hr=", e["raw"])]
        if len(run_markers) > 1 or extra["capture-reconnect"]:
            raise ValueError("Capture reopened or reconnected inside a segment; supply explicit verified line boundaries")
        result = ANALYSIS.analyze(subset, segment["name"], manifest["intent"]["warmup_seconds"],
                                  manifest["intent"]["duration_seconds"], target_fps=manifest["intent"]["target_fps"])
        result["fallback_observations"] = fallback_observations(subset, result)
        result["capture_observations"] = capture_observations(extra, subset, result)
        result["raw_observations"] = dict(extra)
        result["unique_picture_cadence"] = {"status": "estimated only if content-dedup observations exist; otherwise unavailable",
            "dedup_samples": extra["content-dedup"], "per_observed_picture": extra["content-dedup-frame"], "engine_frame_ids_available": False}
        result["geometry"] = manifest["observations"].get("geometry", {"status": "unavailable; measure the actual native video client and fit transform"})
        result["hdmi_signal"] = manifest["observations"].get("hdmi_signal", {"status": "unavailable; USB media dimensions do not establish PS5 HDMI output"})
        result["visual_contamination"] = {"recording_events": len(extra["ui-record"])+len(extra["live-recorder"]),
                                            "screenshot_events": len(extra["image-save"])+len(extra["ui-screenshot"])}
        results.append(result)
        split_manifest.append({**segment, "parsed_session_ids": sorted({e["session"] for e in extra["frame-flow"] if ANALYSIS.numeric(e, "session")}),
                               "source_run_markers": len(run_markers), "range_sha256": hashlib.sha256("\n".join(subset).encode()).hexdigest()})
    if not results:
        raise ValueError("No source-session segments supplied")
    out = run / "analysis"
    out.mkdir(exist_ok=True)
    write_json(out / "sessions.json", {"log": str(log), "sha256": digest(log), "line_number_basis": "1-based inclusive original raw file; per-result events are segment-relative", "segments": split_manifest})
    write_json(out / "console-capture.json", results)
    (out / "console-capture.md").write_text(ANALYSIS.markdown(results), encoding="utf-8")
    summary = {"run": str(path), "mode": manifest["mode"], "exit_code": manifest.get("exit_code"),
        "identity": manifest["identity"]["executable"], "intent": manifest["intent"], "observations": manifest["observations"],
        "segments": [{"name": r["name"], "coverage": r["coverage"], "counts": r["counts"],
                      "capture_observations": r["capture_observations"],
                      "fallback_observations": r["fallback_observations"], "visual_contamination": r["visual_contamination"]} for r in results],
        "measurement_status": "software observations only; completeness is reported per segment, not assumed",
        "physical_scanout_or_controller_latency": "unavailable"}
    write_json(out / "summary.json", summary)
    readable = ["# Live console session", "", "Software observations; Present calls are not display scanout.", "",
                f"Mode: {manifest['mode']}; verbose frame logging: {manifest['intent']['verbose']}; exit: {manifest.get('exit_code')}.", "",
                "Requested settings and measured observations are stored separately in run.json. The preserved profile-at-launch records the actual settings files.", ""]
    for result in results:
        fall = result["fallback_observations"]
        readable += [f"## {result['name']}", "", f"Matched sampled rejected/expired pairs: {fall['sample_count']}. This is not the total rejection count or a proven latency saving.", "",
                     "Observed successful USB media starts: " + json.dumps(result["capture_observations"]["successful_run_media"]) + ".",
                     "Requested window coverage: " + json.dumps(result["capture_observations"]["window_coverage"]) + ".", "",
                     "Capture/decoder negotiation, ordinary timing summaries and content-dedup estimates are preserved verbatim in console-capture.json. Missing detail with verbose logging off remains unavailable.", ""]
    (out / "summary.md").write_text("\n".join(readable), encoding="utf-8")
    print(json.dumps({"status": "analyzed", "output": str(out), "segments": len(results)}))
    return results


def inspect_recording(video, ffprobe, output):
    result = subprocess.run([str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_packets",
        "-show_entries", "stream=codec_name,width,height,pix_fmt,color_range,color_space,color_transfer,color_primaries,r_frame_rate,avg_frame_rate,time_base:packet=pts_time,duration_time,flags", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise ValueError("ffprobe failed: " + result.stderr[-2000:])
    raw = json.loads(result.stdout)
    times = [float(p["pts_time"]) for p in raw.get("packets", []) if "pts_time" in p]
    intervals = [(b-a)*1000 for a, b in zip(times, times[1:]) if b > a]
    report = {"video": str(video.resolve()), "sha256": digest(video), "ffprobe": str(ffprobe.resolve()),
        "streams": raw.get("streams", []), "packet_count": len(raw.get("packets", [])),
        "strictly_increasing_pts": all(b > a for a, b in zip(times, times[1:])) if len(times)>1 else None,
        "packet_interval_ms": ANALYSIS.distribution(intervals),
        "mean_picture_cadence_hz": (len(times)-1)/(times[-1]-times[0]) if len(times)>1 and times[-1]>times[0] else None,
        "limitations": ["Encoded packet cadence is not display cadence or source unique-picture cadence.",
            "Veyra's recorder captures processed graph textures before desktop fit, provider-owned XeSS FG and scanout.",
            "Use a separate timing run; NVENC conversion/copies/encoding add work."], "raw_probe": raw}
    write_json(output, report)
    return report


def similarity_estimates(frames, timestamps):
    """Small-luma threshold sweep against the last classified new picture."""
    if len(frames) != len(timestamps) or any(not math.isfinite(t) for t in timestamps):
        raise ValueError("Decoded image / timestamp counts must match with finite timestamps")
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("Decoded image timestamps must be strictly increasing")
    if frames and (not frames[0] or any(len(f) != len(frames[0]) for f in frames)):
        raise ValueError("Decoded luma frame sizes must match and be nonzero")
    span = timestamps[-1]-timestamps[0] if len(timestamps)>1 else 0
    estimates = []
    for label, mae, band, fraction in (("strict", .25, 3, .001), ("middle", .5, 5, .005), ("loose", 1., 8, .01)):
        reference = frames[0] if frames else None
        changes, repeats = 0, 0
        for frame in frames[1:]:
            difference = [abs(a-b) for a, b in zip(frame, reference)]
            repeat = sum(difference)/len(difference) <= mae and sum(d > band for d in difference)/len(difference) <= fraction
            if repeat:
                repeats += 1
            else:
                changes += 1
                reference = frame
        estimates.append({"threshold": label, "maximum_mean_absolute_luma_difference": mae,
            "component_band": band, "maximum_fraction_outside_band": fraction,
            "estimated_changes": changes, "estimated_repeats": repeats,
            "recorded_picture_change_hz": changes/span if span>0 else None})
    return {"decoded_frames": len(frames), "timestamp_span_seconds": span,
            "decoded_picture_hz": (len(frames)-1)/span if span>0 else None, "threshold_sweep": estimates,
            "limitations": ["Downsampled 160x90 8-bit luma is a similarity estimate, not game-engine frame identity.",
                "Static scenes, small HUD changes, compression, capture noise and slow motion can change classification.",
                "References advance on classified changes; adjacent-only comparison would erase slow accumulated motion.",
                "Dropped recording or presentation frames cannot be recovered; this estimates changes in this recording only.",
                "Generated output must not be interpreted as unique source pictures. Use a no-FG baseline under confirmed sustained motion."]}


def visual_evidence(args):
    if not 0 < args.duration_seconds <= 10:
        raise ValueError("Visual extraction duration must be in (0,10] seconds")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    probe = inspect_recording(args.video, args.ffprobe, output / "recording.json")
    if any(s.get("color_transfer") in ("smpte2084", "arib-std-b67") for s in probe["streams"]):
        raise ValueError("HDR clip preserved, but contact sheets require an explicit verified display transform; automatic tone mapping is not applied")
    source = [str(args.ffmpeg), "-nostdin", "-n", "-ss", str(args.start_seconds), "-t", str(args.duration_seconds), "-i", str(args.video)]
    sheet_filter = f"fps=12/{args.duration_seconds},scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,tile=4x3"
    commands = [source + ["-an", "-vf", sheet_filter, "-frames:v", "1", str(output / "contact-sheet.png")],
                source + ["-an", "-vf", f"fps=3/{args.duration_seconds}", "-frames:v", "3", str(output / "detail-%02d.png")]]
    for number, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, timeout=60)
        (output / f"ffmpeg-visual-{number}.log").write_bytes(result.stderr)
        if result.returncode:
            raise ValueError("Visual extraction failed; preserved ffmpeg log: " + str(output))
    if not (output / "contact-sheet.png").is_file() or not list(output.glob("detail-*.png")):
        raise ValueError("Requested visual interval produced no images; inspect the preserved ffmpeg logs")
    # showinfo reports the exact decoded frame indices and timestamps used by
    # this same raw stream. Do not join packet PTS to decode order by guesswork.
    raw_command = source + ["-an", "-vf", "scale=160:90:flags=area,format=gray,showinfo", "-fps_mode", "passthrough",
                            "-frames:v", "2400", "-f", "rawvideo", "pipe:1"]
    raw = subprocess.run(raw_command, capture_output=True, timeout=60)
    (output / "ffmpeg-similarity.log").write_bytes(raw.stderr)
    if raw.returncode or len(raw.stdout) % (160*90):
        raise ValueError("Incomplete raw decoded frames; inspect preserved ffmpeg-similarity.log")
    frames = [raw.stdout[i:i+160*90] for i in range(0, len(raw.stdout), 160*90)]
    stamp = {}
    for match in re.finditer(r"\[Parsed_showinfo[^\]]*\].*?\bn:\s*(\d+).*?\bpts_time:([^\s]+)", raw.stderr.decode("utf-8", errors="replace")):
        index, value = int(match[1]), float(match[2])
        if index in stamp:
            raise ValueError("Ambiguous duplicate showinfo frame index")
        stamp[index] = value
    if any(i not in stamp for i in range(len(frames))):
        raise ValueError("Missing showinfo timestamps; image/time alignment unavailable")
    estimates = similarity_estimates(frames, [stamp[i] for i in range(len(frames))])
    estimates.update(recording_kind=args.recording_kind, requested_start_seconds=args.start_seconds,
                     requested_duration_seconds=args.duration_seconds, frame_limit_reached=len(frames)>=2400,
                     extra_decoded_timestamps_not_output=sum(i>=len(frames) for i in stamp))
    write_json(output / "similarity.json", estimates)
    write_json(output / "visual-manifest.json", {"source_video": str(args.video.resolve()), "source_sha256": probe["sha256"],
        "ffmpeg_sha256": digest(args.ffmpeg), "ffprobe_sha256": digest(args.ffprobe), "commands": commands + [raw_command],
        "recording_kind": args.recording_kind, "contact_sheet": str(output / "contact-sheet.png"),
        "detail_images": [str(p) for p in sorted(output.glob("detail-*.png"))],
        "contact_sheet_basis": "12 equally spaced timestamp samples, left to right then top to bottom; ffmpeg fps may repeat a picture",
        "timing_classification": "offline decoded recording evidence; not live capture latency"})
    lines = ["# Offline visual evidence", "", "This is a decoded recording comparison, not a live latency measurement.", "",
             f"Recording kind: {args.recording_kind}; decoded pictures: {len(frames)}; timestamp span: {estimates['timestamp_span_seconds']:.3f} s.", "",
             "| Threshold | Estimated recorded-picture changes/s | Repeats |", "|---|---:|---:|"]
    for estimate in estimates["threshold_sweep"]:
        rate = estimate["recorded_picture_change_hz"]
        lines.append(f"| {estimate['threshold']} | {rate:.3f} | {estimate['estimated_repeats']} |" if rate is not None else f"| {estimate['threshold']} | unavailable | {estimate['estimated_repeats']} |")
    lines += ["", "![Contact sheet](contact-sheet.png)", ""] + ["- " + item for item in estimates["limitations"]]
    (output / "visual-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "offline_visual_evidence_created", "output": str(output), "decoded_frames": len(frames)}))
    return estimates


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare", help="Snapshot an isolated profile and identity; never opens capture")
    for name in ("exe", "profile-source", "capture-url-file", "output-root"):
        prep.add_argument("--"+name, type=Path, required=True)
    prep.add_argument("--label", required=True)
    prep.add_argument("--mode", choices=("timing", "visual"), default="timing")
    prep.add_argument("--verbose", choices=("on", "off"), default="on")
    prep.add_argument("--size", default="2560x1400")
    prep.add_argument("--warmup-seconds", type=positive, default=10)
    prep.add_argument("--duration-seconds", type=positive, default=45)
    prep.add_argument("--startup-seconds", type=positive, default=20)
    prep.add_argument("--target-fps", type=positive)
    prep.add_argument("--sequence", help="Human-confirmed sequence description, not proof it occurred")
    prep.add_argument("--observation-file", type=Path)
    prep.add_argument("--hash-runtime", action="store_true")
    run = sub.add_parser("run", help="Launch the owned process; release other capture-card owners first")
    run.add_argument("--manifest", type=Path, required=True)
    analyze = sub.add_parser("analyze", help="Analyze completed source sessions without opening capture")
    analyze.add_argument("--manifest", type=Path, required=True)
    analyze.add_argument("--segments-file", type=Path)
    recording = sub.add_parser("inspect-recording", help="Read packet cadence with an existing ffprobe executable")
    for name in ("video", "ffprobe", "output"):
        recording.add_argument("--"+name, type=Path, required=True)
    visual = sub.add_parser("visual-evidence", help="Offline contact sheet, detail PNGs and cautious luma-similarity estimates")
    for name in ("video", "ffmpeg", "ffprobe", "output-dir"):
        visual.add_argument("--"+name, type=Path, required=True)
    visual.add_argument("--start-seconds", type=positive, default=0)
    visual.add_argument("--duration-seconds", type=positive, default=6)
    visual.add_argument("--recording-kind", choices=("baseline-no-fg", "processed-fg", "unknown"), required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if not re.fullmatch(r"[1-9][0-9]{1,4}x[1-9][0-9]{1,4}", args.size) or not args.duration_seconds or args.target_fps == 0:
                raise ValueError("Size must be positive WxH; duration and target FPS must be positive")
            prepare(args)
        elif args.action == "run":
            launch(args.manifest)
        elif args.action == "analyze":
            analyze_manifest(args.manifest, args.segments_file)
        elif args.action == "inspect-recording":
            inspect_recording(args.video, args.ffprobe, args.output)
        else:
            visual_evidence(args)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
