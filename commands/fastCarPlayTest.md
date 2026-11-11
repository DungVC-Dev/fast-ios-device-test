---
description: Run a mixed phone + CarPlay flow on Simulator.app or Apple's CarPlay Simulator
argument-hint: <flow.json> --target sim|hardware
allowed-tools: Bash(fastCarPlayTest:*), Bash(fastUIClean:*)
---

Run `fastCarPlayTest doctor --target sim|hardware` first, then execute the requested flow with
`fastCarPlayTest run`. Read the `fast-ios-device-test` skill's CarPlay reference before authoring a
flow. Never use `simctl io screenshot --display external`; it destructively remodes iOS 27 CarPlay.

After the report, ask the user once whether to clear the test cache: quote the size
`fastUIClean --project <root>` lists, and run it with `--yes` only on a yes.
