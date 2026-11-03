"""fast_update (version, once-a-day notice) and `npx fast-ios-device-test update` (npm/install.js).
Nothing here reaches npm: FAST_IOS_LATEST_VERSION stands in for the registry."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fast_update
import tool_manager

REPO = Path(__file__).resolve().parent.parent
DAY = fast_update.DAY


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cache = self.dir / "update.json"
        patcher = mock.patch.dict(os.environ, {"FAST_IOS_UPDATE_CACHE": str(self.cache)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ["FAST_IOS_AXE_UPDATE_CACHE"] = str(self.dir / "axe-update.json")
        os.environ["FAST_IOS_BAGUETTE_UPDATE_CACHE"] = str(self.dir / "baguette-update.json")
        for name in ("FAST_IOS_NO_UPDATE_CHECK", "CI", "FAST_IOS_LATEST_VERSION", "FAST_IOS_LATEST_AXE_VERSION",
                     "FAST_IOS_LATEST_BAGUETTE_VERSION"):
            os.environ.pop(name, None)

    def seed(self, **data):
        self.cache.write_text(json.dumps(data))

    def test_versions_compare_numerically(self):
        self.assertTrue(fast_update.is_newer("2.0.10", "2.0.9"))
        self.assertTrue(fast_update.is_newer("2.1.0", "2.0.3"))
        self.assertFalse(fast_update.is_newer("2.0.3", "2.0.3"))
        self.assertFalse(fast_update.is_newer("1.9.0", "2.0.0"))
        self.assertFalse(fast_update.is_newer(None, "2.0.0"))
        self.assertFalse(fast_update.is_newer("garbage", "2.0.0"))

    def test_newer_version_prints_once_a_day(self):
        self.seed(checked_at=1000, latest="2.0.9")
        line = fast_update.notice(now=1000 + 60, current="2.0.3", spawn=False)
        self.assertEqual(line, "update available: fast-ios-device-test 2.0.3 -> 2.0.9 "
                               "(run: npx fast-ios-device-test update)")
        self.assertIsNone(fast_update.notice(now=1000 + 120, current="2.0.3", spawn=False))
        self.assertIsNotNone(fast_update.notice(now=1000 + 60 + DAY, current="2.0.3", spawn=False))

    def test_same_or_older_version_prints_nothing(self):
        self.seed(checked_at=1000, latest="2.0.3")
        self.assertIsNone(fast_update.notice(now=1001, current="2.0.3", spawn=False))
        self.seed(checked_at=1000, latest="1.0.0")
        self.assertIsNone(fast_update.notice(now=1001, current="2.0.3", spawn=False))

    def test_switched_off_by_environment(self):
        self.seed(checked_at=1000, latest="9.0.0")
        for name in ("FAST_IOS_NO_UPDATE_CHECK", "CI"):
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: "1"}):
                self.assertIsNone(fast_update.notice(now=1001, current="2.0.3", spawn=False))

    def test_refresh_starts_only_when_the_cache_is_a_day_old(self):
        self.seed(checked_at=1000)
        with mock.patch.object(fast_update, "start_refresh") as start:
            fast_update.notice(now=1000 + 60, current="2.0.3")
            start.assert_not_called()
            fast_update.notice(now=1000 + DAY, current="2.0.3")
            fast_update.notice(now=1000 + DAY + 1, current="2.0.3")
        self.assertEqual(start.call_count, 1)

    def test_no_cache_never_raises_and_prints_nothing(self):
        with mock.patch.object(fast_update, "start_refresh"):
            self.assertIsNone(fast_update.notice(now=5, current="2.0.3"))
        self.cache.write_text("not json")
        with mock.patch.object(fast_update, "start_refresh"):
            self.assertIsNone(fast_update.notice(now=5 + DAY, current="2.0.3"))

    def test_refresh_stores_the_latest_version(self):
        with mock.patch.dict(os.environ, {"FAST_IOS_LATEST_VERSION": "3.1.4"}):
            fast_update.refresh()
        self.assertEqual(json.loads(self.cache.read_text())["latest"], "3.1.4")

    def test_tool_latest_is_checked_once_a_day_and_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"FAST_IOS_LATEST_AXE_VERSION": "1.9.0"}):
            self.assertEqual(fast_update.latest_tool_once_a_day("axe", now=1000), ("1.9.0", "github"))
        with mock.patch.dict(os.environ, {"FAST_IOS_LATEST_AXE_VERSION": "2.0.0"}):
            self.assertEqual(fast_update.latest_tool_once_a_day("axe", now=1001), ("1.9.0", "cache"))
        with mock.patch.dict(os.environ, {"FAST_IOS_LATEST_BAGUETTE_VERSION": "0.3.0"}):
            self.assertEqual(fast_update.latest_tool_once_a_day("baguette", now=1000), ("0.3.0", "github"))
        with mock.patch.dict(os.environ, {"FAST_IOS_NO_UPDATE_CHECK": "1"}):
            self.assertEqual(fast_update.latest_tool_once_a_day("axe", now=1002), (None, "disabled"))

    def test_axe_release_selects_the_universal_macos_asset_without_network(self):
        payload = {"tag_name": "v1.9.0", "assets": [{
            "name": "AXe-macOS-v1.9.0-universal.tar.gz",
            "browser_download_url": "https://github.com/cameroncooke/AXe/releases/download/v1.9.0/AXe-macOS-v1.9.0-universal.tar.gz",
        }]}
        self.assertEqual(tool_manager.latest_release("axe", payload), {
            "version": "1.9.0",
            "url": payload["assets"][0]["browser_download_url"],
        })

    def test_baguette_release_selects_prebuilt_arm64_asset_without_network(self):
        payload = {"tag_name": "v0.2.13", "assets": [{
            "name": "baguette_v0.2.13_macOS_arm64.tar.gz",
            "browser_download_url": "https://github.com/tddworks/baguette/releases/download/v0.2.13/baguette_v0.2.13_macOS_arm64.tar.gz",
        }]}
        self.assertEqual(tool_manager.latest_release("baguette", payload), {
            "version": "0.2.13",
            "url": payload["assets"][0]["browser_download_url"],
        })

    def test_axe_status_reports_pin_local_and_newer_release(self):
        pin = self.dir / "tools.json"
        pin.write_text(json.dumps({"axe": {"version": "1.8.0"}}))
        binary = self.dir / "axe"
        binary.write_text("#!/bin/sh\necho 1.8.0\n")
        binary.chmod(0o755)
        env = dict(os.environ, FAST_IOS_LATEST_AXE_VERSION="1.9.0")
        ran = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "fast_update.py"), "--tool-status", "axe", str(pin), str(binary)],
            capture_output=True, text=True, env=env, timeout=30,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertIn("axe-pin=1.8.0 installed=1.8.0 latest=1.9.0", ran.stdout)
        self.assertIn("npx fast-ios-device-test update-axe", ran.stdout)

    def test_status_reads_the_installed_folder(self):
        root = self.dir / "tool"
        root.mkdir()
        (root / "package.json").write_text('{"version": "2.0.1"}')
        env = dict(os.environ, FAST_IOS_LATEST_VERSION="2.0.3")
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "fast_update.py"), "--status", str(root)],
                             capture_output=True, text=True, env=env, timeout=30).stdout
        self.assertIn("version=2.0.1 latest=2.0.3", out)
        self.assertIn("npx fast-ios-device-test update", out)

    def test_engines_print_the_notice_after_a_run(self):
        version = fast_update.installed_version(REPO)
        self.seed(checked_at=10**10, latest="999.0.0")
        env = dict(os.environ, FAST_IOS_UPDATE_CACHE=str(self.cache))
        for script in ("fast_ui.py", "fast_device.py"):
            with self.subTest(script=script):
                self.seed(checked_at=10**10, latest="999.0.0")
                ran = subprocess.run([sys.executable, str(REPO / "scripts" / script), "--help"],
                                     capture_output=True, text=True, env=env, timeout=60)
                self.assertIn(f"update available: fast-ios-device-test {version} -> 999.0.0", ran.stderr)


    def test_concurrent_runs_print_the_notice_once(self):
        self.seed(checked_at=10**10, latest="999.0.0")
        code = ("import fast_update; line = fast_update.notice(now=10**10 + 5, current='1.0.0', spawn=False);"
                "print('LINE' if line else '')")
        env = dict(os.environ, FAST_IOS_UPDATE_CACHE=str(self.cache))
        runs = [subprocess.Popen([sys.executable, "-c", code], cwd=REPO / "scripts", env=env,
                                 stdout=subprocess.PIPE, text=True) for _ in range(8)]
        printed = sum(run.communicate(timeout=60)[0].count("LINE") for run in runs)
        self.assertEqual(printed, 1)

    def test_a_closed_stderr_pipe_keeps_the_exit_code(self):
        self.seed(checked_at=10**10, latest="999.0.0")
        env = dict(os.environ, FAST_IOS_UPDATE_CACHE=str(self.cache))
        run = subprocess.Popen([sys.executable, str(REPO / "scripts" / "fast_ui.py"), "--help"], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        run.stderr.close()
        self.assertEqual(run.wait(timeout=60), 0)

    def test_a_closed_stderr_never_moves_the_notice_to_stdout(self):
        self.seed(checked_at=10**10, latest="999.0.0")
        env = dict(os.environ, FAST_IOS_UPDATE_CACHE=str(self.cache))
        ran = subprocess.run(f'"{sys.executable}" "{REPO / "scripts" / "fast_ui.py"}" --help 2>&-',
                             shell=True, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ran.returncode, 0)
        self.assertNotIn("update available", ran.stdout)


@unittest.skipUnless(shutil.which("node"), "needs node")
class NpmUpdateTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.stubs = self.home / "stubs"
        self.stubs.mkdir()
        self.log = self.home / "calls.log"
        for name in ("codex", "claude", "npx"):
            stub = self.stubs / name
            stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.log}"\n')
            stub.chmod(0o755)
        self.version = json.loads((REPO / "package.json").read_text())["version"]
        self.env = dict(os.environ, HOME=str(self.home),
                        PATH=f"{self.stubs}:{os.environ.get('PATH', '')}",
                        FAST_IOS_BIN_DIR=str(self.home / "bin"),
                        FAST_IOS_INSTALL_DIR=str(self.home / "share"),
                        FAST_IOS_LATEST_VERSION=self.version,
                        FAST_IOS_NO_UPDATE_CHECK="1")
        for name in ("CODEX_HOME", "CODEX_PLUGIN_CACHE", "CLAUDE_PLUGINS_DIR"):
            self.env.pop(name, None)

    def update(self):
        ran = subprocess.run(["node", str(REPO / "npm" / "install.js"), "update"],
                             capture_output=True, text=True, env=self.env, timeout=120)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return ran, calls

    def linked_clone(self):
        clone = self.home / "clone"
        (clone / "scripts").mkdir(parents=True)
        (clone / ".git").mkdir()
        (clone / "scripts" / "fast_ui.py").write_text("")
        (self.home / "bin").mkdir()
        (self.home / "bin" / "fastSimulatorTest").symlink_to(clone / "scripts" / "fast_ui.py")
        return clone

    def test_older_package_hands_over_to_the_latest(self):
        self.env["FAST_IOS_LATEST_VERSION"] = "999.0.0"
        ran, calls = self.update()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(calls, ["npx --yes fast-ios-device-test@999.0.0 update"])

    def test_linked_clone_is_not_overwritten_and_plugins_update(self):
        clone = self.linked_clone()
        skill = self.home / ".codex" / "plugins" / "cache" / "fast-ios-device-test" / "fast-ios-device-test" / "2.0.2" / "skills" / "fast-ios-device-test"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("x")
        plugins = self.home / ".claude" / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "installed_plugins.json").write_text('{"plugins": {"fast-ios-device-test@fast-ios-device-test": []}}')
        ran, calls = self.update()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn(f'git -C "{clone.resolve()}" pull', ran.stdout)
        self.assertFalse((self.home / "share").exists())
        self.assertEqual(calls, ["codex plugin marketplace upgrade fast-ios-device-test",
                                 "codex plugin add fast-ios-device-test@fast-ios-device-test",
                                 "claude plugin update fast-ios-device-test@fast-ios-device-test"])

    def test_a_clone_in_the_install_folder_is_not_overwritten(self):
        share = self.home / "share"
        (share / ".git").mkdir(parents=True)
        (share / "keep.txt").write_text("mine")
        ran, _ = self.update()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("git clone", ran.stdout)
        self.assertEqual((share / "keep.txt").read_text(), "mine")

    def test_a_failed_plugin_update_fails_the_command(self):
        self.linked_clone()
        (self.stubs / "codex").write_text(f'#!/bin/sh\necho "codex $*" >> "{self.log}"\nexit 3\n')
        skill = self.home / ".codex" / "plugins" / "cache" / "fast-ios-device-test" / "p" / "1" / "skills" / "fast-ios-device-test"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("x")
        ran, calls = self.update()
        self.assertEqual(ran.returncode, 1)
        self.assertIn("codex: the plugin update failed", ran.stdout)
        self.assertNotIn("restart Codex", ran.stdout)
        self.assertEqual(calls, ["codex plugin marketplace upgrade fast-ios-device-test"])

    def test_no_plugin_installed_runs_no_agent_command(self):
        self.linked_clone()
        ran, calls = self.update()
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(calls, [])

    def test_update_axe_dispatches_to_the_pinned_installer(self):
        bash = self.stubs / "bash"
        bash.write_text(f'#!/bin/sh\necho "bash $*" >> "{self.log}"\n')
        bash.chmod(0o755)
        ran = subprocess.run(["node", str(REPO / "npm" / "install.js"), "update-axe"],
                             capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [f"bash {REPO / 'install.sh'} --update-axe"])

    def test_update_baguette_and_all_tools_dispatch_to_the_pinned_installer(self):
        bash = self.stubs / "bash"
        bash.write_text(f'#!/bin/sh\necho "bash $*" >> "{self.log}"\n')
        bash.chmod(0o755)
        for command, flag in (("update-baguette", "--update-baguette"), ("update-tools", "--update-tools")):
            with self.subTest(command=command):
                ran = subprocess.run(["node", str(REPO / "npm" / "install.js"), command],
                                     capture_output=True, text=True, env=self.env, timeout=30)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(self.log.read_text().splitlines(), [
            f"bash {REPO / 'install.sh'} --update-baguette",
            f"bash {REPO / 'install.sh'} --update-tools",
        ])

    def test_xcode_skills_dispatches_options_to_the_installer(self):
        bash = self.stubs / "bash"
        bash.write_text(f'#!/bin/sh\necho "bash $*" >> "{self.log}"\n')
        bash.chmod(0o755)
        ran = subprocess.run(
            ["node", str(REPO / "npm" / "install.js"), "xcode-skills", "--list"],
            capture_output=True, text=True, env=self.env, timeout=30,
        )
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertEqual(
            self.log.read_text().splitlines(),
            [f"bash {REPO / 'install.sh'} --xcode-skills --list"],
        )


if __name__ == "__main__":
    unittest.main()
