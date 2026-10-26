# Changelog

## Unreleased

### Prompt rules

- `optional_permission_labels` takes rules beside bare labels:
  `{"title_contains": "track", "tap": "Ask App Not to Track"}` answers one kind of prompt,
  matched by its title, on the Simulator and on the iPhone. Bare labels answered every prompt
  with the first declared label it carried, so notifications and tracking (both `Allow`) could
  not get different answers, and a location prompt fell to `Don’t Allow` when its own button was
  not declared. A rule whose title matches owns the prompt: a missing button taps nothing.
- Device: each request starts with no prompt labels. A `do` used to keep the labels of the last
  flow the runner served and tapped those prompts unasked; it now taps only what
  `--prompt-labels` declares. PASS/FAIL lines list what was answered:
  `dismissed=["<title> → <button>"]`.

### Idle wait off, safely

- Device, with `wait_for_idle: false` / `--no-idle-wait`: a tap by selector (`tap_label`,
  `tap_first`, `tap_nearest`) waits until two snapshots agree on the target's frame (up to
  1.5 s), so it no longer lands on a button still sliding in; `launch` and `activate` wait until
  the app is frontmost and its layout stops moving (up to 2 s), so the next `screenshot`,
  `tap_point` or `swipe` no longer acts on the launch screen.
- `do --no-idle-wait` reports `wait_for_idle=unsupported` when the private API is missing, as
  flows already did; it used to keep waiting without a word.
- The runner's pure logic (prompt rules, settling) is checked on the Mac by
  `RunnerLogicTests`, which compiles it with `swiftc`. The next device run rebuilds the runner by
  itself (its cache key covers the Swift sources); a runner already started with `serve` keeps
  the old code until `fastDeviceTest stop`.

### Fixes

- `screenshot` taps away a declared `optional_permission_labels` prompt before capturing, on the
  Simulator and on the iPhone (the device runner needs `--rebuild-runner` once). It read no tree,
  so a notification or location request raised after the flow's last `wait` (during a `pause`)
  ended up in the evidence image. Checked on iOS 26.5 Simulators and an iPhone 11 on iOS 26.7.1.

### Docs

- Only actions that read the tree (and now `screenshot`) dismiss prompts; `pause`, `tap_point` and
  `swipe` do not. iOS 26 labels for the tracking (`Ask App Not to Track`) and location prompts.

- The App Store review sheet is not in the accessibility tree; close it with `tap_point`.
- `open_url` delivers a link with no prompt; a link tapped in Safari raises "Open in …?", where the
  StoreKit `Cancel` label would drop it, so that flow declares `Open`.

## 1.3.0 — 2026-10-13

### The iPhone screen can be recorded

`fastDeviceTest --record` keeps XCTest's own screen recording of a one-shot run. XCTest records
every UI test on a device by default, but its attachment lifetime `deleteOnSuccess` threw the
clip away whenever the test passed — and the runner's tests always pass, even when the flow
fails, because the flow reports its result in a file. `--record` sets `SystemAttachmentLifetime =
keepAlways` in that run's `.xctestrun`. No Control Center, no QuickTime, no recording dot, nothing
in Photos; video inside the app keeps playing (QuickTime/CoreMediaIO capture froze it).

- A PASS keeps `<task>/final[-<session>].mp4`, a FAIL `run.mp4`, as on the Simulator; the PASS and
  FAIL lines carry `video=file://…`. The full-resolution original stays in `result.xcresult`.
- `--record` is refused with `--serve` or while a persistent runner holds the iPhone: the runner
  is one long test, so its clip would span the whole session.
