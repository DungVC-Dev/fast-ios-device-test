#!/usr/bin/env bash
# Cut a release: ./release.sh patch|minor|major|X.Y.Z
# Turns CHANGELOG.md's "## Unreleased" into "## X.Y.Z — <date>", sets the version in package.json
# and every provider manifest, runs the tests, commits, tags vX.Y.Z and pushes. The tag starts
# .github/workflows/publish.yml, which publishes to npm and creates the GitHub release with the zip.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

bump="${1:-}"
[[ -n "$bump" ]] || { echo "usage: ./release.sh patch|minor|major|X.Y.Z"; exit 2; }
[[ "$(git branch --show-current)" == "main" ]] || { echo "error: release from main"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "error: commit or stash your changes first"; exit 1; }
git fetch -q origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || { echo "error: main differs from origin/main; pull or push first"; exit 1; }

current="$(python3 -c "import json; print(json.load(open('package.json'))['version'])")"
version="$(python3 - "$current" "$bump" <<'EOF'
import re, sys
current, bump = sys.argv[1], sys.argv[2]
major, minor, patch = map(int, current.split("."))
if re.fullmatch(r"\d+\.\d+\.\d+", bump):
    print(bump)
else:
    print({"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[bump])
EOF
)" || { echo "error: give patch, minor, major or X.Y.Z"; exit 2; }
git rev-parse -q --verify "refs/tags/v$version" >/dev/null && { echo "error: v$version already exists"; exit 1; }
grep -q '^## Unreleased' CHANGELOG.md || {
    echo "error: CHANGELOG.md has no '## Unreleased' section; write what changed under it first"; exit 1; }

python3 - "$version" <<'EOF'
import datetime, json, pathlib, sys
version = sys.argv[1]
for name in (
    "package.json",
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".antigravity-plugin/plugin.json",
    "gemini-extension.json",
):
    path = pathlib.Path(name)
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
log = pathlib.Path("CHANGELOG.md")
log.write_text(log.read_text().replace("## Unreleased", f"## {version} — {datetime.date.today()}", 1))
EOF

if test_output="$(cd scripts && python3 -m unittest discover -p 'test_*.py' 2>&1)"; then
    tests_run="$(printf '%s\n' "$test_output" | sed -n 's/^Ran \([0-9][0-9]*\) tests.*/\1/p' | tail -1)"
    echo "tests: ${tests_run:-unknown} passed"
else
    git checkout -- package.json plugin.json .claude-plugin/plugin.json .antigravity-plugin/plugin.json gemini-extension.json CHANGELOG.md
    printf '%s\n' "$test_output"
    echo "error: tests fail (cd scripts && python3 -m unittest discover -p 'test_*.py'); nothing released"
    exit 1
fi

git commit -qam "release $version"
git tag "v$version"
git push -q origin main "v$version"
echo "released v$version: GitHub Actions publishes it to npm and creates the release"
echo "watch: gh run watch -R $(git remote get-url origin | sed -E 's#.*github.com[:/]##; s#\.git$##') \$(gh run list -w publish.yml -L 1 --json databaseId -q '.[0].databaseId')"
