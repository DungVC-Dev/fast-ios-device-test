#!/usr/bin/env python3
"""Turn an Amplitude tracking-plan workbook into a compact events.json the agent and matcher read.

The model never reads the workbook itself: this keeps a 90-event plan around 4k tokens.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("FAIL tracking_plan: openpyxl missing; install it with: python3 -m pip install --user openpyxl")

HEADERS = {
    "category": "category", "event name (display)": "name", "scope": "scope", "ingested name": "ingested",
    "source": "source", "trigger description": "trigger", "event properties": "properties",
    "user properties to set": "user_properties",
}


def kind(source: str) -> str:
    text = source.lower()
    if "backend" in text or "http api" in text:
        return "backend"
    if "amplitude sdk" in text:
        return "sdk"
    return "client"


def property_names(cell: str) -> list[str]:
    names = []
    for line in str(cell or "").splitlines():
        line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        # "name (note)", "name: note" and "name - note" give "name"; "sign-in method" stays whole.
        line = re.split(r"\s*[(:]|\s+[-–]", line)[0].strip()
        if line and len(line) < 60:
            names.append(line)
    return names


def struck(cell) -> bool:
    return bool(cell is not None and getattr(cell, "font", None) and cell.font.strike)


def load(path: Path, sheet: str) -> list[dict]:
    workbook = openpyxl.load_workbook(path)
    rows = list(workbook[sheet].iter_rows())
    header = {str(c.value).strip().lower(): i for i, c in enumerate(rows[0]) if c.value}
    columns = {key: header[title] for title, key in HEADERS.items() if title in header}
    events = []
    for row in rows[1:]:
        value = lambda key: row[columns[key]].value if key in columns and columns[key] < len(row) else None
        name, ingested = value("name"), value("ingested")
        if not name or not ingested or struck(row[columns["name"]]):
            continue
        events.append({
            "name": str(name).strip(),
            "category": str(value("category") or "").strip(),
            "kind": kind(str(value("source") or "")),
            "trigger": " ".join(str(value("trigger") or "").split())[:160],
            "properties": property_names(value("properties")),
        })
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet", default="Amplitude Events")
    parser.add_argument("--out", type=Path, default=Path("events.json"))
    args = parser.parse_args()
    events = load(args.workbook.expanduser(), args.sheet)
    args.out.write_text(json.dumps(events, indent=1, ensure_ascii=False) + "\n")
    by_kind = {k: sum(e["kind"] == k for e in events) for k in ("client", "sdk", "backend")}
    print(f"PLAN events={len(events)} {by_kind} properties={sum(len(e['properties']) for e in events)} out={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
