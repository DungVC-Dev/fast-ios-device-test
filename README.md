<div align="center">
  <img src="assets/fast-ios-device-test.png" width="176" alt="fast-ios-device-test logo">
  <h1>fast-ios-device-test</h1>
  <p><strong>Tell your coding agent what to verify. Get a PASS/FAIL and evidence you can review.</strong></p>

  <p>
    <a href="https://www.npmjs.com/package/fast-ios-device-test"><img alt="npm version" src="https://img.shields.io/npm/v/fast-ios-device-test?style=flat-square&logo=npm&color=CB3837"></a>
    <a href="https://www.npmjs.com/package/fast-ios-device-test"><img alt="npm downloads" src="https://img.shields.io/npm/dm/fast-ios-device-test?style=flat-square&logo=npm&color=CB3837"></a>
    <img alt="macOS" src="https://img.shields.io/badge/macOS-only-111111?style=flat-square&logo=apple">
    <img alt="Xcode 26 or 27" src="https://img.shields.io/badge/Xcode-26%20%7C%2027-147EFB?style=flat-square&logo=xcode&logoColor=white">
    <a href="#license-and-credits"><img alt="License and credits" src="https://img.shields.io/badge/license-see%20credits-6E7781?style=flat-square"></a>
  </p>

  <p>
    <a href=".claude-plugin/plugin.json"><img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-D97757?style=flat-square&logo=anthropic&logoColor=white"></a>
    <a href="plugin.json"><img alt="Codex plugin" src="https://img.shields.io/badge/Codex-plugin-111111?style=flat-square&logo=openai&logoColor=white"></a>
    <a href="gemini-extension.json"><img alt="Gemini CLI extension" src="https://img.shields.io/badge/Gemini_CLI-extension-8E75B2?style=flat-square&logo=googlegemini&logoColor=white"></a>
    <a href=".antigravity-plugin/plugin.json"><img alt="Antigravity plugin" src="https://img.shields.io/badge/Antigravity-plugin-4285F4?style=flat-square&logo=google&logoColor=white"></a>
  </p>
</div>

## Why fast-ios-device-test?

- **Fast feedback.** Cached builds and local drivers keep repeat runs short.
- **No XCUITest target to write.** The agent writes the flow; AXe and the bundled runner drive it.
- **Evidence you can review.** Every case keeps metrics; ask for screenshots, video, or a report.

<table>
  <tr>
    <td align="center" width="34%"><img src="https://raw.githubusercontent.com/DungVC-Dev/fast-ios-device-test/672db5ba22f38faf7152bc1742fd43952cb1ef6f/assets/readme/settings-simulator.png" width="220" alt="Settings on an iPhone Simulator after a passing fastSimulatorTest run"></td>
    <td align="center" width="66%"><img src="https://raw.githubusercontent.com/DungVC-Dev/fast-ios-device-test/672db5ba22f38faf7152bc1742fd43952cb1ef6f/assets/readme/carplay-simulator.jpg" width="520" alt="CarPlay home screen in a real Simulator run"></td>
  </tr>
  <tr>
    <td align="center"><strong>Simulator</strong><br><code>PASS</code> Settings in 9.5s</td>
    <td align="center"><strong>CarPlay Simulator</strong><br>Real display capture</td>
  </tr>
</table>

## Quick start

### 1. Install the runtime

```bash
npx fast-ios-device-test
npx fast-ios-device-test --check
```

This installs the launchers, required AXe, and optional CarPlay tool `baguette`. Tool versions and
SHA-256 checksums are pinned in [`vendor/tools.json`](vendor/tools.json). Homebrew is not required.

### 2. Connect your agent

The runtime gives you the engines. The plugin or extension teaches your agent how to use them.

| Agent | Install | Then |
|---|---|---|
| **Codex** | `codex plugin marketplace add DungVC-Dev/fast-ios-device-test`<br>`codex plugin add fast-ios-device-test@fast-ios-device-test` | Restart Codex |
| **Antigravity** | `agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test` | `agy plugin list`, restart Antigravity |
| **Gemini CLI** | `gemini extensions install https://github.com/DungVC-Dev/fast-ios-device-test` | Restart Gemini CLI |
| **Claude Code** | `/plugin marketplace add DungVC-Dev/fast-ios-device-test`<br>`/plugin install fast-ios-device-test@fast-ios-device-test` | Optional, see below |

