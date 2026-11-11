"""Analyze Veyra 2.1.5 verbose capture logs without mixing clock domains.

Read-only with respect to the application. Each input file is one source session.
Only uniquely matched events contribute joined durations. No GPU envelope is
formed because equal timestamp frequencies do not establish a shared GPU clock.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re


CHANNELS = {
    "capture-ingress-sample", "capture-read-sample", "capture-graph-sample",
    "capture-present-sample", "gpu-timestamp", "pacing-sample", "frame-flow",
    "fg-drops", "live-fg-admission", "nr-reuse", "content-dedup",
    "live-anchor", "player-timing", "frame-trace", "capture-timeline",
}
EVENT = re.compile(r"\[(" + "|".join(sorted(CHANNELS)) + r")\]\s+(.*)")
FIELD = re.compile(r"(\w+)=([^\s]+)")
GPU_STAGES = (
    "Color Sr Flow Nr Residual Fg1 Fg2 Fg3 Fg4 Fg5 Fg6 Fg7 FgBatch Blit VideoHdr "
    "NrLayer0 NrLayer1 NrLayer2 NrLayer3 ColorNode0 ColorNode1 ColorNode2 "
    "ColorNode3 ColorNode4 ColorNode5 AaNode0 AaNode1 BeautyNode0 BeautyNode1 "
    "BeautyNode2 BeautyNode3 BeautyNode4 BeautyNode5 BeautyDetect"
).split()


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}
    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        low = int(position)
        return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)
    return {"count": len(ordered), "mean": sum(ordered) / len(ordered),
            "min": ordered[0], "p50": percentile(.5), "p95": percentile(.95),
            "p99": percentile(.99), "max": ordered[-1]}


def number(value):
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value, 0) if value.lower().startswith("0x") else int(value)
    except ValueError:
        try:
            result = float(value)
            return result if math.isfinite(result) else value
        except ValueError:
            return value


def numeric(event, *fields):
    return all(isinstance(event.get(key), (int, float)) and
               math.isfinite(event[key]) for key in fields)


def parse(lines):
    events = defaultdict(list)
    for line_number, line in enumerate(lines, 1):
        match = EVENT.search(line)
        if not match:
            continue
        record = {key: number(value) for key, value in FIELD.findall(match[2])}
        record["line"] = line_number
        events[match[1]].append(record)
    return events


def analyze(lines, name="run", warmup_seconds=0, duration_seconds=None,
            start_host_100ns=None, target_fps=None):
    events = parse(lines)
    sessions = {event['session'] for records in events.values() for event in records
                if numeric(event, 'session')}
    if len(sessions) > 1:
        raise ValueError('Multiple source sessions observed; split the log at source-session boundaries before analysis')
    policies = {event.get("pacing") for event in events["capture-timeline"]}
    if policies == {"capture-ready"} and all(event.get("FG") is False for event in events["capture-timeline"]):
        deadline_applicability = "not_applicable_capture_ready"
    elif len(policies) == 1 and policies <= {"capture-pair", "decoded-pair", "source-pts"}:
        deadline_applicability = "explicit_scheduled_capture_policy"
    else:
        deadline_applicability = "unavailable_missing_or_mixed_policy_evidence"
    coverage = Counter()
    metrics = defaultdict(list)
    counts = Counter()
    indices = {}
    def index(channel, fields):
        key = (channel, fields)
        if key not in indices:
            result = defaultdict(list)
            for event in events[channel]:
                if numeric(event, *fields):
                    result[tuple(event[field] for field in fields)].append(event)
            indices[key] = result
        return indices[key]

    def unique(channel, fields, event, label):
        if not numeric(event, *fields):
            coverage[label + "_invalid_key"] += 1
            return None
        candidates = index(channel, fields).get(tuple(event[field] for field in fields), [])
        # Older logs omit session on hot-path events. Missing session never
        # resolves a collision. Explicit mismatches always fail the join.
        candidates = [candidate for candidate in candidates
                      if "session" not in event or "session" not in candidate or
                      candidate["session"] == event["session"]]
        if len(candidates) != 1:
            coverage[label + ("_missing" if not candidates else "_ambiguous")] += 1
            return None
        return candidates[0]

    capture_times = [event["arrival"] for channel in
                     ("capture-ingress-sample", "capture-read-sample", "capture-graph-sample", "capture-present-sample")
                     for event in events[channel] if numeric(event, "arrival") and event["arrival"] > 0]
    host_times = capture_times + [event["arrival"] for event in events["pacing-sample"]
                                 if numeric(event, "arrival") and event["arrival"] > 0]
    origin = start_host_100ns if start_host_100ns is not None else min(host_times, default=0)
    start = origin + round(warmup_seconds * 10_000_000)
    end = start + round(duration_seconds * 10_000_000) if duration_seconds is not None else None
    def selected(event, field="arrival"):
        return numeric(event, field) and event[field] >= start and (end is None or event[field] < end)

    def span(label, begin, finish):
        if not isinstance(begin, (int, float)) or not isinstance(finish, (int, float)) or begin <= 0 or finish <= 0:
            coverage[label + "_unavailable"] += 1
        elif finish < begin:
            coverage[label + "_negative_rejected"] += 1
        else:
            metrics[label].append((finish - begin) / 10_000)

    ingress_key = ("source", "arrival")
    graph_key = ("source", "epoch", "revision", "arrival")
    gpu_key = ("source", "epoch", "revision")
    selected_graphs = []
    ingress_groups = defaultdict(list)
    for event in events["capture-ingress-sample"]:
        if selected(event):
            counts["ingress_records"] += 1
            span("callback_copy_lock_ms", event.get("arrival"), event.get("copied"))
            ingress_groups[event.get("session")].append(event["arrival"])
    for times in ingress_groups.values():
        times.sort()
        for first, second in zip(times, times[1:]):
            span("observed_callback_interval_ms", first, second)
    for event in events["capture-graph-sample"]:
        if not selected(event):
            continue
        counts["graph_records"] += 1
        selected_graphs.append(event)
        span("graph_cpu_submission_ms", event.get("start"), event.get("submitted"))
        if numeric(event, "slotWaitMs") and event["slotWaitMs"] >= 0:
            metrics["graph_slot_wait_ms"].append(event["slotWaitMs"])
        ingress = unique("capture-ingress-sample", ingress_key, event, "graph_ingress")
        read = unique("capture-read-sample", ingress_key, event, "graph_read")
        if ingress and read:
            span("mailbox_after_copy_ms", ingress.get("copied"), read.get("read"))
        if read:
            span("read_to_graph_ms", read.get("read"), event.get("start"))

    interval_groups = defaultdict(list)
    matched_pacing = set()
    for event in events["capture-present-sample"]:
        if not selected(event, "end") or not numeric(event, "generated", "begin", "end"):
            continue
        kind = "generated" if event["generated"] else "real"
        counts[kind + "_present_records"] += 1
        span(kind + "_b_callback_to_present_return_ms", event.get("arrival"), event.get("end"))
        span(kind + "_present_call_ms", event.get("begin"), event.get("end"))
        span(kind + "_b_callback_to_ready_observed_ms", event.get("arrival"), event.get("ready"))
        span(kind + "_ready_observed_to_present_begin_ms", event.get("ready"), event.get("begin"))
        if kind == "generated":
            span("generated_a_callback_to_present_return_ms", event.get("arrivalA"), event.get("end"))
            span("generated_ab_callback_gap_ms", event.get("arrivalA"), event.get("arrival"))
        graph = unique("capture-graph-sample", graph_key, event, "present_graph")
        if graph:
            span(kind + "_submit_to_ready_observed_ms", graph.get("submitted"), event.get("ready"))
        pacing = unique("pacing-sample", ("arrival", "begin", "generated"), event, "present_pacing")
        if pacing:
            matched_pacing.add(pacing["line"])
        # Split discontinuous histories. An arrival regression is harmless after
        # sorting but repeated identities cannot be used to guess GPU attribution.
        group = (event.get("session"), event.get("revision"), event.get("epoch"))
        interval_groups[(group, "all")].append(event["end"])
        interval_groups[(group, kind)].append(event["end"])

    for (_, kind), times in interval_groups.items():
        times.sort()
        for first, second in zip(times, times[1:]):
            span(kind + "_present_interval_ms", first, second)
            if kind == "all" and target_fps:
                counts["intervals_above_1_5_target"] += second - first > 15_000_000 / target_fps
                counts["intervals_below_0_5_target"] += second - first < 5_000_000 / target_fps
    for event in events["pacing-sample"]:
        if selected(event, "end"):
            if numeric(event, "queue"):
                metrics["observed_scheduler_queue_depth"].append(event["queue"])
            if numeric(event, "lateMs"):
                metrics["raw_logged_deadline_deviation_ms"].append(event["lateMs"])
                if deadline_applicability == "explicit_scheduled_capture_policy":
                    metrics["scheduled_deadline_deviation_ms"].append(event["lateMs"])
                    counts["observed_present_after_deadline"] += event["lateMs"] > 0
            if event["line"] not in matched_pacing:
                coverage["pacing_without_capture_present_match"] += 1

    selected_graph_lines = {event["line"] for event in selected_graphs}
    matched_gpu_graph_lines = set()
    for event in events["gpu-timestamp"]:
        event = dict(event, source=event.get("frame"))
        graph = unique("capture-graph-sample", gpu_key, event, "gpu_graph")
        if not graph or graph["line"] not in selected_graph_lines:
            continue
        if not numeric(event, "begin", "end", "frequency", "stage") or event["frequency"] <= 0 or event["end"] < event["begin"]:
            coverage["gpu_invalid_duration"] += 1
            continue
        stage = event["stage"]
        label = GPU_STAGES[stage] if isinstance(stage, int) and 0 <= stage < len(GPU_STAGES) else "unknown_" + str(stage)
        metrics["gpu_" + label + "_ms"].append((event["end"] - event["begin"]) * 1000 / event["frequency"])
        counts["gpu_matched_records"] += 1
        matched_gpu_graph_lines.add(graph["line"])

    formats = sorted({(event["width"], event["height"], event["format"])
                      for event in events["capture-read-sample"]
                      if selected(event) and numeric(event, "width", "height", "format")})
    # These records have no monotonic timestamp, so retain snapshots with line
    # numbers rather than pretending they measure the chosen warmup window.
    snapshot_channels = ("frame-flow", "fg-drops", "live-fg-admission", "nr-reuse", "content-dedup", "live-anchor", "player-timing", "frame-trace", "capture-timeline")
    snapshots = {channel: events[channel] for channel in snapshot_channels if events[channel]}
    return {
        "schema_version": 1, "name": name,
        "basis": "software callback-to-Present return; GPU stage durations use their own frequency",
        "window": {"start_host_100ns": start if host_times or start_host_100ns is not None else None,
                   "end_host_100ns_exclusive": end, "warmup_seconds": warmup_seconds,
                   "selection": "Ingress, read, graph and joined GPU records use callback arrival; presentation and pacing records use Present return"},
        "counts": dict(counts), "metrics": {key: distribution(value) for key, value in sorted(metrics.items())},
        "coverage": {"parsed_records": {key: len(value) for key, value in sorted(events.items()) if value},
                     "join_issues": dict(coverage), "observed_formats": formats,
                     "gpu_graphs_in_window": len(selected_graphs),
                     "graphs_with_any_gpu_stage": len(matched_gpu_graph_lines),
                     "graphs_without_gpu_stage": len(selected_graphs) - len(matched_gpu_graph_lines),
                     "timestamped_capture_records_available": bool(capture_times),
                     "timestamped_host_records_available": bool(host_times),
                     "deadline_observation_applicability": deadline_applicability},
        "unwindowed_snapshots": snapshots,
        "limitations": [
            "Controller, HDMI, USB pre-callback delay, scanout and panel response are unmeasured.",
            "GPU readiness is a CPU observation and can overestimate GPU completion time.",
            "GPU stage durations can nest or overlap. They must not be summed into total processing time.",
            "Missing verbose records and query drops remain unknown. Event counts do not establish complete coverage.",
            "Session is absent from older hot-path records. Ambiguous identity joins are rejected, including GPU joins across repeated identities.",
            "Each input must contain one continuous source session. Multiple observed session IDs are rejected; missing session markers cannot prove continuity. Split at stop, reopen and source switches as well as process boundaries.",
            "Unwindowed snapshots have no host timestamp and are not warmup-filtered or converted to window counter deltas.",
            "Raw logged lateMs is not a deadline miss without explicit consistent scheduling evidence. Capture-ready no-FG has no active presentation deadline; its stale timeline difference is retained only for audit.",
            "All-present intervals use capture-present records. Provider-owned XeSS generated presents require provider telemetry.",
            "Verbose text logging formats messages and takes the logger mutex. Compare logging-on and logging-off runs for overhead.",
        ],
    }


def markdown(results):
    lines = ["# Console capture software timing", "", "All values below are observed software timings. External controller-to-photon latency remains unmeasured.", ""]
    for result in results:
        lines += ["## " + result["name"], "", "| Metric | Samples | Median | p95 | p99 |", "|---|---:|---:|---:|---:|"]
        for key, metric in result["metrics"].items():
            lines.append(f"| {key} | {metric['count']} | {metric['p50']:.3f} | {metric['p95']:.3f} | {metric['p99']:.3f} |")
        if not result["metrics"]:
            lines.append("| No timestamped measurements | 0 | — | — | — |")
        lines += ["", "Coverage and counts", "", "```json", json.dumps({"counts": result["counts"], "coverage": result["coverage"]}, indent=2), "```", ""]
    lines += ["## Interpretation limits", ""] + ["- " + item for item in results[0]["limitations"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=10)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--start-host-100ns", type=int)
    parser.add_argument("--target-fps", type=float)
    args = parser.parse_args()
    for name in ("warmup_seconds", "duration_seconds", "target_fps"):
        value = getattr(args, name)
        if value is not None and (not math.isfinite(value) or value < 0 or (name != "warmup_seconds" and value == 0)):
            parser.error(name + " must be finite and " + ("nonnegative" if name == "warmup_seconds" else "positive"))
    results = []
    for path in args.logs:
        with path.open(encoding="utf-8-sig", errors="replace") as source:
            try:
                results.append(analyze(source, str(path.resolve()), args.warmup_seconds,
                                       args.duration_seconds, args.start_host_100ns, args.target_fps))
            except ValueError as error:
                parser.error(str(path) + ': ' + str(error))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "console-capture.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "console-capture.md").write_text(markdown(results), encoding="utf-8")
    print(json.dumps({"runs": len(results), "output": str(args.output_dir.resolve()),
                      "measured_runs": sum(bool(result["metrics"]) for result in results)}))


if __name__ == "__main__":
    main()
