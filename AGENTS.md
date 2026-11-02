# AGENTS.md

Guidance for Codex (and any agent that reads AGENTS.md) working in this repository.
`AGENTS.md` (Codex) and `CLAUDE.md` (Claude Code) carry the same
project facts below their intro; when you change a fact, change it in both. `GEMINI.md`
(Antigravity CLI) holds only Antigravity notes, because Antigravity also loads `AGENTS.md`.

The slash commands in `commands/` and the `ui-explorer` subagent in `agents/` are written for
Claude Code; Codex does not load them. Run the engines directly instead (`scripts/fast_ui.py`,
`scripts/fast_device.py`, or the launchers in `~/.local/bin`).
`skills/fast-ios-device-test/SKILL.md` is a standard Agent Skill: Codex picks it up when it is
linked into `~/.codex/skills/` (see README, "Use with Codex or Antigravity CLI"); otherwise read
it directly for how a flow is written. Where it mentions a subagent, do the steps yourself.
`install.sh` only installs into `~/.claude`.

## Project overview

`fast-ios-device-test` — fast iOS UI-flow verification for AI agents. It ships as the npm package
`fast-ios-device-test` (`npx fast-ios-device-test` installs it), plugins for Claude Code, Codex and
Antigravity, a Gemini CLI extension, and a release zip. macOS only; needs Xcode 26 or 27.

- `/fastSimulatorTest` drives an app on Simulator through a JSON flow (project-managed AXe is
  pinned in `vendor/tools.json` and installed under `~/.local/share/axe`),
  including iPhone Duo outer/inner displays and Device Hub poses on Xcode 27.1.
  Agents use the `duo` action for in-flow display changes and `--duo-pose` rows for
  one-framebuffer-per-pose recordings; they never drive Device Hub directly.
- `/fastDeviceTest` runs the same flows on a physical iPhone through a cached, auto-signed
  XCUITest runner (`device-runner/`), including Settings, Shortcuts and SpringBoard.
- `/fastUIReview` builds contact sheets from recorded runs. Other launchers: `fastUIMap`,
  `fastEvidenceSheet`, `fastUIClean`, `fastUIReport`, and `fastUITest` (legacy alias of
  `fastSimulatorTest`).

User-facing docs: `README.md` (English), `GUIDE.md` (Vietnamese, for testers), `SETUP.md`
(step-by-step setup an agent can follow), `CHANGELOG.md`.

## Repository structure

| Path | What |
|---|---|
| `scripts/fast_ui.py` | Simulator flow engine (`--record`, `--session`) |
| `scripts/tool_manager.py` | Installs or updates pinned AXe and baguette; stdlib only |
| `scripts/fast_device.py` | Physical-iPhone engine |
| `device-runner/` | XCUITest runner app. The `.xcodeproj` is committed; after editing `project.yml` run `cd device-runner && xcodegen generate` |
| `scripts/fast_guard.py` | Checks `do` requests (destructive steps, shapes) for both engines |
| `scripts/fast_media.py` | Video re-encode, one-final-clip rule |
| `scripts/fast_evidence.py`, `scripts/fast_evidence_sheet.py` | PR evidence folder on the Desktop, captioned sheet |
| `scripts/fast_ui_map.py`, `scripts/fast_ui_clean.py`, `scripts/fast_ui_report.py`, `scripts/fast_ui_review.py` | `fastUIMap`, `fastUIClean`, `fastUIReport`, `fastUIReview` |
| `scripts/test_*.py` | Unit tests, one file per module |
| `scripts/runner_logic_checks.swift` | Pure-logic checks for the runner, compiled by `test_fast_ui.RunnerLogicTests` (skipped without `swiftc`) |
| `scripts/shims/swiftlint` | No-op SwiftLint used to skip linting in test builds |
| `scripts/fastUnitTest`, `scripts/fast_device_test.sh`, `scripts/fastUnitTest.command.md.disabled` | Experimental on-device XCTest runner; not installed as a command |
| `bin/` | Repo-local symlinks to `scripts/` for the plugin install. `install.sh` does not use them: it links `scripts/*.py` into `~/.local/bin` itself |
| `skills/fast-ios-device-test/` | The skill (`SKILL.md` + `references/device.md`, `review.md`, `usage.md`): how an agent *uses* the tool |
| `commands/` | Slash commands `fastSimulatorTest`, `fastDeviceTest`, `fastUIReview` |
| `agents/ui-explorer.md` | Haiku subagent for long step-by-step searches (experimental) |
| `install.sh` | Installer: copy/link/check/uninstall plus pinned-tool install/update flags |
| `npm/install.js` | `npx` entry: install, clean, package update and managed-tool updates; refuses `--link` |
| `scripts/fast_update.py` | Installed/latest npm and pinned/installed/latest tool status; daily caches respect `FAST_IOS_NO_UPDATE_CHECK=1` |
| `.claude-plugin/` | Plugin + marketplace manifests |
| `plugin.json`, `.agents/plugins/` | Portable Codex plugin manifest + repo marketplace catalog |
| `.antigravity-plugin/`, `gemini-extension.json` | Antigravity plugin manifest + Gemini CLI extension manifest |
| `assets/fast-ios-device-test.png` | Shared Codex/Antigravity marketplace icon |
| `vendor/` | `tools.json` pins AXe + baguette; only AXe's smaller archive is vendored; licences included |
| `release.sh`, `make-zip.sh`, `.github/workflows/` | Release, zip, npm publish, upstream sync, managed-tool update PR |
| `scripts/package_marketplaces.py` | Clean Codex, Antigravity and Gemini CLI marketplace ZIPs under `build/plugin-packages/` |