> [!NOTE]
> **Claude Code needs no plugin.** `npx fast-ios-device-test` already links the skill, the slash
> commands and the subagent into `~/.claude`. Add the plugin only if you want to manage it with
> `/plugin`; with both, Claude Code lists the skill and the commands twice.

### 3. Ask for a check

Claude Code has slash commands:

```text
/fastSimulatorTest Settings opens and shows General, take a screenshot
```

With Codex, Gemini CLI, or Antigravity, ask in plain words:

> Test the paywall on Simulator in dark mode and record it.

The agent writes the flow, runs it, and returns one result line per case. You do not write
`flow.json` by hand.

<details>
<summary>Store status</summary>

Codex repository-marketplace, Antigravity GitHub-plugin and Gemini CLI direct installs work now.
The public Codex directory listing and the curated Antigravity listing
(`agy plugin install fast-ios-device-test@antigravity-plugins-official`) are submission-ready but
not live yet. When they are, install from Codex `/plugins` (search **Fast iOS Device Test**) or
Antigravity **Customizations → Marketplace**.

</details>

<details>
<summary>Update or check a clone</summary>

```bash
npx fast-ios-device-test update
npx fast-ios-device-test update-tools
./install.sh --check
```

A missing `baguette` does not fail the check. Install its verified pin only when needed with
`./install.sh --install-baguette`.

</details>

## Supported targets

| Target | Driver | UI flow | Screenshots | Recording | Notes |
|---|---|---:|---:|---:|---|
| iPhone Simulator | AXe | Yes | Yes | Yes | Xcode 26 or 27 |
| Physical iPhone | Bundled XCUITest runner | Yes | Yes | Yes | Recording uses a one-shot run |
| iPhone Duo | AXe + Device Hub | Yes | Outer + inner | One display | Xcode 27.1; closed, open, book, tabletop |
| CarPlay Simulator | AXe + `baguette` | Phone + car | Yes | No | Disposable `agent-tmp-*` simulator only |
| CarPlay hardware | XCUITest + CarPlay Simulator | Phone + car | Yes | Yes | USB iPhone; Automaker UI reports `VOID` |

## How a run works

```mermaid
flowchart LR
    A[AI agent] --> C{Slash command or launcher}
    C --> S[fastSimulatorTest]
    C --> D[fastDeviceTest]
    C --> P[fastCarPlayTest]
    S --> SE[fast_ui.py + AXe]
    D --> DE[fast_device.py + XCUITest runner]
    P --> PE[fast_carplay.py + baguette]
    SE --> SIM[Simulator or iPhone Duo]
    DE --> IP[Physical iPhone]
    PE --> CP[CarPlay display]
```

Flows are versioned JSON. Each engine prints one result line and stores screenshots, metrics, and
failure evidence under the flow's artifact root.

## What each command does

Each command works the same way: you describe the behavior, the agent writes a JSON flow, runs it,
and answers with one result line per case plus the evidence.

### `/fastSimulatorTest`: Simulator

```text
/fastSimulatorTest Settings opens and shows General, take a screenshot
```

The agent builds the app once, drives the Simulator through AXe and replies:

```text
PASS task=settings-general-smoke total=9.5s build=skip artifacts=file:///…/settings-general-smoke/
```

A failure names the step and the cause (`FAIL … step=03_wait error=…`) next to a screenshot and the
screen labels it saw. Ask for *dark mode*, *larger text* or *record it* in plain words; the agent
maps them to `--appearance`, `--content-size` and `--record`.

<details>
<summary>Flow the agent writes</summary>

```json
{
  "version": 1,
  "name": "settings-general-smoke",
  "app": {
    "project_root": "/absolute/path/to/project",
    "bundle_id": "com.apple.Preferences",
    "simulator": "iPhone 17 Pro",
    "prebuilt": true
  },
  "actions": [
    {"type": "launch"},
    {"type": "wait", "label": "General"},
    {"type": "screenshot", "name": "general.png"}
  ]
}
```

