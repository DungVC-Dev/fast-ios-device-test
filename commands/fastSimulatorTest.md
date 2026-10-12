---
description: Run a UI test on Simulator via a JSON flow (one screen, or a matrix of cases × simulators)
argument-hint: <screen, flow, or list of cases; optionally which simulators>
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, Agent
---

Test only this requested UI behavior: `$ARGUMENTS`.

Read and follow the shared `fast-ios-device-test` skill
(`skills/fast-ios-device-test/SKILL.md` in this plugin, or `~/.claude/skills/fast-ios-device-test/SKILL.md`). The engine is:

```bash
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastSimulatorTest" <flow.json> [--reuse-app|--build-only]
```

Decide the shape first, before writing any flow:

- ONE flow on ONE simulator → write the smallest version-1 flow in a temporary
  directory, run it, return the PASS/FAIL line.
- Several flows on ONE simulator (up to about 5) → build once with
  `--build-only`, then run them one after another here with `--reuse-app`.
- 2+ simulators, or more flows than that → follow the skill's "several flows or
  several simulators" section: build once with `--build-only`, then dispatch one
  `sonnet` agent per booted simulator in a single message, each running its
  flows with `--reuse-app --session <name>`, then collate with
  `"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastUIReport" --root <project>/build/fast-ui --session <name>`.
  Never run a multi-simulator matrix serially in this conversation.
- The user asks for video ("quay", "record") → add `--record`; only the final
  passing clip per task is kept.
- A FAIL whose visible labels show the app in a wrong state is a product bug:
  fix the code, rebuild, rerun the same flow until it passes.

Rules that keep it fast: timeouts ≤ 8 s except the first wait (≤ 20 s);
`post_delay` ≤ 1 s; unknown label → a `dump` action, never a fake `wait`; on
FAIL fix one selector using the `visible labels` in the FAIL line, at most two
reruns per flow.

Remove temporary flows afterward; persist only when the user asks. Do not edit
the Python engine for a screen-specific task. Return the PASS/FAIL lines (a
flow × simulator table when fanned out) and one concise cause per FAIL.
