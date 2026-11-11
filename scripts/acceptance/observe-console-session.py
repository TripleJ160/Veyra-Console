"""Bounded, read-only PresentMon observation of an already-running Veyra.

Does not open the capture device, change settings, or stop the target process.
Raw timestamps and the continuous log prefix are preserved across resets.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def clock_sample():
    counter, frequency = ctypes.c_longlong(), ctypes.c_longlong()
    ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency))
    before = time.time_ns()
    ctypes.windll.kernel32.QueryPerformanceCounter(ctypes.byref(counter))
    after = time.time_ns()
    return dict(qpc=counter.value, frequency=frequency.value,
                utc_ns_midpoint=(before + after) // 2,
                bracket_ns=after - before)


def identity(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def powershell(code):
    return subprocess.check_output(
        ['powershell.exe', '-NoProfile', '-Command', code],
        text=True, encoding='utf-8-sig', errors='replace', timeout=30)


def snapshot_profile(source, destination):
    destination.mkdir()
    result = []
    for item in sorted(source.iterdir()):
        if item.is_file() and item.stat().st_size < 4 * 1024 * 1024:
            target = destination / item.name
            shutil.copyfile(item, target)
            result.append(identity(target))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--engine-log', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--presentmon', type=Path, required=True)
    parser.add_argument('--logs-only', action='store_true', help='Observe existing logs without ETW collection')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 120 or args.pid <= 0:
        parser.error('duration must be 5..120 seconds and pid must be positive')
    # Never reuse an evidence directory or stop an unrelated ETW session.
    args.output.mkdir(parents=True, exist_ok=False)
    raw = powershell(f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                     f"Get-CimInstance Win32_Process -Filter 'ProcessId={args.pid}' | "
                     "Select-Object ProcessId,ExecutablePath,CommandLine,CreationDate | ConvertTo-Json")
    process = json.loads(raw)
    if not process or Path(process['ExecutablePath']).name.lower() != 'veyra_qml_ui.exe':
        raise ValueError('Target must be an existing Veyra GUI process')
    prefix = args.engine_log.read_bytes()
    (args.output / 'engine-before.log').write_bytes(prefix)
    session = 'Veyra5090-' + uuid.uuid4().hex[:12]
    command = [str(args.presentmon), '--process_id', str(args.pid),
               '--output_file', str(args.output / 'presentmon.csv'),
               '--timed', str(args.seconds), '--terminate_after_timed',
               '--session_name', session, '--no_console_stats', '--qpc_time',
               '--no_track_input']
    manifest = dict(schema=1, label=args.label, status='starting',
                    collection='logs-only' if args.logs_only else 'presentmon-and-logs',
                    process=process, executable=identity(process['ExecutablePath']),
                    presentmon=identity(args.presentmon), command=None if args.logs_only else command,
                    profile_before=snapshot_profile(args.profile, args.output / 'profile-before'),
                    engine_log=str(args.engine_log), engine_start_offset=len(prefix),
                    clock_start=clock_sample(),
                    limitations=['Existing session; settings may change interactively.',
                                 'Uncontrolled source until user confirms the requested action.',
                                 ('No ETW collector was started.' if args.logs_only else
                                  'PresentMon tracing overhead is not subtracted.'),
                                 'ETW display timing is not optical controller latency.',
                                 'No per-frame lineage if verbose logging was disabled.'])
    manifest_path = args.output / 'manifest.json'
    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save()
    if args.logs_only:
        manifest.update(status='collecting', start_utc=datetime.now(timezone.utc).isoformat())
        save()
        print(json.dumps(dict(status='collecting', manifest=str(manifest_path),
                              collection='logs-only')), flush=True)
        time.sleep(args.seconds)
        code = 0
    else:
        with (args.output / 'presentmon-console.log').open('wb') as stream:
            collector = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            manifest.update(status='collecting', collector_pid=collector.pid,
                            start_utc=datetime.now(timezone.utc).isoformat())
            save()
            print(json.dumps(dict(status='collecting', manifest=str(manifest_path),
                                  collector_pid=collector.pid)), flush=True)
            try:
                code = collector.wait(timeout=args.seconds + 20)
            except subprocess.TimeoutExpired:
                # Stop only this task's collector, never Veyra or another ETW session.
                collector.terminate()
                collector.wait(timeout=10)
                code = -1
    manifest.update(clock_end=clock_sample(), collector_exit=code,
                    end_utc=datetime.now(timezone.utc).isoformat())
    final = args.engine_log.read_bytes()
    same_prefix = final.startswith(prefix)
    manifest['continuous_log_prefix_preserved'] = same_prefix
    (args.output / 'engine-observation.log').write_bytes(
        final[len(prefix):] if same_prefix else final)
    manifest['engine_end_offset'] = len(final)
    manifest['profile_after'] = snapshot_profile(args.profile, args.output / 'profile-after')
    manifest['status'] = 'completed' if code == 0 and same_prefix else 'incomplete'
    manifest['csv_exists'] = (args.output / 'presentmon.csv').is_file()
    if not args.logs_only and not manifest['csv_exists']:
        manifest['status'] = 'incomplete'
    save()
    print(json.dumps(dict(status=manifest['status'], exit=code,
                          manifest=str(manifest_path))), flush=True)
    return code or (0 if manifest['status'] == 'completed' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
