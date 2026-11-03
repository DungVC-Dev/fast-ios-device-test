---
description: Run a UI test on Simulator via a JSON flow (one screen, a system app, iPhone Duo poses, or a matrix)
argument-hint: <screen, flow, or list of cases; optionally which simulators>
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, Agent
---

Test only this requested UI behavior: `$ARGUMENTS`.

Read and follow the `fast-ios-device-test` skill
(`~/.claude/skills/fast-ios-device-test/SKILL.md`, or `skills/fast-ios-device-test/SKILL.md`
in this plugin): flow format, selectors, timing rules, the two-rerun cap and when to fan out.
The engine is:

```bash
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastSimulatorTest" <flow.json> [--reuse-app|--build-only|--record|--session <name>|--duo-pose <pose>|--duo-orientation portrait|landscape]
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastSimulatorTest" start <draft.json> | do '<action json>' | labels | save <flow.json>
```

Exploring or checking one screen step by step → `fastSimulatorTest do '<action or array>' --simulator <udid-or-name>`
(the skill's "Step by step"). A new screen to turn into a flow: `start` + `do` step by step + `save`,
not repeated full runs with `dump`.

iPhone Duo requires Xcode 27.1. Use `"simulator":"iPhone Duo"`; the engine selects that Xcode,
boots the device and opens Device Hub. In one flow, switch and capture displays with:

```json
[{"type":"duo","pose":"closed","orientation":"landscape"},{"type":"screenshot","name":"outer.png"},
 {"type":"duo","pose":"open"},{"type":"screenshot","name":"inner.png"}]
```

The defaults are `closed` outer portrait, `open` flat inner landscape, `book` inner landscape
with a vertical fold, and `tabletop` inner portrait with a horizontal fold. `closed` and `open`
also accept the other orientation; use the action's `orientation`, `setup.duo_orientation`, or
`--duo-orientation`. `book+portrait` and `tabletop+landscape` are physically contradictory and
are refused. A non-default matrix row is named such as `@duo-closed-landscape`.
For a recorded pose matrix, run one row per `--duo-pose closed|open|book|tabletop`, all with the
same `--session` and `--record`: a video records one framebuffer, while a flow that switches poses
uses screenshots. An explicit screenshot/motion may set `"display":"outer|inner"`.

One requested behavior → one flow, written and run at once (no extra cases or variants the user
did not ask for). The user listed several flows: up to about 5 on one simulator →
`--build-only` once, then run them here with `--reuse-app`; more flows or 2+ simulators →
the skill's fan-out, collated with `fastUIReport`. "quay"/"record" → `--record`.

At the end of the work, `fastSimulatorTest shutdown` (every booted simulator, or `--simulator <udid-or-name>`;
spare one Xcode is running the app on).

Return the PASS/FAIL lines (a flow × simulator table when fanned out) and one concise cause
per FAIL, with artifact links. Remove temporary flows; never edit the engine for one screen.
