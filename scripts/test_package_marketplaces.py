import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import package_marketplaces


class MarketplacePackageTests(unittest.TestCase):
    def test_builds_clean_provider_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "packages"
            archives = package_marketplaces.build(out)
            self.assertEqual(3, len(archives))
            version = package_marketplaces.read_version()

            expected_roots = {
                "codex": "plugin.json",
                "antigravity": "plugin.json",
                "gemini-cli": "gemini-extension.json",
            }
            for provider, manifest in expected_roots.items():
                archive = out / f"fast-ios-device-test-{provider}-{version}.zip"
                with zipfile.ZipFile(archive) as package:
                    names = set(package.namelist())
                    self.assertIn(manifest, names)
                    self.assertIn("skills/fast-ios-device-test/SKILL.md", names)
                    self.assertIn("skills/fast-ios-device-test-setup/SKILL.md", names)
                    self.assertIn("assets/fast-ios-device-test.png", names)
                    self.assertFalse(any(name.startswith(".agents/") for name in names))
                    self.assertFalse(any(name.startswith(".claude-plugin/") for name in names))

            antigravity_manifest = json.loads(
                (out / "stage" / "antigravity" / "plugin.json").read_text()
            )
            self.assertEqual(version, antigravity_manifest["version"])


if __name__ == "__main__":
    unittest.main()
