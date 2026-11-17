#!/usr/bin/env python3
"""Diff a tracking plan (events.json) against the app's Swift source, with no build and no UI.

Reads `eventName` / `parameters` switches of every TrackingFlowData-style enum and reports, per
planned event: found or missing, plus property keys the plan lists that the code never sends and
keys the code sends that the plan does not list. Runs in seconds; the model only reads the summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CASE = re.compile(r"^\s*case\s+(?:let\s+)?(.+?):\s*(.*)$")
NAME = re.compile(r"\.(\w+)")
KEY = re.compile(r'"([^"\n]{1,60})"\s*:')
RETURN_STRING = re.compile(r'return\s+"([^"]+)"')


def switch_body(text: str, var: str) -> str:
    start = text.find(f"var {var}")
    if start < 0:
        return ""
    depth, begun = 0, False
    for index in range(start, len(text)):
        if text[index] == "{":
            depth, begun = depth + 1, True
        elif text[index] == "}":
            depth -= 1
            if begun and depth == 0:
                return text[start:index]
    return text[start:]


def cases(body: str) -> list[tuple[list[str], str]]:
    blocks: list[tuple[list[str], str]] = []
    for line in body.splitlines():
        match = CASE.match(line)
        if match:
            blocks.append((NAME.findall(match.group(1)), match.group(2)))
        elif blocks:
            names, rest = blocks[-1]
            blocks[-1] = (names, rest + "\n" + line)
    return blocks


def scan(root: Path) -> tuple[dict[str, set[str]], dict[str, str], str]:
    events: dict[str, set[str]] = {}
    where: dict[str, str] = {}
    corpus = []
    for path in root.rglob("*.swift"):
        text = path.read_text(errors="ignore")
        corpus.append(text)
        if "var eventName" not in text:
            continue
        names = {}
        for case_names, rest in cases(switch_body(text, "eventName")):
            found = RETURN_STRING.search(rest)
            if found:
                for case in case_names:
                    names[case] = found.group(1)
        keys: dict[str, set[str]] = {}
        for case_names, rest in cases(switch_body(text, "parameters")):
            for case in case_names:
                keys.setdefault(case, set()).update(KEY.findall(rest))
        for case, event in names.items():
            events.setdefault(event, set()).update(keys.get(case, set()))
            where.setdefault(event, path.name)
    return events, where, "\n".join(corpus)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="events.json from tracking_plan.py")
    parser.add_argument("source", type=Path, help="app source root, e.g. MyApp/Sources")
    parser.add_argument("--out", type=Path, default=Path("static.json"))
    args = parser.parse_args()
    plan = json.loads(args.events.read_text())
    code, where, corpus = scan(args.source)
    rows = []
    for event in plan:
        name = event["name"]
        if name in code:
            sent = code[name]
            planned = set(event["properties"]) - {"app theme"}
            rows.append({
                "event": name, "kind": event["kind"], "status": "in_code", "file": where[name],
                "missing_keys": sorted(planned - sent), "extra_keys": sorted(sent - planned),
            })
        elif f'"{name}"' in corpus:
            rows.append({"event": name, "kind": event["kind"], "status": "literal_only"})
        elif event["kind"] == "sdk":
            rows.append({"event": name, "kind": "sdk", "status": "sdk_auto"})
        else:
            rows.append({"event": name, "kind": event["kind"], "status": "not_in_code"})
    planned_names = {e["name"] for e in plan}
    unplanned = sorted(set(code) - planned_names)
    args.out.write_text(json.dumps({"events": rows, "unplanned": unplanned}, indent=1, ensure_ascii=False) + "\n")

    client = [r for r in rows if r["kind"] != "backend"]
    count = lambda status: sum(r["status"] == status for r in client)
    mismatched = [r for r in client if r.get("missing_keys") or r.get("extra_keys")]
    print(f"STATIC client+sdk={len(client)} in_code={count('in_code')} literal_only={count('literal_only')} "
          f"sdk_auto={count('sdk_auto')} not_in_code={count('not_in_code')} key_mismatch={len(mismatched)} unplanned={len(unplanned)} out={args.out}")
    for row in client:
        if row["status"] == "not_in_code":
            print(f"  MISSING  {row['event']}")
    for row in mismatched:
        detail = []
        if row["missing_keys"]:
            detail.append(f"plan-only {row['missing_keys']}")
        if row["extra_keys"]:
            detail.append(f"code-only {row['extra_keys']}")
        print(f"  KEYS     {row['event']} ({row['file']}): {'; '.join(detail)}")
    for name in unplanned:
        print(f"  UNPLANNED {name} ({where[name]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
