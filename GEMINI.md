# GEMINI.md

Guidance for Antigravity CLI (`agy`, the successor of Gemini CLI) working in this repository.

Antigravity loads both `GEMINI.md` and `AGENTS.md` from the repo root automatically, so the
project facts (structure, commands, conventions, git and release rules) live only in
`AGENTS.md`; this file holds what is specific to Antigravity. Keep it that way, or the facts are
loaded twice.

## Antigravity notes

- The slash commands in `commands/` and the `ui-explorer` subagent in `agents/` are written for
  Claude Code. The Antigravity source manifest is `.antigravity-plugin/plugin.json`; build its
  clean marketplace bundle with `python3 scripts/package_marketplaces.py`, then validate and install
  `build/plugin-packages/stage/antigravity` (`agy plugin install build/plugin-packages/stage/antigravity`).
- `skills/fast-ios-device-test/SKILL.md`, `skills/fast-ios-device-test-setup/SKILL.md`, and
  `skills/iphone-duo-swiftui/SKILL.md` are standard Agent Skills. Antigravity loads them from the
  plugin (`agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test`), or globally when
  linked or copied into `~/.gemini/config/skills/`; Gemini CLI loads them from the extension declared
  by `gemini-extension.json`. Locally exported `apple-app-resizability` and `apple-liquid-glass`
  skills complement code changes but are never packaged.
- Antigravity has no Claude slash commands; drive every engine through the CLI launchers in
  `~/.local/bin` (or `scripts/*.py`):
  - **Simulator:** `fastSimulatorTest <flow.json> [--reuse-app] [--record]`; explore live screens with
    `fastSimulatorTest start <draft.json>`, `fastSimulatorTest do '<action>'`, `fastSimulatorTest labels`,
    and `fastSimulatorTest save <flow.json>`; shut down with `fastSimulatorTest shutdown [--simulator <udid>]`.
  - **Physical iPhone:** `fastDeviceTest <flow.json> [--device <name|udid>] [--record]`; explore or tap
    with `fastDeviceTest do '<action>' --device <name|udid>`; verify rig with `fastDeviceTest check`;
    lock screen when done with `fastDeviceTest lock`.
  - **iPhone Duo (Xcode 27.1):** use `"simulator":"iPhone Duo"`. Change pose and orientation in flow
    actions with `{"type":"duo","pose":"closed|open|book|tabletop","orientation":"portrait|landscape"}`.
    Screenshots target the active framebuffer or set `"display":"outer|inner"`. For video, run one
    `--duo-pose <pose> [--duo-orientation <orientation>]` row per pose with a shared `--session --record`.
    Never automate Device Hub directly.
  - **CarPlay:** verify rig with `fastCarPlayTest doctor --target sim|hardware`; run mixed phone + car
    flows with `fastCarPlayTest run <flow.json> --target sim|hardware [--display widescreen|standard|hd|WxH@S]`.
    Car actions use `"surface":"car"`, `car_tap`, `car_swipe`, `car_screenshot`, and `car_wait_stable`.
  - **Liquid Glass:** derive cases LG-01..LG-11 using `skills/fast-ios-device-test/references/liquid-glass.md`;
    run matrix variants with `fastSimulatorTest flow.json --appearance light|dark --session <name>` and
    `--content-size <size>`; export local Apple Liquid Glass guides with
    `npx fast-ios-device-test xcode-skills --docs liquid-glass`.
  - **Review:** `fastUIReview --root <artifacts-root> --session <name>` builds contact sheets and
    `review-notes-<session>.json`; collate results table with `fastUIReport --root <artifacts-root> --session <name>`.
- **Subagents:** Claude Code's `ui-explorer` subagent is not loaded in Antigravity or Gemini CLI.
  Perform step-by-step screen exploration yourself directly via `fastSimulatorTest do` / `fastDeviceTest do`,
  or invoke an Antigravity subagent (`invoke_subagent`). When fanning out across multiple simulators, run
  flows sequentially or launch an Antigravity subagent per booted simulator.
- `install.sh` and `npx fast-ios-device-test` install runtime launchers into `~/.local/bin` and AXe into
  `~/.local/share/axe`. Default skill symlinks target Claude Code (`~/.claude/skills`), while Antigravity
  loads skills from the plugin or `~/.gemini/config/skills/`. Export Apple Xcode skills into managed
  agent directories with `npx fast-ios-device-test xcode-skills` (or `--docs liquid-glass`); list with
  `--list`. Never run `install.sh` with unknown arguments to probe flags: any unknown argument triggers
  a real install (details in `AGENTS.md`).
