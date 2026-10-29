# Evidence on the Desktop — design

Status: built in 1.7.0, 2026-10-29. Decisions changed while building are marked *(built)*.

## Why

Evidence for a pull request is today a separate step: after testing, the user asks the agent to
"export evidence", the agent writes a sheet spec, runs `fastEvidenceSheet`, copies clips into
`<repo>/build/evidence-<ticket>/bitbucket/`, and the user drags that folder to the Desktop to
pick files in the browser's upload dialog. After the PR merges they delete the Desktop copy.

That leaves two problems:

- Nothing ever deletes what stays in `<repo>/build/`: run folders of iPhone runs, evidence
  folders of merged tickets, and whatever the agent built next to them. One cleanup on
  2026-10-29 freed 80 GB; Xcode's Clean Build Folder and deleting DerivedData touch none of it.
- The export depends on the agent remembering a skill. When it forgets, or does it its own way,
  the light files the reviewer needs are missing and the heavy ones stay.

The tool should do the filing itself: every flow run that counts as evidence lands, light and
captioned, in one folder per ticket on the Desktop, and nothing of it stays in `build/`.

## Goals

- After a flow run on a ticket branch, the files to attach to the PR for that ticket are in
  `~/Desktop/<project> <ticket>/` with no extra request from the user.
- The folder shows the bug ("before") and the fix ("after") side by side when the agent marked a
  run as "before".
- Screenshots are combined into a captioned sheet; recordings are not combined, only compressed
  (the engines already shrink them to 960 px, ~1–2 MB) and copied.
- A sheet can be changed later without quality loss: replace a shot, reorder cells, fix a
  caption, then render again.
- A filed PASS run leaves only its few-KB `metrics.json` in `build/fast-ui` or
  `build/fast-device`, pruned after 3 days.
- Light enough to attach, sharp enough to read: a shot is readable at 2× zoom on a laptop.

Success means:

- On branch `feature/PRJ-12-paywall`, three PASS flow runs on a Simulator produce
  `~/Desktop/MyApp PRJ-12/PRJ-12.jpg` with three cells, plus `source/` holding three shot JPEGs
  and `sheet.json`; their run folders in `build/fast-ui/<task>/` hold only `metrics.json`.
- Running one of those flows again replaces that case's cell image, keeps its edited caption and
  its place in the sheet, and keeps the case's "before" cell.
- Editing `source/sheet.json` (order, label, caption, an `image` path) and running
  `fastEvidenceSheet "~/Desktop/MyApp PRJ-12/source/sheet.json"` re-renders the sheet from the
  stored shots with no visible loss.
- Sheet ≤ ~350 KB for seven phone shots, each stored shot ≤ ~150 KB, each clip ≤ ~2 MB.

## Non-goals

- Uploading to Bitbucket or any other host. The user attaches files by hand.
- Deleting the Desktop folder after the merge. The user does that.
- Combining clips into one video.
- Cleaning app builds (`derived_data`, e.g. `build/fast-ui-dd`): the next run reuses them.
- Test-suite results and the PR description: those stay with the agent (see "The agent's part").

## Anti-goals

- A failed run caused by a broken flow (a selector that never appeared) shown to a reviewer as
  "the bug".
- A re-run that silently drops the "before" shot or the agent's captions.
- Desktop clutter from exploration: step-by-step `do` requests never file anything.
- Private names, device names or UDIDs in this public repo's docs, tests or examples.

## Decisions already made

- Approach: the tool files evidence itself (chosen over "the skill tells the agent to do it",
  which depends on the agent remembering, and over "a flag the agent passes", which is not
  automatic).
- Every flow run that qualifies is filed; there is no separate export request.
- Destination is one folder per ticket on the Desktop. The user deletes it after the merge.
- Both "before" (bug) and "after" (fixed) shots go in.
- Raw run files are not kept in `build/` once filed.
- The team-specific PR description rules stay in a private skill, not in this repo.

## Approaches considered

