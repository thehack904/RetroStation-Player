from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bump_version


class BumpVersionScriptTests(unittest.TestCase):
    def test_normalize_version_accepts_prefix_and_plain(self) -> None:
        base, v = bump_version.normalize_version("0.2.0")
        self.assertEqual(base, "0.2.0")
        self.assertEqual(v, "v0.2.0")

        base2, v2 = bump_version.normalize_version("v1.0.0")
        self.assertEqual(base2, "1.0.0")
        self.assertEqual(v2, "v1.0.0")

    def test_normalize_version_rejects_invalid_values(self) -> None:
        with self.assertRaises(SystemExit):
            bump_version.normalize_version("0.2")

        with self.assertRaises(SystemExit):
            bump_version.normalize_version("not-a-version")

    def test_main_updates_target_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_file = root / "retrostation_player" / "__init__.py"
            app_file = root / "retrostation_player" / "app.py"
            changelog = root / "CHANGELOG.md"
            readme = root / "README.md"

            init_file.parent.mkdir(parents=True)

            init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
            app_file.write_text('APP_VERSION = "0.1.0"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## Unreleased\n\n### Added\n- something\n\n\n## [0.1.0] - 2026-07-19\n\n### Added\n- initial release\n",
                encoding="utf-8",
            )
            readme.write_text(
                '<img src="https://img.shields.io/badge/version-v0.1.0-blue?style=for-the-badge">\n',
                encoding="utf-8",
            )

            with (
                patch.object(bump_version, "INIT_FILE", init_file),
                patch.object(bump_version, "APP_FILE", app_file),
                patch.object(bump_version, "CHANGELOG_FILE", changelog),
                patch.object(bump_version, "README_FILE", readme),
            ):
                bump_version.main(["bump_version.py", "0.2.0", "--date", "2026-08-01"])

            self.assertIn('__version__ = "0.2.0"', init_file.read_text(encoding="utf-8"))
            self.assertIn('APP_VERSION = "0.2.0"', app_file.read_text(encoding="utf-8"))

            changelog_text = changelog.read_text(encoding="utf-8")
            self.assertIn("## [0.2.0] - 2026-08-01", changelog_text)
            self.assertIn("### Added", changelog_text)
            self.assertIn("### Changed", changelog_text)
            self.assertIn("### Fixed", changelog_text)
            # New section should appear before the old one
            self.assertLess(
                changelog_text.index("## [0.2.0]"),
                changelog_text.index("## [0.1.0]"),
            )

            self.assertIn("version-v0.2.0-blue", readme.read_text(encoding="utf-8"))

    def test_changelog_skips_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = root / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## [0.2.0] - 2026-08-01\n\n### Added\n- something\n",
                encoding="utf-8",
            )

            with patch.object(bump_version, "CHANGELOG_FILE", changelog):
                bump_version.update_changelog("0.2.0", "2026-08-01")

            # Should still have only one occurrence of the section
            text = changelog.read_text(encoding="utf-8")
            self.assertEqual(text.count("## [0.2.0] - 2026-08-01"), 1)

    def test_update_init_sets_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_file = Path(tmp) / "__init__.py"
            init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")

            with patch.object(bump_version, "INIT_FILE", init_file):
                bump_version.update_init("0.2.0")

            self.assertEqual(init_file.read_text(encoding="utf-8"), '__version__ = "0.2.0"\n')

    def test_update_app_sets_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app_file = Path(tmp) / "app.py"
            app_file.write_text('APP_VERSION = "0.1.0"\n', encoding="utf-8")

            with patch.object(bump_version, "APP_FILE", app_file):
                bump_version.update_app("0.2.0")

            self.assertEqual(app_file.read_text(encoding="utf-8"), 'APP_VERSION = "0.2.0"\n')

    def test_update_readme_updates_badge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                "![version](https://img.shields.io/badge/version-v0.1.0-blue)\n",
                encoding="utf-8",
            )

            with patch.object(bump_version, "README_FILE", readme):
                bump_version.update_readme("v0.2.0")

            self.assertIn("version-v0.2.0-blue", readme.read_text(encoding="utf-8"))

    def test_missing_files_are_skipped_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_init = root / "retrostation_player" / "__init__.py"
            missing_app = root / "retrostation_player" / "app.py"
            missing_changelog = root / "CHANGELOG.md"
            missing_readme = root / "README.md"

            with (
                patch.object(bump_version, "INIT_FILE", missing_init),
                patch.object(bump_version, "APP_FILE", missing_app),
                patch.object(bump_version, "CHANGELOG_FILE", missing_changelog),
                patch.object(bump_version, "README_FILE", missing_readme),
            ):
                # Should not raise even though files are absent
                bump_version.update_init("0.2.0")
                bump_version.update_app("0.2.0")
                bump_version.update_changelog("0.2.0", "2026-08-01")
                bump_version.update_readme("v0.2.0")


if __name__ == "__main__":
    unittest.main()