Run by hand: `fastSimulatorTest flow.json --record --session <name>`. Step by step:
`fastSimulatorTest start <draft.json>`, `fastSimulatorTest do '<action-json>'`,
`fastSimulatorTest labels`, then `fastSimulatorTest save <flow.json>`.
</details>

### `/fastDeviceTest`: physical iPhone

```text
/fastDeviceTest login works on my iPhone, record a video
```

Same flows, run on the cabled iPhone by a cached, auto-signed XCUITest runner. Settings, Shortcuts
and SpringBoard work too.

```text
PASS task=login device=My iPhone mode=server total=<seconds>s artifacts=<file-url>
```

<details>
<summary>Flow the agent writes</summary>

```json
{
  "version": 1,
  "name": "device-home",
  "app": {
    "project_root": "/absolute/path/to/project",
    "bundle_id": "com.example.app",
    "device": "My iPhone"
  },
  "actions": [
    {"type": "launch"},
    {"type": "wait", "label": "Home"},
    {"type": "screenshot", "name": "home.png"}
  ]
}
```

Run by hand: `fastDeviceTest flow.json --device <name-or-udid> [--install <app>] [--record] [--session <name>]`.
</details>

### iPhone Duo

```text
/fastSimulatorTest the Home screen on iPhone Duo, closed and open
```

The agent drives Device Hub (Xcode 27.1): `closed` shows the outer display, `open`, `book` and
`tabletop` the inner one, and each screenshot comes from the display in use. One result row per
pose (`@duo-closed`, `@duo-open`).

<details>
<summary>Flow the agent writes</summary>

```json
{
  "version": 1,
  "name": "duo-displays",
  "app": {
    "project_root": "/absolute/path/to/project",
    "bundle_id": "com.apple.Preferences",
    "simulator": "iPhone Duo",
    "prebuilt": true
  },
  "actions": [
    {"type": "launch"},
    {"type": "duo", "pose": "closed"},
    {"type": "screenshot", "name": "outer.png"},
    {"type": "duo", "pose": "open"},
    {"type": "screenshot", "name": "inner.png"}
  ]
}
```

Run by hand: `fastSimulatorTest flow.json --duo-pose closed|open|book|tabletop`.
</details>

### `/fastCarPlayTest`: CarPlay

```text
/fastCarPlayTest the lyrics widget shows on the CarPlay screen
/fastCarPlayTest same check on the small 800×480 display
/fastCarPlayTest CPR-01 on the CarPlay Simulator
```

- **Simulator**: Xcode's CarPlay window on a throwaway `agent-tmp-*` simulator, driven by baguette.
  Widescreen 1920×720 by default; ask for the *small* (800×480) or *HD* display when you need it.
  One size per run.
- **Hardware**: Apple's CarPlay Simulator with your iPhone on USB, including connect/disconnect
  cases. An "Automaker UI" screen means CarPlay was not connected: the case is `VOID`, not `FAIL`.

```text
PASS task=lyrics-widget target=sim total=17.5s artifacts=file:///…/lyrics-widget/
```

<details>
<summary>Flow the agent writes</summary>

```json
{
  "version": 1,
  "name": "carplay-home",
  "app": {
    "project_root": "/absolute/path/to/project",
    "bundle_id": "com.example.app",
    "simulator": "agent-tmp-carplay",
    "prebuilt": true
  },
  "setup": {
    "carplay_display": "widescreen",
    "carplay_arm_script": "/absolute/path/to/project/tools/carplay_sim_display.sh"
  },
  "actions": [
    {"type": "launch"},
    {"surface": "car", "type": "car_wait_stable", "name": "CarPlay ready"},
    {"surface": "car", "type": "car_screenshot", "name": "car-home.png"}
  ]
}
```

Run by hand: `fastCarPlayTest doctor --target sim --display widescreen`, then
`fastCarPlayTest run flow.json --target sim --display widescreen --udid <udid>`. For hardware,
use `fastCarPlayTest run flow.json --target hardware --device <name> --record`.
</details>

