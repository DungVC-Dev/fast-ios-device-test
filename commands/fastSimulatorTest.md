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
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastSimulatorTest" <flow.json> [--reuse-app|--build-only|--record|--session <name>|--duo-pose <pose>]
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastSimulatorTest" start <draft.json> | do '<action json>' | labels | save <flow.json>
```

Exploring or checking one screen step by step → `fastSimulatorTest do '<action or array>' --simulator <udid>`
(the skill's "Step by step"). A new screen to turn into a flow: `start` + `do` step by step + `save`,
not repeated full runs with `dump`.

One requested behavior → one flow, written and run at once (no extra cases or variants the user
did not ask for). The user listed several flows: up to about 5 on one simulator →
`--build-only` once, then run them here with `--reuse-app`; more flows or 2+ simulators →
the skill's fan-out, collated with `fastUIReport`. "quay"/"record" → `--record`.

At the end of the work, `fastSimulatorTest shutdown` (every booted simulator, or `--simulator <udid>`;
spare one Xcode is running the app on).

Return the PASS/FAIL lines (a flow × simulator table when fanned out) and one concise cause
per FAIL, with artifact links. Remove temporary flows; never edit the engine for one screen.
