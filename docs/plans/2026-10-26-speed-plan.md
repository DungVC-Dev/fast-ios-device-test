# Faster first runs — design and plan

Status: approved by the user 2026-10-26 ("cả 3 đi") after Fable's analysis: per decision an agent
step takes ~13 s on the iPhone (7.5 s tool + 5.6 s model) and ~45 s on the Simulator, where every
step re-runs a whole flow. Goal: ~6–8 s per step on the iPhone, ≤10 s on the Simulator, and fewer
model turns on linear paths.

## A. `fastSimulatorTest do`

`fastSimulatorTest do '<action or array>' [--simulator <udid>] [--app <bundle id>] [--out <dir>]
[--prompt-labels <labels>]` runs actions on what the Simulator shows now: no build, install,
launch or preferences. AXe is one process per call anyway, so no resident runner is needed.

- `--simulator` defaults to `FAST_SIMULATOR`; one of them is required.
- Boot check and Device Hub as a flow does (`ensure_booted`), then the actions through
  `execute_action`; an array stops at the first failure.
- One tree read at the end; the line matches the iPhone's `do`:
  `PASS <type>|actions=N [screenshot(s)=…] [ui=…] labels=[…]`, or
  `FAIL [actions=N step=K type=…] error=… labels=[…]` on stdout, input refused before anything
  runs on stderr, as `fastDeviceTest do` does; exit 0 / 1.
- Screenshots and dumps go to `--out` (default the current directory).
- The screen map records the trail when `--app` (or `FAST_UI_APP`) names the bundle id.

## B. Fixed costs and defaults

- `serve` stores the device (udid, name, os) in its state file. `resolve_device` first looks
  at the state files: a request that names a serving iPhone by UDID or full name and gets a ping
  answer skips `xcrun devicectl list devices` (measured 0.16 s on this Mac, up to ~1 s).
- `FAST_DEVICE` is the default `--device`; `FAST_SIMULATOR` the default simulator for `do`.
- `fastDeviceTest do` runs with the idle wait off by default (the runner settles on its own);
  `--idle-wait` turns it back on; `--no-idle-wait` is still accepted. Flows keep their setting.
- SKILL.md and device.md: explore step by step with `do` on both engines; no `pause`, `dump` or
  `screenshot` in routine steps (the line already lists 40 labels); send known steps as one
  array with `expect` guards; one-line replies between steps.

## C. Guarded multi-step requests

- Any action may carry `expect` (a selector) and `expect_timeout` (default 2 s). After the action
  the engine waits for it; a miss stops the request at that step with the visible labels.
  Native in `execute_action` (Simulator) and `execute()` (iPhone runner), so step numbers stay.
- In a `do` array of more than one action, a gesture whose selector text looks destructive —
  delete, remove, erase, reset, pay, buy, purchase, subscribe, send, sign out, log out,
  unpair, forget — refuses the whole request before anything runs, unless that action has
  `"confirm": true`. A single-action `do` and flows are not checked: the agent chose that step
  alone, or a person wrote the flow.
- Shared by both launchers in `scripts/fast_guard.py` (with `parse_prompt_labels`).

## Tasks

1. `fast_guard.py` + tests: `DESTRUCTIVE`, `risky_step(actions) -> tuple[int, str] | None`,
   `parse_prompt_labels` (moved from `fast_device.py`).
2. `expect` in `execute_action` + tests; `expect` in the runner's `execute()`; compile.
3. Simulator `do` (`run_do` in `fast_ui.py`, `main()` dispatch) + tests: PASS/FAIL lines, no
   build/install/launch, `FAST_SIMULATOR`, trail with `--app`, destructive refusal.
4. Device: cached device in the state file, `FAST_DEVICE`, idle wait off by default,
   destructive refusal + tests.
5. Docs (SKILL.md rules, usage.md, device.md, commands), CHANGELOG.
6. Hardware: Simulator `do` and iPhone `do` timings before/after on Settings; an `expect` miss on
   both; Fable review; commit and push when the user says so.
