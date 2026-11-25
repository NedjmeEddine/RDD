#!/usr/bin/env python3
"""Offline tests for opencode_rdd installer CLI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencode_rdd.cli import install_rdd  # noqa: E402


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_project_install_merges_opencode_json_non_destructively(self) -> None:
        existing = self.root / "opencode.json"
        existing.write_text(
            json.dumps(
                {
                    "model": "example/model",
                    "mcp": {"servers": {"custom": {"type": "local", "command": ["echo", "hi"]}}},
                }
            ),
            encoding="utf-8",
        )
        install_rdd(target=self.root, global_install=False, with_mcp=True)

        self.assertTrue((self.root / ".opencode" / "agents" / "research-repos.md").is_file())
        self.assertTrue((self.root / ".opencode" / "skills" / "research" / "SKILL.md").is_file())
        self.assertTrue((self.root / ".opencode" / "skills" / "research" / "scripts" / "research.py").is_file())

        merged = json.loads(existing.read_text(encoding="utf-8"))
        self.assertEqual(merged["model"], "example/model")
        self.assertIn("custom", merged["mcp"]["servers"])
        self.assertIn("octocode", merged["mcp"]["servers"])
        self.assertIn("context7", merged["mcp"]["servers"])
        self.assertIn("arxiv", merged["mcp"]["servers"])

    def test_global_install_rewrites_script_paths(self) -> None:
        fake_home = self.root / "home"
        install_rdd(global_install=True, with_mcp=True, home_dir=fake_home)

        skill_md = fake_home / ".config" / "opencode" / "skills" / "research" / "SKILL.md"
        self.assertTrue(skill_md.is_file())
        self.assertIn("~/.config/opencode/skills/research/scripts/", skill_md.read_text(encoding="utf-8"))
        self.assertTrue((fake_home / ".config" / "opencode" / "opencode.json").is_file())


if __name__ == "__main__":
    unittest.main()
