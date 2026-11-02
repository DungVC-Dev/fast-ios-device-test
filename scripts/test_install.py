"""install.sh: broken links are reported by --check and a dead Codex/Antigravity skill link is
repaired by an install. Every path points into a temporary home, never the user's setup."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAUNCHERS = ["fastSimulatorTest", "fastDeviceTest", "fastUIReview", "fastUIReport",
             "fastEvidenceSheet", "fastUIMap", "fastUIClean"]


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class InstallCheckTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.dirs = {name: self.home / name for name in
                     ("bin", "skills", "commands", "agents", "codex", "antigravity")}
        for path in self.dirs.values():
            path.mkdir()
        self.env = dict(os.environ,
                        HOME=str(self.home),
                        FAST_IOS_INSTALL_DIR=str(self.home / "share"),
                        FAST_IOS_BIN_DIR=str(self.dirs["bin"]),
                        FAST_IOS_AXE_DIR=str(self.home / "axe"),
                        CLAUDE_SKILLS_DIR=str(self.dirs["skills"]),
                        CLAUDE_COMMANDS_DIR=str(self.dirs["commands"]),
                        CLAUDE_AGENTS_DIR=str(self.dirs["agents"]),
                        CODEX_HOME=str(self.home / "codex-home"),
                        CODEX_SKILLS_DIR=str(self.dirs["codex"]),
                        ANTIGRAVITY_SKILLS_DIR=str(self.dirs["antigravity"]))

    def link_everything(self):
        for name in LAUNCHERS:
            (self.dirs["bin"] / name).symlink_to(REPO / "scripts" / "fast_ui.py")
        (self.dirs["skills"] / "fast-ios-device-test").symlink_to(REPO / "skills" / "fast-ios-device-test")
        (self.dirs["agents"] / "ui-explorer.md").symlink_to(REPO / "agents" / "ui-explorer.md")

    def run_install(self, *args):
        result = subprocess.run(["bash", str(REPO / "install.sh"), *args], env=self.env,
                                capture_output=True, text=True, timeout=300)
        return result.returncode, result.stdout + result.stderr

    def missing_line(self, output):
        return next((line for line in output.splitlines() if line.startswith("CHECK")), "")

    def test_check_reports_a_dangling_claude_skill_link(self):
        self.link_everything()
        skill = self.dirs["skills"] / "fast-ios-device-test"
        skill.unlink()
        skill.symlink_to(self.home / "deleted-clone" / "skills" / "fast-ios-device-test")
        code, out = self.run_install("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("skill (broken link)", self.missing_line(out))
        self.assertIn(f"broken link: {skill}", out)

    def test_check_reports_a_dangling_launcher(self):
        self.link_everything()
        launcher = self.dirs["bin"] / "fastUIMap"
        launcher.unlink()
        launcher.symlink_to(self.home / "gone" / "fast_ui_map.py")
        _, out = self.run_install("--check")
        self.assertIn("fastUIMap launcher (broken link)", self.missing_line(out))

    def test_check_reports_a_dangling_codex_skill_link(self):
        self.link_everything()
        (self.dirs["codex"] / "fast-ios-device-test").symlink_to(self.home / "old-clone")
        _, out = self.run_install("--check")
        self.assertIn("codex skill (broken link)", self.missing_line(out))
        self.assertIn("codex=broken skill link", out)

    def test_check_reports_an_empty_codex_plugin_cache(self):
        self.link_everything()
        cache = self.home / "codex-home" / "plugins" / "cache" / "fast-ios-device-test"
        cache.mkdir(parents=True)
        _, out = self.run_install("--check")
        self.assertIn("codex skill (empty plugin cache)", self.missing_line(out))
        skill = cache / "fast-ios-device-test" / "2.0.2" / "skills" / "fast-ios-device-test"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: fast-ios-device-test\n---\n")
        _, out = self.run_install("--check")
        self.assertIn("codex=plugin", out)
        self.assertNotIn("codex skill", self.missing_line(out))

    def test_check_accepts_a_working_codex_link_and_no_codex(self):
        self.link_everything()
        _, out = self.run_install("--check")
        self.assertNotIn("codex", out)
        (self.dirs["codex"] / "fast-ios-device-test").symlink_to(REPO / "skills" / "fast-ios-device-test")
        _, out = self.run_install("--check")
        self.assertIn("codex=skill link", out)
        self.assertNotIn("codex", self.missing_line(out))

    @unittest.skipUnless(shutil.which("xcodebuild"), "install needs Xcode")
    def test_link_install_repairs_only_a_dangling_other_agent_link(self):
        codex = self.dirs["codex"] / "fast-ios-device-test"
        codex.symlink_to(self.home / "deleted" / "fast-ios-device-test")
        elsewhere = self.home / "my-clone" / "skills" / "fast-ios-device-test"
        elsewhere.mkdir(parents=True)
        antigravity = self.dirs["antigravity"] / "fast-ios-device-test"
        antigravity.symlink_to(elsewhere)
        self.env["PATH"] = f"{self.dirs['bin']}:{os.environ.get('PATH', '')}"
        code, out = self.run_install("--link")
        self.assertEqual(code, 0, out)
        self.assertEqual(Path(os.readlink(codex)), REPO / "skills" / "fast-ios-device-test")
        self.assertEqual(Path(os.readlink(antigravity)), elsewhere)

    def test_uninstall_removes_a_dangling_codex_link_and_keeps_a_working_clone_link(self):
        codex = self.dirs["codex"] / "fast-ios-device-test"
        codex.symlink_to(self.home / "share" / "skills" / "fast-ios-device-test")
        antigravity = self.dirs["antigravity"] / "fast-ios-device-test"
        antigravity.symlink_to(REPO / "skills" / "fast-ios-device-test")
        code, out = self.run_install("--uninstall")
        self.assertEqual(code, 0, out)
        self.assertFalse(codex.is_symlink())
        self.assertTrue(antigravity.is_symlink())


if __name__ == "__main__":
    unittest.main()
