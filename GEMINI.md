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
- `skills/fast-ios-device-test/SKILL.md` is a standard Agent Skill. Antigravity loads it from the
  plugin, or globally when it is linked into `~/.gemini/antigravity-cli/skills/`; Gemini CLI loads
  it from the extension declared by `gemini-extension.json`.
- `install.sh` only installs into `~/.claude`. Never run it to probe flags: any unknown
  argument triggers a real install (details in `AGENTS.md`).
