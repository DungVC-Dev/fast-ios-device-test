---
description: Verify Amplitude tracking against a tracking-plan doc (xlsx): diff it with the code, drive the app on Simulator, report each event PASS/FAIL with evidence
argument-hint: <path to tracking plan .xlsx> [journey, category or event names to focus on]
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, Agent, Workflow
---

Verify Amplitude tracking for: `$ARGUMENTS`.

Follow the `amplitude-tracking-test` skill
(`~/.claude/skills/amplitude-tracking-test/SKILL.md`). Scripts:
`~/.local/share/fast-ios-device-test/amplitude-tracking-test/scripts/` (with `install.sh --link`: the
clone's `amplitude-tracking-test/scripts/`, `../../amplitude-tracking-test/scripts/` from the skill's real path).

- No focus given → run steps 1–3 (plan, static diff, key guard) and report them first; then run the
  saved journeys for the app. A focus given → only the journeys that cover it.
- Read only script summary lines and non-PASS rows; never the workbook or raw logs.
- Never tap purchase/subscribe buttons; never test against a production key.
- End with the report described in the skill and offer to save new or fixed flows.
