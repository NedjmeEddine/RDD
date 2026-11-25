#!/usr/bin/env python3
"""Offline unit tests for compat-dryrun.py (sandboxed env, dry-run flags, license audit)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("compat_dryrun", SCRIPTS_DIR / "compat-dryrun.py")
assert SPEC and SPEC.loader
compat = importlib.util.module_from_spec(SPEC)
sys.modules["compat_dryrun"] = compat
SPEC.loader.exec_module(compat)


class CompatDryrunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_scrubbed_env_strips_secrets_and_proxies(self) -> None:
        dirty = {
            "PATH": "/usr/bin",
            "HOME": "/home/tester",
            "GITHUB_TOKEN": "ghp_secret",
            "OPENAI_API_KEY": "sk-secret",
            "NPM_TOKEN": "npm_secret",
            "HTTP_PROXY": "http://user:pass@proxy:8080",
            "SSH_AUTH_SOCK": "/tmp/agent.sock",
        }
        clean = compat.build_scrubbed_env(dirty)
        self.assertEqual(clean, {"PATH": "/usr/bin", "HOME": "/home/tester"})

    def test_pypi_flags_scratch_dir_and_resolves(self) -> None:
        req = self.root / "requirements.txt"
        req.write_text("anyio==4.6.0\n", encoding="utf-8")
        seen: dict = {}

        def fake_runner(cmd: list[str], cwd: Path, env: dict[str, str]):
            seen["cmd"] = cmd
            seen["cwd"] = cwd
            seen["env"] = env
            report = {
                "install": [
                    {"metadata": {"name": "anyio", "version": "4.6.0", "license": "MIT"}},
                    {"metadata": {"name": "httpx", "version": "0.27.2", "license_expression": "BSD-3-Clause"}},
                ]
            }
            return compat.CmdResult(0, json.dumps(report), "")

        payload, rc = compat.run_compat(
            ecosystem="pypi",
            add_specs=["httpx==0.27.2"],
            manifest=req,
            forbidden_licenses=["GPL", "AGPL"],
            python_version="3.11",
            runner=fake_runner,
            base_env={"PATH": "/usr/bin", "GITHUB_TOKEN": "secret"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "RESOLVES")
        self.assertIn("-q", seen["cmd"])
        self.assertIn("--only-binary=:all:", seen["cmd"])
        self.assertIn("--dry-run", seen["cmd"])
        self.assertIn("--ignore-installed", seen["cmd"])
        self.assertIn("--python-version", seen["cmd"])
        self.assertNotIn("GITHUB_TOKEN", seen["env"])
        self.assertNotEqual(seen["cwd"], self.root)

    def test_pypi_sdist_blocked_returns_conflict_without_fallback(self) -> None:
        calls = {"n": 0}

        def fail_sdist(cmd: list[str], cwd: Path, env: dict[str, str]):
            calls["n"] += 1
            return compat.CmdResult(1, "", "ERROR: Could not find a version that satisfies (only-binary=:all:)")

        payload, rc = compat.run_compat(
            ecosystem="pypi",
            add_specs=["sdist-only-pkg"],
            runner=fail_sdist,
        )
        self.assertEqual(rc, 1)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(payload["status"], "CONFLICT")
        self.assertIn("--only-binary=:all:", payload["reason"])

    def test_npm_ignore_scripts_and_scratch_manifest_isolation(self) -> None:
        pkg_json = self.root / "package.json"
        original_text = json.dumps({"name": "app", "dependencies": {"zod": "^3.23.0"}}, indent=2)
        pkg_json.write_text(original_text, encoding="utf-8")
        seen: dict = {}

        def fake_npm(cmd: list[str], cwd: Path, env: dict[str, str]):
            seen["cmd"] = cmd
            seen["cwd"] = cwd
            lock = {
                "packages": {
                    "": {"name": "app"},
                    "node_modules/zod": {"version": "3.23.8", "license": "MIT"},
                    "node_modules/hono": {"version": "4.6.0", "license": "MIT"},
                }
            }
            (cwd / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
            return compat.CmdResult(0, "", "")

        out_path = self.root / "compat.json"
        rc = compat.main(
            [
                "--ecosystem",
                "npm",
                "--manifest",
                str(pkg_json),
                "--add",
                "hono@4.6.0",
                "--forbidden-licenses",
                "GPL,AGPL",
                "--output",
                str(out_path),
            ],
            runner=fake_npm,
        )
        self.assertEqual(rc, 0)
        self.assertIn("--ignore-scripts", seen["cmd"])
        self.assertIn("--package-lock-only", seen["cmd"])
        self.assertEqual(pkg_json.read_text(encoding="utf-8"), original_text)
        self.assertFalse((self.root / "package-lock.json").exists())
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "RESOLVES")

    def test_license_block_and_license_unknown_exit_1(self) -> None:
        def gpl_runner(cmd: list[str], cwd: Path, env: dict[str, str]):
            report = {
                "install": [
                    {"metadata": {"name": "okpkg", "version": "1.0.0", "license": "MIT"}},
                    {"metadata": {"name": "copyleft", "version": "2.0.0", "license": "GPL-3.0-only"}},
                ]
            }
            return compat.CmdResult(0, json.dumps(report), "")

        payload_block, rc_block = compat.run_compat(
            ecosystem="pypi",
            add_specs=["okpkg"],
            forbidden_licenses=["GPL", "AGPL"],
            runner=gpl_runner,
        )
        self.assertEqual(rc_block, 1)
        self.assertEqual(payload_block["status"], "LICENSE_BLOCK")

        def unknown_runner(cmd: list[str], cwd: Path, env: dict[str, str]):
            report = {
                "install": [
                    {"metadata": {"name": "mystery", "version": "0.1.0", "license": "UNKNOWN"}},
                ]
            }
            return compat.CmdResult(0, json.dumps(report), "")

        payload_unk, rc_unk = compat.run_compat(
            ecosystem="pypi",
            add_specs=["mystery"],
            forbidden_licenses=["GPL", "AGPL"],
            runner=unknown_runner,
        )
        self.assertEqual(rc_unk, 1)
        self.assertEqual(payload_unk["status"], "LICENSE_UNKNOWN")

    def test_cpp_always_not_checked(self) -> None:
        payload, rc = compat.run_compat(ecosystem="cpp", add_specs=["fmt"])
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "NOT_CHECKED")
        self.assertIn("V0 scope", payload["reason"])


if __name__ == "__main__":
    unittest.main()
