"""install.sh: broken links are reported by --check and a dead Codex/Antigravity skill link is
repaired by an install. Every path points into a temporary home, never the user's setup."""

import hashlib
import contextlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tool_manager

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
                        FAST_IOS_BAGUETTE_DIR=str(self.home / "baguette"),
                        FAST_IOS_INSTALL_TOOLS="axe",
                        CLAUDE_SKILLS_DIR=str(self.dirs["skills"]),
                        CLAUDE_COMMANDS_DIR=str(self.dirs["commands"]),
                        CLAUDE_AGENTS_DIR=str(self.dirs["agents"]),
                        CODEX_HOME=str(self.home / "codex-home"),
                        CODEX_SKILLS_DIR=str(self.dirs["codex"]),
                        ANTIGRAVITY_SKILLS_DIR=str(self.dirs["antigravity"]),
                        FAST_IOS_NO_UPDATE_CHECK="1", FAST_IOS_LATEST_VERSION="0.0.1",
                        FAST_IOS_UPDATE_CACHE=str(self.home / "update.json"),
                        ANTIGRAVITY_PLUGIN_DIR=str(self.home / "agy-plugins" / "fast-ios-device-test"))

    def fake_tool(self, name, version=None):
        pin = json.loads((REPO / "vendor" / "tools.json").read_text())[name]
        version = version or pin["version"]
        local = self.home / name / name
        local.parent.mkdir(exist_ok=True)
        local.write_text(f"#!/bin/sh\necho {version}\n")
        local.chmod(0o755)
        wrapper = self.dirs["bin"] / name
        wrapper.write_text(f'#!/bin/sh\nexec "{local}" "$@"\n')
        wrapper.chmod(0o755)
        return local

    def link_everything(self, include_baguette=True):
        for name in LAUNCHERS:
            (self.dirs["bin"] / name).symlink_to(REPO / "scripts" / "fast_ui.py")
        (self.dirs["skills"] / "fast-ios-device-test").symlink_to(REPO / "skills" / "fast-ios-device-test")
        (self.dirs["agents"] / "ui-explorer.md").symlink_to(REPO / "agents" / "ui-explorer.md")
        if include_baguette:
            self.fake_tool("baguette")

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
        self.assertIn("codex skill (empty plugin)", self.missing_line(out))
        skill = cache / "fast-ios-device-test" / "2.0.2" / "skills" / "fast-ios-device-test"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: fast-ios-device-test\n---\n")
        _, out = self.run_install("--check")
        self.assertIn("codex=plugin", out)
        self.assertNotIn("codex skill", self.missing_line(out))

    def test_check_rejects_a_plugin_cache_holding_only_the_setup_skill(self):
        self.link_everything()
        cache = self.home / "codex-home" / "plugins" / "cache" / "fast-ios-device-test"
        setup = cache / "fast-ios-device-test" / "2.0.2" / "skills" / "fast-ios-device-test-setup"
        setup.mkdir(parents=True)
        (setup / "SKILL.md").write_text("---\nname: fast-ios-device-test-setup\n---\n")
        _, out = self.run_install("--check")
        self.assertIn("codex skill (empty plugin)", self.missing_line(out))

    def test_check_reports_the_antigravity_plugin(self):
        self.link_everything()
        plugin = self.home / "agy-plugins" / "fast-ios-device-test"
        plugin.mkdir(parents=True)
        _, out = self.run_install("--check")
        self.assertIn("antigravity skill (empty plugin)", self.missing_line(out))
        (plugin / "skills" / "fast-ios-device-test").mkdir(parents=True)
        (plugin / "skills" / "fast-ios-device-test" / "SKILL.md").write_text("x")
        _, out = self.run_install("--check")
        self.assertIn("antigravity=plugin", out)
        self.assertNotIn("antigravity", self.missing_line(out))

    def test_default_antigravity_dir_is_the_one_agy_reads(self):
        source = (REPO / "install.sh").read_text()
        self.assertIn('$HOME/.gemini/config/skills', source)
        self.assertNotIn("antigravity-cli/skills", source)

    def test_pin_matches_vendored_archive_and_install_axe_ignores_path_copy(self):
        pin = json.loads((REPO / "vendor" / "tools.json").read_text())["axe"]
        archive = REPO / "vendor" / Path(pin["url"]).name
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), pin["sha256"])
        fake = self.home / "path-bin"
        fake.mkdir()
        (fake / "axe").write_text("#!/bin/sh\necho 9.9.9\n")
        (fake / "axe").chmod(0o755)
        self.env["PATH"] = f"{fake}:{os.environ.get('PATH', '')}"
        code, out = self.run_install("--install-axe")
        self.assertEqual(code, 0, out)
        installed = subprocess.run([str(self.home / "axe" / "axe"), "--version"], capture_output=True, text=True)
        self.assertIn(pin["version"], installed.stdout + installed.stderr)
        wrapper = self.dirs["bin"] / "axe"
        self.assertIn(f'exec "{self.home / "axe" / "axe"}"', wrapper.read_text())
        self.link_everything()
        code, out = self.run_install("--check")
        self.assertEqual(code, 0, out)
        self.assertIn(f"axe-pin={pin['version']} installed={pin['version']}", out)
        self.assertEqual(self.missing_line(out), "CHECK OK")

    def test_check_requires_the_local_axe_to_match_the_pin(self):
        self.link_everything()
        local = self.home / "axe" / "axe"
        local.parent.mkdir()
        local.write_text("#!/bin/sh\necho 0.0.1\n")
        local.chmod(0o755)
        wrapper = self.dirs["bin"] / "axe"
        wrapper.write_text(f'#!/bin/sh\nexec "{local}" "$@"\n')
        wrapper.chmod(0o755)
        _, out = self.run_install("--check")
        pinned = json.loads((REPO / "vendor" / "tools.json").read_text())["axe"]["version"]
        self.assertIn(f"axe-pin={pinned} installed=0.0.1", out)
        self.assertIn(f"axe-{pinned}", self.missing_line(out))

    def test_check_passes_without_optional_baguette(self):
        self.link_everything(include_baguette=False)
        self.fake_tool("axe")
        code, out = self.run_install("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("baguette=missing (optional, only fastCarPlayTest; ./install.sh --install-baguette)", out)
        self.assertEqual(self.missing_line(out), "CHECK OK")

    def test_optional_baguette_offline_failure_keeps_install_successful(self):
        calls = []

        def install(name, root, force=False):
            calls.append(name)
            if name == "baguette":
                raise OSError("GitHub is offline")
            return "1.8.0"

        errors = io.StringIO()
        with mock.patch.object(tool_manager, "selected_tools", return_value=["axe", "baguette"]), \
                mock.patch.object(tool_manager, "install_one", side_effect=install), \
                contextlib.redirect_stderr(errors):
            tool_manager.install("all", REPO)
        self.assertEqual(calls, ["axe", "baguette"])
        self.assertIn("note: optional baguette was not installed", errors.getvalue())
        self.assertIn("./install.sh --install-baguette", errors.getvalue())

    def test_install_all_cli_survives_unreachable_baguette_download(self):
        env = dict(self.env, FAST_IOS_INSTALL_TOOLS="baguette",
                   HTTPS_PROXY="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1",
                   NO_PROXY="", no_proxy="")
        ran = subprocess.run(
            ["python3", str(REPO / "scripts" / "tool_manager.py"), "install", "all", "--root", str(REPO)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("note: optional baguette was not installed", ran.stderr)
        self.assertIn("./install.sh --install-baguette", ran.stderr)

    def test_intel_mac_skips_optional_baguette_without_downloading(self):
        errors = io.StringIO()
        with mock.patch.object(tool_manager, "selected_tools", return_value=["baguette"]), \
                mock.patch.object(tool_manager.platform, "machine", return_value="x86_64"), \
                mock.patch.object(tool_manager, "checked_archive") as archive, \
                mock.patch.dict(os.environ, self.env, clear=True), \
                contextlib.redirect_stderr(errors):
            tool_manager.install("all", REPO)
        archive.assert_not_called()
        self.assertIn("not arm64", errors.getvalue())
        self.assertIn("optional baguette", errors.getvalue())

    def test_matching_pin_skips_download_and_force_reinstalls(self):
        pin = json.loads((REPO / "vendor" / "tools.json").read_text())["baguette"]
        local = self.fake_tool("baguette")
        (local.parent / ".fast-ios-pin.json").write_text(json.dumps(pin))
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(tool_manager, "checked_archive") as archive:
            self.assertEqual(tool_manager.install_one("baguette", REPO), pin["version"])
        archive.assert_not_called()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(tool_manager, "checked_archive", side_effect=tool_manager.ToolError("forced")) as archive:
            with self.assertRaisesRegex(tool_manager.ToolError, "forced"):
                tool_manager.install_one("baguette", REPO, force=True)
        archive.assert_called_once()

    def test_baguette_pin_is_download_only_and_generic_installer_preserves_bundle(self):
        pin = json.loads((REPO / "vendor" / "tools.json").read_text())["baguette"]
        self.assertFalse(pin["vendored"])
        self.assertFalse((REPO / "vendor" / Path(pin["url"]).name).exists())
        root = self.home / "fixture-root"
        (root / "vendor").mkdir(parents=True)
        fixture_pin = dict(pin, sha256="0" * 64)
        (root / "vendor" / "tools.json").write_text(json.dumps({
            "axe": json.loads((REPO / "vendor" / "tools.json").read_text())["axe"],
            "baguette": fixture_pin,
        }))
        (root / "vendor" / "baguette-LICENSE").write_text("Apache-2.0 fixture")
        payload = self.home / "payload" / "baguette-v0.2.12-macOS-arm64"
        payload.mkdir(parents=True)
        binary = payload / "Baguette"
        binary.write_text("#!/bin/sh\necho 0.2.12\n")
        binary.chmod(0o755)
        (payload / "Baguette_Baguette.bundle").mkdir()
        (payload / "Baguette_Baguette.bundle" / "resource.txt").write_text("kept")
        archive = self.home / "baguette.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(payload, arcname=payload.name)
        with mock.patch.object(tool_manager, "checked_archive", return_value=(archive, False)), \
                mock.patch.object(tool_manager.platform, "machine", return_value="arm64"), \
                mock.patch.dict(os.environ, self.env, clear=True):
            tool_manager.install_one("baguette", root)
        self.assertEqual((self.home / "baguette" / "Baguette_Baguette.bundle" / "resource.txt").read_text(), "kept")
        self.assertEqual((self.home / "baguette" / "LICENSE").read_text(), "Apache-2.0 fixture")
        self.assertIn("Upstream does not publish a NOTICE", (self.home / "baguette" / "NOTICE").read_text())

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
        codex.symlink_to(self.home / "deleted" / "custom-skill-dir")
        elsewhere = self.home / "my-clone" / "skills" / "fast-ios-device-test"
        elsewhere.mkdir(parents=True)
        antigravity = self.dirs["antigravity"] / "fast-ios-device-test"
        antigravity.symlink_to(elsewhere)
        self.env["PATH"] = f"{self.dirs['bin']}:{os.environ.get('PATH', '')}"
        code, out = self.run_install("--link")
        self.assertEqual(code, 0, out)
        self.assertEqual(Path(os.readlink(codex)), REPO / "skills" / "fast-ios-device-test")
        self.assertEqual(Path(os.readlink(antigravity)), elsewhere)

    @unittest.skipUnless(shutil.which("xcodebuild"), "install needs Xcode")
    def test_plain_install_refuses_to_delete_a_clone_in_the_install_folder(self):
        share = self.home / "share"
        (share / ".git").mkdir(parents=True)
        (share / "keep.txt").write_text("mine")
        self.env["PATH"] = f"{self.dirs['bin']}:{os.environ.get('PATH', '')}"
        code, out = self.run_install()
        self.assertNotEqual(code, 0)
        self.assertIn("is a git clone", out)
        self.assertEqual((share / "keep.txt").read_text(), "mine")

    def test_uninstall_removes_a_relative_link_into_the_copy(self):
        skill = self.home / "share" / "skills" / "fast-ios-device-test"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("x")
        (self.home / "share" / "install.sh").write_text("")
        codex = self.dirs["codex"] / "fast-ios-device-test"
        codex.symlink_to(Path("..") / "share" / "skills" / "fast-ios-device-test")
        self.assertTrue(codex.exists())
        code, out = self.run_install("--uninstall")
        self.assertEqual(code, 0, out)
        self.assertFalse(codex.is_symlink())

    def test_uninstall_removes_a_link_to_the_copy_itself(self):
        share = self.home / "share"
        share.mkdir()
        (share / "install.sh").write_text("")
        (share / "SKILL.md").write_text("x")
        codex = self.dirs["codex"] / "fast-ios-device-test"
        codex.symlink_to(share)
        code, out = self.run_install("--uninstall")
        self.assertEqual(code, 0, out)
        self.assertFalse(codex.is_symlink())

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
