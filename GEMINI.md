# GEMINI.md

Guidance for Antigravity CLI (`agy`, the successor of Gemini CLI) working in this repository.

Antigravity loads both `GEMINI.md` and `AGENTS.md` from the repo root automatically, so the
project facts (structure, commands, conventions, git and release rules) live only in
`AGENTS.md`; this file holds what is specific to Antigravity. Keep it that way, or the facts are
loaded twice.

## Antigravity notes

- The slash commands in `commands/` and the `ui-explorer` subagent in `agents/` are written for
  Claude Code; Antigravity does not load them. Run the engines directly instead
  (`scripts/fast_ui.py`, `scripts/fast_device.py`, or the launchers in `~/.local/bin`).
- `skills/fast-ios-device-test/SKILL.md` is a standard Agent Skill. Antigravity picks it up
  globally when it is linked into `~/.gemini/config/skills/` (see README, "Use with Codex or
  Antigravity CLI"); otherwise read it directly for how a flow is written. Where it mentions a
  subagent, do the steps yourself.
- `install.sh` only installs into `~/.claude`. Never run it to probe flags: any unknown
  argument triggers a real install (details in `AGENTS.md`).