### `/fastUIReview`: review and report

```text
/fastUIReview last session
```

Contact sheets of every recorded case (needs Pillow), and a PASS/FAIL table across flows, variants
and devices from `fastUIReport`.

### Several cases at once

Ask for them in one message: *"check this screen in light and dark, normal and largest text"*.
The agent runs one variant per run in a shared session and answers with one table. It adds only the
variants you ask for.

## FAQ

<details>
<summary><strong>Do I have to write the JSON flow?</strong></summary>

No. Describe the check to your agent. The JSON shown below each command is the repeatable artifact
the agent writes and runs for you.

</details>

<details>
<summary><strong>Does this require Homebrew?</strong></summary>

No. The installer manages a checksum-verified AXe pin under `~/.local/share/axe`. It installs
optional `baguette` under `~/.local/share/baguette` for CarPlay Simulator runs.

</details>

<details>
<summary><strong>Why can CarPlay Simulator take screenshots but not record video?</strong></summary>

The Simulator target supports `car_screenshot` steps. `--record` is supported only by the hardware
target's standalone CarPlay Simulator window.

</details>

<details>
<summary><strong>Why will a CarPlay run not use my normal simulator?</strong></summary>

Changing a CarPlay display can reboot and re-arm the simulator. For safety, the engine accepts only
a disposable simulator named `agent-tmp-*`.

</details>

<details>
<summary><strong>What does iPhone Duo need?</strong></summary>

Install Xcode 27.1's additional components and iOS runtime. Allow the terminal or agent under
**System Settings → Privacy & Security → Accessibility** so Device Hub can change pose.

</details>

## Reference

<details>
<summary><strong>Repository layout</strong></summary>

| Path | Purpose |
|---|---|
| `scripts/fast_ui.py` | Simulator and iPhone Duo engine |
| `scripts/fast_device.py` | Physical-iPhone engine |
| `scripts/fast_carplay.py` | Simulator and hardware CarPlay engine |
| `device-runner/` | Cached XCUITest runner project |
| `skills/fast-ios-device-test/` | Agent skill, examples, and detailed action reference |
| `commands/` | Claude Code slash commands |
| `vendor/tools.json` | Pinned versions, URLs, checksums, and licenses |
| `build/fast-ui/` | Default Simulator artifacts |
| `build/fast-device/` | Default physical-device artifacts |
| `build/fast-carplay/` | Default CarPlay artifacts |

</details>

<details>
<summary><strong>Environment variables</strong></summary>

| Variable | Purpose |
|---|---|
| `FAST_SIMULATOR` | Default Simulator UDID for step-by-step commands |
| `FAST_UI_APP` | Default bundle identifier for Simulator step-by-step commands |
| `FAST_DEVICE` | Default physical iPhone name or UDID |
| `FAST_UI_ROOT` | Simulator artifact root |
| `FAST_DEVICE_ROOT` | Physical-device artifact root |
| `FAST_UI_SESSION` | Shared report and review session name |
| `FAST_IOS_AXE_DIR` | Managed AXe installation directory |
| `FAST_IOS_BAGUETTE_DIR` | Managed `baguette` installation directory |
| `FAST_IOS_BIN_DIR` | Launcher and managed-tool wrapper directory |
| `FAST_IOS_INSTALL_DIR` | Runtime installation directory |
| `FAST_IOS_NO_UPDATE_CHECK=1` | Disable background package and tool update checks |
| `DUO_XCODE` | Override the Xcode 27.1 application used for iPhone Duo |

</details>

For guided setup and troubleshooting, see [SETUP.md](SETUP.md). Testers can use the Vietnamese
[GUIDE.md](GUIDE.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## License and credits

This repository does not currently declare a project-wide license. Managed third-party tools keep
their upstream licenses:

- [AXe](https://github.com/cameroncooke/AXe) by Cameron Cooke — MIT; see
  [`vendor/AXe-LICENSE`](vendor/AXe-LICENSE).
- [baguette](https://github.com/tddworks/baguette) by TDDWorks — Apache-2.0; see
  [`vendor/baguette-LICENSE`](vendor/baguette-LICENSE).
