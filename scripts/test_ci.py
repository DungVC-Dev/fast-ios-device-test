#!/usr/bin/env python3

"""Text-level contracts for CI workflows without adding a YAML dependency."""

from __future__ import annotations

import os
import tempfile
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class WorkflowTests(unittest.TestCase):
    def test_ci_has_reusable_linear_history_and_least_privilege_jobs(self) -> None:
        ci = read(".github/workflows/ci.yml")
        for token in (
            "pull_request:", "types: [opened, synchronize, reopened]", "branches: [main]",
            "workflow_call:", "cancel-in-progress: true", "contents: read",
            "history:", "test:", "consistency:", "origin/main..HEAD",
            "rebase on main: git fetch && git rebase origin/main",
        ):
            self.assertIn(token, ci)
        for action in ("actions/checkout@v7", "actions/setup-python@v7", "actions/setup-node@v7"):
            self.assertIn(action, ci)
        self.assertNotIn("@v4", ci)

    def test_ci_runs_full_package_and_consistency_checks(self) -> None:
        ci = read(".github/workflows/ci.yml")
        for token in (
            "python3 -m pip install pillow", "command -v swiftc", "unittest discover -p 'test_*.py'",
            "bash -n install.sh release.sh make-zip.sh", "shellcheck -S warning",
            "python3 scripts/package_marketplaces.py", "npm pack --dry-run --json", "12 * 1024 * 1024",
            '"assets/readme/", "build/"', ".antigravity-plugin/plugin.json", "## Unreleased",
            "sed -n '/^## Project overview/,$p'", "raw\\.githubusercontent\\.com",
            "[^\\s)>\"\\'`]+",
            "curl -LIfsS --retry 3",
        ):
            self.assertIn(token, ci)

    def test_publish_reuses_ci_and_requires_main_and_environment(self) -> None:
        publish = read(".github/workflows/publish.yml")
        for token in (
            "uses: ./.github/workflows/ci.yml", "needs: checks", "environment: npm",
            "git merge-base --is-ancestor", "origin/main", "actions/checkout@v7",
            "actions/setup-node@v7",
        ):
            self.assertIn(token, publish)

    def test_upstream_sync_is_linear_and_can_open_a_pr(self) -> None:
        sync = read(".github/workflows/sync-upstream.yml")
        self.assertIn('cron: "0 */6 * * *"', sync)
        self.assertIn("git rebase origin/main", sync)
        self.assertIn("gh pr create --base main", sync)
        self.assertIn("pull-requests: write", sync)
        self.assertNotRegex(sync, r"\bgit merge(?:\s|$)")

    def test_repo_rules_script_is_dry_run_by_default_and_complete(self) -> None:
        script_path = ROOT / "scripts/setup_repo_rules.sh"
        script = script_path.read_text(encoding="utf-8")
        self.assertTrue(os.access(script_path, os.X_OK))
        for token in (
            "apply=false", "--dry-run", "--apply", "--include-admins", "--maintainer",
            '"allow_merge_commit": false', '"allow_squash_merge": false',
            '"allow_rebase_merge": true', '"delete_branch_on_merge": true',
            '"history", "test", "consistency"', '"required_linear_history": true',
            '"allow_force_pushes": false', '"allow_deletions": false',
            "branches/main/protection", "environments/npm", '"type": "User"',
        ):
            self.assertIn(token, script)

    def test_repo_rules_script_targets_origin_not_upstream(self) -> None:
        """A fork has an "upstream" remote; `gh repo view` would pick it and protect the wrong repo."""
        script = (ROOT / "scripts/setup_repo_rules.sh").read_text(encoding="utf-8")
        self.assertNotIn("$(gh repo view", script)
        self.assertIn("git remote get-url origin", script)
        self.assertIn("--repo)", script)
        with tempfile.TemporaryDirectory() as raw:
            subprocess.run(["git", "init", "-q", raw], check=True)
            subprocess.run(["git", "-C", raw, "remote", "add", "origin",
                            "git@github.com:owner/fork.git"], check=True)
            subprocess.run(["git", "-C", raw, "remote", "add", "upstream",
                            "https://github.com/other/original"], check=True)
            fake_bin = Path(raw) / "bin"
            fake_bin.mkdir()
            gh = fake_bin / "gh"
            gh.write_text("#!/bin/sh\ncase \"$*\" in *user*) echo me ;; *users/*) echo 1 ;; esac\n")
            gh.chmod(0o755)
            env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
            env.pop("GH_REPO", None)
            result = subprocess.run(["bash", str(ROOT / "scripts/setup_repo_rules.sh")], cwd=raw,
                                    capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repository=owner/fork ", result.stdout)

    def test_agent_facts_remain_identical(self) -> None:
        def facts(name: str) -> str:
            text = read(name)
            return text[text.index("## Project overview"):]

        self.assertEqual(facts("AGENTS.md"), facts("CLAUDE.md"))


if __name__ == "__main__":
    unittest.main()
