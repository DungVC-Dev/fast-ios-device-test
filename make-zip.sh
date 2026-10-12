#!/usr/bin/env bash
# Build the shareable zip next to this folder: fast-ios-device-test-<version>.zip,
# without git history, caches, build output or Finder metadata.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="$(basename "$HERE")"
VERSION="$(python3 -c "import json; print(json.load(open('$HERE/.claude-plugin/plugin.json'))['version'])")"
OUT="$(dirname "$HERE")/$NAME-$VERSION.zip"

rm -f "$OUT"
(cd "$(dirname "$HERE")" && zip -rq "$OUT" "$NAME" \
    -x '*.DS_Store' -x '*__pycache__*' -x "$NAME/.git/*" -x "$NAME/.superpowers/*" -x "$NAME/build/*")
echo "$OUT ($(du -h "$OUT" | cut -f1))"