- `fastDeviceTest --session` (or `FAST_UI_SESSION`, shared with the Simulator) tags device runs;
  `fastUIReport` and `fastUIReview` now read them (keyed by the iPhone's UDID).

### Clips light enough for a PR

Both engines re-encode recordings at review quality: H.264 MP4, long side 960 px, ~800 kbit/s.

| Clip | Before | After |
|---|---|---|
| iPhone, 17 s, 1290×2796 | 20 MB (H.264, 10 Mbit/s) | 1.4 MB, 442×960, ~2 s to encode |
| Simulator, 23 s | full-resolution HEVC | 0.4 MB H.264, plays in every browser |

The re-encode replaces a clip only when it succeeded and came out smaller; any failure keeps
the original. `FAST_VIDEO_LONG_SIDE` / `FAST_VIDEO_KBPS` tune it, `FAST_VIDEO_LONG_SIDE=0` keeps
originals. AVFoundation only, no ffmpeg.

### `fastEvidenceSheet`

A new launcher lays chosen screenshots into one captioned sheet for a PR or ticket: a title,
then a label and a wrapped caption above each shot, from a JSON spec. Task cells take the shot
from the task's newest passing run; JPEG quality 80 by default (seven phone shots ≈ 300 KB);
the font covers Vietnamese diacritics; one FAIL line lists every missing shot with the shots
that exist.

### Smaller fixes

- `fastUIReview` prints its sheets, notes and review folder as `file://` links, like the engines.
- Tests: `test_fast_media.py` (including a real AVFoundation encode) and
  `test_fast_evidence_sheet.py`; 102 tests in all, one of them runs every launcher as the copy a
  zip stores. `install.sh` self-tests the media module too.

## 1.2.0 — 2026-10-13

Compared with the first version (1.1.0 by DungVC, with the Xcode 27 fixes listed below).
Every change came from measurements on Xcode 27.0 and from 63 past sessions that used the
tool; the research and the plan are in `docs/`.

### Fewer reruns: failures explain themselves

The most common failure in those sessions was a wrong selector, and each rerun waited out a
20 s timeout because the FAIL line showed labels without saying why none matched.

- A FAIL line now lists `label (Type)` for every visible label, says when the wanted label
  exists under another element type (`'Add Widget' exists as StaticText, not Button`), and
  otherwise suggests the closest labels.
- `tap_label` without `element_type` taps the one node carrying the label when no Button
  does, and reports `fallback_type`. It never taps the Application or Window root, and on
  a device it treats nested containers with the same label and frame as one target.
- New selectors on simulator and device: `id` (accessibilityIdentifier, the most stable
  key) and `value` (a switch's `1`/`0`, a field's text). `tap_label` accepts every key.
- AXe sometimes fails to open its automation session on the first tap after a boot; the
  engine now retries once instead of failing the flow.

### Faster

| Where | Before | After |
|---|---|---|
| Simulator, each `wait` followed by a tap | two `describe-ui` calls (0.9–2.7 s each) | one: a tree younger than 300 ms is reused |
| iPhone, each tap on a screen that never stops animating | ~2.4 s of XCUITest wait-for-idle | ~0 with `setup.wait_for_idle: false` or `do --no-idle-wait` |
| `fastUIReview` helper | interpreted by `swift` on every run (~4 s cold) | compiled once and cached |
| Install on a new Mac with Xcode | Homebrew had to install AXe and xcodegen | under a second, nothing downloaded |

`"settle": true` on a tap or swipe is new and opt-in: it waits until the hierarchy stops
changing (at most 2.5 s), for screens where a fixed `post_delay` is a guess.

### Does more

- Simulator actions `type_text`, `launch`, `terminate` and `open_url` (deep links).
- `"prebuilt": true` in `app` drives what is already on the simulator, such as Settings or
  a build Xcode installed, without a project, DerivedData or fresh install.
- `--device` accepts a unique part of the iPhone's name; a part shared by two is refused.
- The engine runs without Pillow; only `motion` and `fastUIReview` need it.

### Lighter on tokens and disk

- `dump` and `failure-ui.json` are a flat list of label, type, id, value, frame and tap
  centre. A real failure dump went from 11 MB to 47 KB.
- `SKILL.md` went from 1366 to 887 words and the two main slash commands from 316 and 231
  to 158 and 135 words, so each invocation loads about 1.5k fewer tokens. In a before/after
  test an agent found the prebuilt-app mode in `SKILL.md` and passed on the first run
  (3 tool calls instead of 8).
- `SKILL.md` now says when to use Xcode 27's own `device-interaction` MCP tools (exploring
  an unknown screen, pinch, drag, console log) and when to use this tool (repeatable proof,
  matrix, video, report).

### Install and packaging

- AXe 1.8.0 ships in `vendor/` (MIT, licence included) and the device runner's `.xcodeproj`
  is committed: no Homebrew and no xcodegen.
- `install.sh --check` prints Xcode, AXe, Python, Pillow and signing-profile status and what
  is missing, and still reports cleanly on a Mac with no Xcode selected.
- `make-zip.sh` builds `fast-ios-device-test-<version>.zip`.
- Unit tests: 53 → 77; the suite runs with or without Pillow.

### Known limitations, planned for 1.2.1

- The docs tell prebuilt flows to start with `launch`, but the engine already launches the
  app, so that step costs an extra ~0.5 s.
- Editing `device-runner/project.yml` without regenerating the committed `.xcodeproj`
  builds the old project silently.
- `fastDeviceTest do --no-idle-wait` cannot report when the private XCTest selector is
  missing (flows do report it).
- `install.sh` does not warn when an older `axe` earlier on PATH shadows the bundled one.
- The "add element_type" hint appears even when the selector already has one.

## 1.1.0-xcode27 — 2026-10-02

Local fixes on top of 1.1.0, which was written against Xcode 26.

- The engine opens Device Hub on Xcode 27; AXe's automation session times out without it.
- Taps linger 0.4 s under Device Hub (measured: a post-delay of 0 lost 6 of 6 taps, 0.15 s
  lost 2 of 6, 0.25 s lost none).
- A flow without `build_inputs` no longer reuses a stale app forever.
- `SKILL.md` gained a complete flow example and was split into `references/device.md` and
  `references/review.md`; fan-out uses `sonnet` agents, and only for 2+ simulators or more
  than 5 flows.

## 1.1.0 — DungVC

The original tool: `/fastSimulatorTest`, `/fastDeviceTest` and `/fastUIReview`, JSON flows,
fresh install with seeded UserDefaults, dark and Dynamic Type variants, recording with
contact-sheet review, per-simulator fan-out and the `fastUIReport` table.