| Approach | Trade-off | Outcome |
|---|---|---|
| A. The tool files every qualifying run | Works the same for every app and every agent session, testable; changes default behaviour of a public tool | **Chosen** |
| B. A skill tells the agent to export after each run | No tool change; depends on the agent remembering, which is how the 80 GB built up | Rejected |
| C. The tool gains `--evidence-dir`, the agent passes it | No change for other users; still depends on the agent | Rejected |

## Design

### When a run is filed

A flow run (both engines: `fastSimulatorTest <flow>`, `fastDeviceTest <flow>`) is filed when:

- it **passed**, or it is marked **before** (see below) and passed or failed **at or after its
  outcome step**;
- and evidence is not turned off (`FAST_EVIDENCE=0`, or `"evidence": false` in the flow).

Never filed: `do` requests, `--build-only`, a FAIL run not marked before, and a before run that
failed earlier than its outcome step (prepare, install, launch, or a navigation step).

**Outcome step.** A before run is usually the after flow run on the base build: it fails at the
`wait`/`expect` that looks for the fixed state, and the screen at that moment *is* the bug. A
broken flow fails earlier, on the way there. So an action may carry `"outcome": true`; without
one, the outcome step is the last action that is not a `screenshot`, `dump`, `motion` or
`pause` *(built: flows usually end with a screenshot after the check, which "the last action"
would have made unreachable)*. Both engines already report the failing step
as `"<NN>_<type>"`, so "at or after" is a comparison of `NN`. *(Our call: this keeps a broken
flow out of the PR without asking the agent to judge each failure.)*

### Ticket and folder

The folder is `<FAST_EVIDENCE_DIR>/<project> <ticket>/`; `FAST_EVIDENCE_DIR` defaults to
`~/Desktop`. *(Builder: on by default is our call — the point is that nobody has to ask.)*

- `<project>`, first match wins: the flow's `evidence.project`; `FAST_EVIDENCE_PROJECT`; the
  folder name of the main checkout of `project_root`'s git repo (the parent of
  `git rev-parse --path-format=absolute --git-common-dir`), so a `git worktree` of the base
  branch files into the same folder as the ticket; the `project_root` folder name (e.g. `MyApp`).
  A plain copy without `.git` (`cp`, `git archive`) needs the overrides; the agent's skill says so.
- `<ticket>`, first match wins:
  1. the flow's `evidence.ticket`;
  2. the `FAST_EVIDENCE_TICKET` environment variable;
  3. ticket keys in the current git branch of `project_root` (`[A-Z][A-Z0-9]+-\d+`, upper
     case only — *(built)* a lower-case `fix-crash-2` is not a ticket; several keys joined with
     a space, e.g. `feature/PRJ-12_PRJ-13-x` → `PRJ-12 PRJ-13`);
  4. the branch name with `/` replaced by `-`;
  5. a detached HEAD: `<YYYY-MM-DD>`;
  6. *(built)* no git repo and no ticket given: the run is not filed, so throwaway flows in a
     temp folder (smoke tests, scratch runs) never reach the Desktop.

(1) and (2) exist for "before" runs built from a copy of the base branch, whose own branch is
not the ticket's.

### Marking a run as "before", labels and captions

The flow JSON gains an optional `evidence` object; everything in it is optional:

```json
"evidence": {
  "role": "before",
  "case": "gating-off",
  "label": "G2 · Off",
  "caption": "reopen: false → no paywall",
  "shots": ["1-paywall", "main"],
  "sheet": "gating",
  "ticket": "PRJ-12"
}
```

- `role`: `"after"` (default) or `"before"`. `--before` on the command line sets it too.
- `case`: what pairs a before run with its after run. Default: the task name including its
  variant suffix (`flow@dark`) plus the device or simulator name, so a matrix files one case per
  device and variant.
- `label` default: `<task> · <device>`; `caption` default: the flow's `expect`.
- `shots`: which named screenshots to file, in order. Default: every screenshot the run saved,
  in step order; a FAIL "before" run adds its `failure.png`.
- `sheet`: which sheet in the folder; default: the ticket (`PRJ-12.jpg`).

### Folder layout

