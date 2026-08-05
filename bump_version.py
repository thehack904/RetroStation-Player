#!/usr/bin/env python3
"""Automate version bumps for RetroStation Player."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

INIT_FILE = Path("retrostation_player/__init__.py")
APP_FILE = Path("retrostation_player/app.py")
CHANGELOG_FILE = Path("CHANGELOG.md")
README_FILE = Path("README.md")


def normalize_version(raw: str) -> tuple[str, str]:
    base = raw.strip().lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+\.\d+", base):
        raise SystemExit(f"Invalid version '{raw}'. Expected format: 0.2.0 or v0.2.0")
    return base, f"v{base}"


def update_init(base_version: str) -> None:
    if not INIT_FILE.exists():
        print(f"[-] {INIT_FILE} not found, skipping")
        return

    text = INIT_FILE.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^__version__\s*=\s*"[^"]*"',
        f'__version__ = "{base_version}"',
        text,
        flags=re.MULTILINE,
    )
    INIT_FILE.write_text(new_text, encoding="utf-8")
    print(f'[+] {INIT_FILE}: set __version__ = "{base_version}" ({count} match{"es" if count != 1 else ""})')


def update_app(base_version: str) -> None:
    if not APP_FILE.exists():
        print(f"[-] {APP_FILE} not found, skipping")
        return

    text = APP_FILE.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^APP_VERSION\s*=\s*"[^"]*"',
        f'APP_VERSION = "{base_version}"',
        text,
        flags=re.MULTILINE,
    )
    APP_FILE.write_text(new_text, encoding="utf-8")
    print(f'[+] {APP_FILE}: set APP_VERSION = "{base_version}" ({count} match{"es" if count != 1 else ""})')


def update_changelog(base_version: str, date_str: str) -> None:
    if not CHANGELOG_FILE.exists():
        print(f"[-] {CHANGELOG_FILE} not found, skipping")
        return

    content = CHANGELOG_FILE.read_text(encoding="utf-8")
    if f"## [{base_version}] - " in content:
        print(f"[=] CHANGELOG.md: section for {base_version} already exists, skipping")
        return

    lines = content.splitlines()
    try:
        insert_at = next(i for i, line in enumerate(lines) if re.match(r"^## \[", line))
    except StopIteration:
        raise SystemExit("Could not find any existing versioned release section in CHANGELOG.md")

    new_block = [
        f"## [{base_version}] - {date_str}",
        "",
        "### Added",
        "- (empty)",
        "",
        "### Changed",
        "- (empty)",
        "",
        "### Fixed",
        "- (empty)",
        "",
        "",
    ]

    updated = lines[:insert_at] + new_block + lines[insert_at:]
    CHANGELOG_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print(f"[+] CHANGELOG.md: inserted section for {base_version} - {date_str}")


def update_readme(v_version: str) -> None:
    if not README_FILE.exists():
        print(f"[-] {README_FILE} not found, skipping")
        return

    text = README_FILE.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"(version-)v\d+\.\d+\.\d+(-blue)",
        rf"\1{v_version}\2",
        text,
    )
    README_FILE.write_text(new_text, encoding="utf-8")
    print(f'[+] README.md: updated version badge ({count} match{"es" if count != 1 else ""})')


def git_commit(v_version: str) -> None:
    tracked_files = [str(path) for path in [INIT_FILE, APP_FILE, CHANGELOG_FILE, README_FILE] if path.exists()]
    if not tracked_files:
        print("[!] No files to add to git")
        return

    try:
        subprocess.run(["git", "add", *tracked_files], check=True)
        subprocess.run(["git", "commit", "-m", f"Bump version to {v_version}"], check=True)
        print("[+] Git commit created")
    except subprocess.CalledProcessError:
        print("[!] Git commit failed")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Bump RetroStation Player version strings.")
    parser.add_argument("new_version", help="Version to set, e.g. 0.2.0 or v0.2.0")
    parser.add_argument("--date", dest="release_date", help="Release date in YYYY-MM-DD format")
    parser.add_argument("--commit", action="store_true", help="Create a git commit after updates")
    args = parser.parse_args(argv[1:])

    base_version, v_version = normalize_version(args.new_version)
    release_date = args.release_date or datetime.today().strftime("%Y-%m-%d")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
        raise SystemExit("Invalid --date format. Expected YYYY-MM-DD")

    print("== RetroStation Player version bump ==")
    print(f"   New version: {v_version}")
    print(f"   Release date: {release_date}")
    print("")

    update_init(base_version)
    update_app(base_version)
    update_changelog(base_version, release_date)
    update_readme(v_version)

    if args.commit:
        git_commit(v_version)


if __name__ == "__main__":
    main(sys.argv)
