import contextlib
import io
import os
import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import xcode_skills


class XcodeSkillExportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.destination = self.root / "skills"

    def fake_xcode(self, version="27.1", skill="app-resizability"):
        app = self.root / f"Xcode {version}.app"
        resources = app / xcode_skills.RESOURCE_SUFFIX
        resources.mkdir(parents=True)
        with (app / "Contents" / "Info.plist").open("wb") as stream:
            plistlib.dump({"CFBundleShortVersionString": version}, stream)
        (resources / f"{skill}.idechatprompttemplate").write_text(
            f"---\nname: {skill}\ndescription: Fake local fixture.\n---\n\n"
            f"# Fixture\n\nRead [idiom](references/idiom-task.md).\n"
        )
        (resources / f"{skill}-ref-idiom-task.md.packaged").write_text("# Fake reference\n")
        return app

    def test_export_rewrites_name_and_copies_references(self):
        app = self.fake_xcode()
        output = xcode_skills.render_skill(app, "app-resizability", self.destination)
        text = (output / "SKILL.md").read_text()
        self.assertIn("name: apple-app-resizability", text)
        self.assertIn(f"Exported from {app} 27.1 — Apple content, not redistributed", text)
        self.assertIn("references/idiom-task.md", text)
        self.assertEqual(
            (output / "references" / "idiom-task.md").read_text(), "# Fake reference\n"
        )
        self.assertTrue((output / xcode_skills.MARKER).is_file())

    def test_export_is_idempotent_and_remove_only_deletes_managed_folder(self):
        app = self.fake_xcode()
        first = xcode_skills.render_skill(app, "app-resizability", self.destination)
        second = xcode_skills.render_skill(app, "app-resizability", self.destination)
        self.assertEqual(first, second)
        self.assertEqual(
            xcode_skills.remove_skill("app-resizability", [self.destination]), [first]
        )
        self.assertFalse(first.exists())
        unmanaged = self.destination / "apple-app-resizability"
        unmanaged.mkdir()
        with self.assertRaisesRegex(xcode_skills.ExportError, "unmanaged"):
            xcode_skills.remove_skill("app-resizability", [self.destination])

    def test_newest_xcode_containing_the_skill_wins(self):
        old = self.fake_xcode("27.1")
        new = self.fake_xcode("27.2")
        other = self.fake_xcode("28.0", "swiftui-specialist")
        with mock.patch.object(xcode_skills, "xcode_candidates", return_value=[old, new, other]):
            self.assertEqual(xcode_skills.choose_xcode("app-resizability"), new)

    def test_list_reports_only_templates_with_agent_skill_frontmatter(self):
        app = self.fake_xcode()
        resources = app / xcode_skills.RESOURCE_SUFFIX
        (resources / "internal.idechatprompttemplate").write_text("internal prompt")
        (resources / "swiftui-specialist.idechatprompttemplate").write_text(
            "---\nname: swiftui-specialist\ndescription: Fixture.\n---\n"
        )
        output = io.StringIO()
        with mock.patch.object(xcode_skills, "choose_xcode", return_value=app), \
                contextlib.redirect_stdout(output):
            self.assertEqual(xcode_skills.main(["--list"]), 0)
        self.assertIn("app-resizability", output.getvalue())
        self.assertIn("swiftui-specialist", output.getvalue())
        self.assertNotIn("internal\n", output.getvalue())

    def test_default_destination_respects_claude_override(self):
        with mock.patch.dict(os.environ, {"CLAUDE_SKILLS_DIR": str(self.destination)}):
            self.assertEqual(xcode_skills.default_destination(), self.destination)


if __name__ == "__main__":
    unittest.main()
