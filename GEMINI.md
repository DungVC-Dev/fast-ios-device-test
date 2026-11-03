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
  `build/plugin-packages/stage/antigravity`. Run the engines through launchers in `~/.local/bin`.
- `skills/fast-ios-device-test/SKILL.md` and `skills/iphone-duo-swiftui/SKILL.md` are standard
  Agent Skills. Antigravity loads them from the
  plugin, or globally when it is linked into `~/.gemini/config/skills/`; Gemini CLI loads
  them from the extension declared by `gemini-extension.json`. A locally exported
  `apple-app-resizability` skill complements Duo code changes but is never packaged.
- For iPhone Duo, run the installed `fastSimulatorTest` launcher; use `duo` flow actions for
  outer/inner display changes and `--duo-pose closed|open|book|tabletop` for fixed-framebuffer
  recording rows. Do not automate Device Hub outside the launcher. The Antigravity marketplace
  README and Gemini extension context repeat this provider-facing workflow.
- `install.sh` only installs into `~/.claude`. Never run it to probe flags: any unknown
  argument triggers a real install (details in `AGENTS.md`).
