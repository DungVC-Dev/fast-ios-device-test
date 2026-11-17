#!/usr/bin/env python3
"""Print which Amplitude key a built app sends to, and refuse a production key.

Reads AMPLITUDE_API_KEY from the .app's Info.plist (the value xcconfig baked in for that scheme) and
compares it with every *Prod*.xcconfig in the project. Exit 2 = production key: do not run tests.
"""

from __future__ import annotations

import argparse
import plistlib
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="built .app")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--key-name", default="AMPLITUDE_API_KEY")
    args = parser.parse_args()
    info = plistlib.loads((args.app.expanduser() / "Info.plist").read_bytes())
    key = str(info.get(args.key_name, "")).strip()
    production = set()
    for config in args.project_root.expanduser().rglob("*.xcconfig"):
        if "prod" in config.name.lower():
            match = re.search(rf"^\s*{args.key_name}\s*=\s*(\S+)", config.read_text(), re.M)
            if match:
                production.add(match.group(1))
    if not key:
        print(f"KEY none: {args.key_name} is empty in {args.app.name}; the SDK sends nothing")
        return 1
    if key in production:
        print(f"KEY production {key[:4]}…: refusing to test against production data")
        return 2
    print(f"KEY ok {key[:4]}… (not a production key)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