```
~/Desktop/MyApp PRJ-12/
  PRJ-12.jpg                 sheet(s): what gets attached
  gating-off.mp4             clip of the after run, named after the case
  gating-off-before.mp4      clip of the before run
  PR-description.md          written by the agent, not the tool
  source/
    sheet.json               one spec per sheet (sheet-<name>.json when several)
    shots/<case>/<role>-<shot>.jpg
```

Only attachable files sit at the top so the upload dialog shows nothing else. Folder and file
names must be safe for a browser upload dialog (no `/`, `:`).

### Shots and the sheet

- Each filed screenshot is stored as JPEG quality 80, 720 px wide (2× the 360 px sheet cell),
  ~80–150 KB.
- `sheet.json` uses the existing `fastEvidenceSheet` spec with `image` cells pointing into
  `source/shots/`, so the existing renderer and its edit-and-render loop work unchanged.
- Filing a run updates `sheet.json`, then renders the sheet:
  - an existing cell (same case, role, shot) gets the new image only; its label, caption and
    position stay as they are, since the agent may have edited them;
  - a new case's cells are appended; a before cell is inserted right before the first after
    cell of the same case, and vice versa;
  - cells the agent removed from `sheet.json` are not re-added by a re-run of that case.
    *(Builder: how removals are remembered is yours, e.g. a `"removed"` list in the spec.)*
- Clips: the run's published clip (`final[-<session>].mp4`, or a before run's `run.mp4`) is
  copied as `<case>.mp4` / `<case>-before.mp4`, replacing an older one.

### What is deleted from `build/`

Only when the artifacts root is the default (`<project_root>/build/fast-ui` or
`build/fast-device`). A root set with `--artifacts-root` / `FAST_UI_ROOT` was chosen to keep
runs, so filing copies from it and deletes nothing there.

- After filing a PASS run: every file of its run folder except `metrics.json`, and its
  task-level clip. `metrics.json` (a few KB) stays with its `video` rewritten to the filed clip
  on the Desktop, so `fastUIReport` and `fastUIReview`, which glob `<root>/*/*/metrics.json` and
  follow `video`, keep working unchanged, attempt counts (`×N`) and `--since` included.
- A FAIL run (filed as before or not) keeps its whole folder for debugging.
- Run folders, what is left of them included, are pruned after `FAST_UI_KEEP_DAYS` (3) days. The
  iPhone engine gains the same prune the Simulator engine already has (`prune_artifacts` in
  `fast_ui.py`).
- `derived_data` app builds are not touched.

### Output

The PASS/FAIL line gains `evidence=file://…/<folder>` when the run was filed, so the agent can
link it.

### Concurrency

Several agent sessions can run flows for the same ticket at once. Updating `sheet.json`,
replacing shots and rendering happen under one lock per evidence folder, as the screen map
already does with `flock`.

## The agent's part (skills)

- **This repo's skill** (`skills/fast-ios-device-test`): a short "Evidence" section: where it
  lands, how to mark a before run, write `evidence.label`/`caption` in flows meant for a PR,
  how to edit and re-render a sheet, `FAST_EVIDENCE=0` for throwaway runs.
- **A team's private PR skill** (outside this repo): keeps the PR description, the test-suite
  summary against the base branch, and the choice of cases; writes `PR-description.md` into the
  Desktop folder; deletes the base/head app builds it made for the test comparison as soon as
  the comparison is done.

## Constraints

- Public repo: examples use `MyApp`, `PRJ-12`; no real device names, UDIDs or team names.
- Python 3 standard library plus Pillow, which `fastEvidenceSheet` already needs; no ffmpeg.
- Both engines behave the same; tests follow the existing `scripts/test_*.py` pattern.
- Filing must not turn a PASS into a FAIL: a filing error is reported on the line
  (`evidence_error=…`) and the run's own status and exit code stand.

## Left to the builder

- Module layout (e.g. a new `scripts/fast_evidence.py` used by both engines).
- Exact JSON field names beyond those above, the lock, removal tracking.
- Version number and CHANGELOG wording.
