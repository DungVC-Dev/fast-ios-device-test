#!/usr/bin/env python3
"""Match captured analytics log lines against the tracking plan and print a compact verdict table.

Input: events.json (tracking_plan.py), or `-` to only list what fired, one or more run folders
or logs, and optionally an expectations file listing the events each journey must fire. A run
folder is searched for console.log (this tool's runs) and app.log (fastSimulatorTest /
fastDeviceTest `--app-log`). The model reads only the summary and
the non-PASS rows; payloads and screenshots stay on disk as evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LINE = re.compile(r'\[TRACKING\]\[Amplitude\] event=(.+?) params=(\[.*\])')
PAIR = re.compile(r'"((?:[^"\\]|\\.)*)":\s*("(?:[^"\\]|\\.)*"|[^,\]]+)')
# Added after the log line is printed (SDK enrichment plugins), so only Amplitude can prove them.
ENRICHED = {"app theme", "from background"}


def parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        return raw[1:-1].replace('\\"', '"')
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def read_events(paths: list[Path]) -> list[dict]:
    events = []
    for path in paths:
        logs = sorted([*path.rglob("console.log"), *path.rglob("app.log")]) if path.is_dir() else [path]
        for log in logs:
            for line in log.read_text(errors="ignore").splitlines():
                match = LINE.search(line.replace('\\"', '"'))
                if match:
                    params = {k: parse_value(v) for k, v in PAIR.findall(match.group(2))}
                    events.append({"event": match.group(1), "params": params, "run": log.parent.name})
    return events


def list_fired(captured: list[dict], out: Path) -> int:
    """No plan: one row per fired event in firing order of first appearance, with its count."""
    fired: dict[str, list[dict]] = {}
    for event in captured:
        fired.setdefault(event["event"], []).append(event)
    lines = ["| Event | Fired | Last payload |", "| --- | --- | --- |"]
    lines += [f"| {name} | {len(hits)}x | `{json.dumps(hits[-1]['params'], ensure_ascii=False)}` |"
              for name, hits in fired.items()]
    out.write_text("\n".join(lines) + "\n")
    print(f"MATCH captured={len(captured)} distinct={len(fired)} plan=none report={out}")
    for name, hits in fired.items():
        print(f"  FIRED     {name} x{len(hits)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", help="events.json, or - to list the fired events without a plan")
    parser.add_argument("logs", type=Path, nargs="+", help="run folders, console.log or app.log files")
    parser.add_argument("--expect", type=Path, help='JSON: [{"event": "...", "params": {...}, "once": true}]')
    parser.add_argument("--out", type=Path, default=Path("tracking-report.md"))
    args = parser.parse_args()
    if args.events == "-" and args.expect:
        print("MATCH error: --expect needs a plan (events.json), not -")
        return 2
    missing = [str(path) for path in args.logs if not path.exists()]
    if missing:
        print(f"MATCH error: no such run folder or log: {', '.join(missing)}")
        return 2
    captured = read_events(args.logs)
    if not captured:
        print("MATCH captured=0: no tracking lines in the logs; run with --app-log (fastSimulatorTest / "
              "fastDeviceTest) or setup.capture_console, and check that the build prints them")
        return 1
    if args.events == "-":
        return list_fired(captured, args.out)
    plan = {e["name"]: e for e in json.loads(Path(args.events).read_text())}
    fired = defaultdict(list)
    for event in captured:
        fired[event["event"]].append(event)

    rows = []
    expected = json.loads(args.expect.read_text()) if args.expect else [{"event": n} for n in fired]
    for item in expected:
        name, hits = item["event"], fired.get(item["event"], [])
        planned = set(plan.get(name, {}).get("properties", [])) - ENRICHED
        if not hits:
            rows.append((name, "MISSING", "not fired", ""))
            continue
        sent = set().union(*(set(h["params"]) for h in hits))
        problems = []
        if planned - sent:
            problems.append(f"missing keys {sorted(planned - sent)}")
        if name in plan and sent - planned - ENRICHED:
            problems.append(f"unplanned keys {sorted(sent - planned - ENRICHED)}")
        for key, want in (item.get("params") or {}).items():
            got = [h["params"].get(key) for h in hits]
            if want not in got:
                problems.append(f"{key}={got[-1]!r}, want {want!r}")
        if name not in plan:
            status = "UNPLANNED"
        elif problems:
            status = "FAIL"
        elif item.get("once") and len(hits) > 1:
            status, problems = "DUPLICATE", [f"fired {len(hits)}x"]
        else:
            status = "PASS"
        rows.append((name, status, "; ".join(problems), json.dumps(hits[-1]["params"], ensure_ascii=False)))
    if args.expect:
        listed = {item["event"] for item in expected}
        for name in sorted(set(fired) - listed):
            rows.append((name, "EXTRA" if name in plan else "UNPLANNED", f"fired {len(fired[name])}x", ""))

    counts = Counter(status for _, status, _, _ in rows)
    lines = ["| Event | Status | Detail | Last payload |", "| --- | --- | --- | --- |"]
    lines += [f"| {n} | {s} | {d} | `{p}` |" if p else f"| {n} | {s} | {d} | |" for n, s, d, p in rows]
    args.out.write_text("\n".join(lines) + "\n")
    print(f"MATCH captured={len(captured)} distinct={len(fired)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f" report={args.out}")
    for name, status, detail, _ in rows:
        if status != "PASS":
            print(f"  {status:9} {name}: {detail}")
    return 0 if not any(s in ("MISSING", "FAIL") for _, s, _, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