## Commands

Run each in a subshell so the working directory does not change between commands.

```bash
# Tests — must pass before any commit (same set release.sh runs)
(cd scripts && python3 -m unittest test_fast_ui test_fast_media test_fast_ui_map test_fast_guard test_fast_ui_clean test_install test_fast_update)

# Extra tests that need Pillow (python3 -m pip install --user pillow)
(cd scripts && python3 -m unittest test_fast_evidence test_fast_evidence_sheet test_fast_ui_review)

# Provider package inventory and version checks
(cd scripts && python3 -m unittest test_package_marketplaces)

# Build clean provider ZIPs; validate the Antigravity staging folder with agy
python3 scripts/package_marketplaces.py
agy plugin validate --strict build/plugin-packages/stage/antigravity

# Install from this clone for local testing, then verify (last line must be CHECK OK)
./install.sh --link && ./install.sh --check

# Build the release zip next to the repo folder
./make-zip.sh
```

`install.sh` treats any unknown argument as a plain install: `./install.sh clean` or
`./install.sh --help` **copies** the clone over `~/.local/share/fast-ios-device-test` and re-points
the user's `~/.claude` and `~/.local/bin` links away from a `--link` clone. Read its source
instead of probing it. Only run it with a documented flag (`--link`, `--check`, `--install-tools`,
per-tool install/update flags, `--uninstall`) or no flag. To test the installer without
touching the user's setup, point it elsewhere with `FAST_IOS_INSTALL_DIR`, `FAST_IOS_BIN_DIR`,
`FAST_IOS_AXE_DIR`, `FAST_IOS_BAGUETTE_DIR`, `CLAUDE_SKILLS_DIR`, `CLAUDE_COMMANDS_DIR`, `CLAUDE_AGENTS_DIR`, `CODEX_HOME`,
`CODEX_SKILLS_DIR`, `CODEX_PLUGIN_CACHE` and `ANTIGRAVITY_SKILLS_DIR` (`scripts/test_install.py`
does this). The installer never creates a Codex or Antigravity skill link; it re-points one left
dangling, removes one into the copy it uninstalls, and `--check` fails on a broken one.

After `./install.sh --link`, edits to `scripts/`, `skills/`, `commands/` and `agents/` take effect at once.

## Conventions

- Python 3 standard library only in the engines; Pillow is optional (video review, evidence
  sheets) and must degrade gracefully when missing.
- Any behaviour change gets a test in the matching `scripts/test_*.py`.
- Keep the docs in step with the code: when a command, flag or action changes, update
  `skills/fast-ios-device-test/` (what agents read), `README.md`, and `GUIDE.md`/`SETUP.md` when
  they cover it. When commands change, also update the descriptions in `.claude-plugin/`.
- A new launcher needs a `link` line and a `chmod` entry in `install.sh`, a `bin/` symlink, and
  its files covered by `package.json` `files` (the npm package ships only what is listed there).
- Write every user-visible change under `## Unreleased` at the top of `CHANGELOG.md` (add that
  heading under `# Changelog` if it is missing; `release.sh` refuses to run without it).
- Do not edit `.github/upstream-sha` by hand. When `UPSTREAM_REPO` is set, the sync-upstream
  workflow commits straight to `main` every 6 hours, so rebase a branch on `main` before merging.

## Git and releases

- Work on a branch and open a PR. Never push to `main`, tag, or publish unless the maintainer
  explicitly asks.
- Releases: `./release.sh patch|minor|major|X.Y.Z` from a clean, up-to-date `main`. It turns
  `## Unreleased` into the version heading, bumps `package.json` and every provider plugin manifest,
  runs the tests, commits, tags `vX.Y.Z` and pushes. The tag triggers
  `.github/workflows/publish.yml` (npm Trusted Publisher + GitHub release with the zip).
  Do not bump versions by hand.
