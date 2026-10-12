---
description: Run a UI flow on a physical iPhone (tap/type/swipe/screenshot via XCUITest), including Settings/Shortcuts/SpringBoard
argument-hint: <screen or flow; optionally which iPhone>
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Test only this requested behavior on a physical iPhone: `$ARGUMENTS`.

Read `references/device.md` of the `fast-ios-device-test` skill first
(`~/.claude/skills/fast-ios-device-test/references/device.md`); the flow format
and timing rules are in that skill's `SKILL.md`. The engine is:

```bash
"${CLAUDE_PLUGIN_ROOT:-$HOME/.local}/bin/fastDeviceTest" <flow.json> [--device <udid|name>] [--install <App.app>]
```

- The flow uses the same JSON schema as /fastSimulatorTest; `app.simulator`,
  `derived_data`, `app_path` and `fresh_install` are ignored on device.
- The app under test must already be installed on the iPhone (the user usually
  builds it); pass `--install` only when an .app for iphoneos is at hand.
- Several connected iPhones → ask which one or use the one the user named.
- To drive another app in a step, add `"app": "<bundle id>"` to that action
  (`com.apple.Preferences`, `com.apple.shortcuts`, `com.apple.springboard`).
- On FAIL, read `failure.png` and the `visible labels` in the FAIL line, fix one
  selector, rerun at most twice.

- More than one run, or exploring a screen step by step → `fastDeviceTest serve`
  first, then flows (~5 s each) or `fastDeviceTest do '<action json>'` (~1 s);
  `fastDeviceTest stop` when done so the iPhone is free for other agents.
- Matrix variants: `--appearance light|dark`, `--content-size <simctl name>`.

Remove temporary flows afterward. Return the PASS/FAIL line and one cause per FAIL.
