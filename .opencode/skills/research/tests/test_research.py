#!/usr/bin/env python3
"""Offline unit tests for research.py state machine and phase gates."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import research  # noqa: E402


VALID_DECOMP = """# Topic Decomposition

## Kill Criteria
- Must support Python 3.11+ stdlib only.

## Sub-Problem Axes
- storage-layout | MODERATE | How should research artifacts be organized on disk?
- http-client | REVERSIBLE | Which HTTP client mechanism fits best?

## Adjacent-Domain Translation
| Axis | Adjacent Field | Terms |
|---|---|---|
| storage-layout | Databases | WAL, manifest |
| http-client | Networking | retry, backoff |
"""


def make_dossier(axis: str, claim_id: str, extra: str = "", omit_receipt: bool = False) -> str:
    receipt_line = "" if omit_receipt else 'receipt: "docs:2026-10"\n'
    return (
        f"# Dossier for {axis}\n\n"
        "```yaml:claim\n"
        f"id: {claim_id}\n"
        f"axis: {axis}\n"
        f'claim: "Verbatim evidence claim for {axis}."\n'
        'url: "https://example.com/docs"\n'
        'anchor: "Verbatim evidence anchor text"\n'
        f"{receipt_line}"
        f"{extra}"
        "```\n"
    )


class ResearchStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _run(self, *args: str) -> int:
        return research.main(["--root", str(self.root), *args])

    def _topic_dir(self, topic: str = "demo-topic") -> Path:
        return self.root / ".research" / topic

    def _state(self, topic: str = "demo-topic") -> dict:
        return json.loads((self._topic_dir(topic) / "state.json").read_text(encoding="utf-8"))

    def test_init_invalid_slug_exits_2(self) -> None:
        rc = self._run("init", "Bad_Slug!")
        self.assertEqual(rc, 2)

    def test_phase1_requires_approval(self) -> None:
        self.assertEqual(self._run("init", "demo-topic"), 0)
        (self._topic_dir() / "decomposition.md").write_text(VALID_DECOMP, encoding="utf-8")

        # Must block Phase 1 -> 2 before approve
        self.assertEqual(self._run("next", "demo-topic"), 1)
        self.assertEqual(self._state()["current_phase"], 1)

        # Approve and advance
        self.assertEqual(self._run("approve", "demo-topic"), 0)
        state = self._state()
        self.assertTrue(state["decomposition_approved"])
        self.assertEqual(len(state["axes"]), 2)

        self.assertEqual(self._run("next", "demo-topic"), 0)
        self.assertEqual(self._state()["current_phase"], 2)

    def test_approve_fails_on_missing_heading(self) -> None:
        self.assertEqual(self._run("init", "demo-topic"), 0)
        (self._topic_dir() / "decomposition.md").write_text("## Kill Criteria\n- None\n", encoding="utf-8")
        self.assertEqual(self._run("approve", "demo-topic"), 1)

    def test_phase2_blocks_missing_receipt_and_forbidden_status(self) -> None:
        self.assertEqual(self._run("init", "demo-topic"), 0)
        (self._topic_dir() / "decomposition.md").write_text(VALID_DECOMP, encoding="utf-8")
        self.assertEqual(self._run("approve", "demo-topic"), 0)
        self.assertEqual(self._run("next", "demo-topic"), 0)

        sub = self._topic_dir() / "subproblems"
        # Missing receipt on storage-layout
        (sub / "01-storage-layout.md").write_text(
            make_dossier("storage-layout", "C01", omit_receipt=True), encoding="utf-8"
        )
        (sub / "02-http-client.md").write_text(
            make_dossier("http-client", "C02"), encoding="utf-8"
        )
        self.assertEqual(self._run("next", "demo-topic"), 1)

        # Forbidden status key on storage-layout
        (sub / "01-storage-layout.md").write_text(
            make_dossier("storage-layout", "C01", extra="status: VERIFIED\n"), encoding="utf-8"
        )
        self.assertEqual(self._run("next", "demo-topic"), 1)

    def test_phase2_escalate_upgrades_axis_to_hard_to_reverse(self) -> None:
        self.assertEqual(self._run("init", "demo-topic"), 0)
        (self._topic_dir() / "decomposition.md").write_text(VALID_DECOMP, encoding="utf-8")
        self.assertEqual(self._run("approve", "demo-topic"), 0)
        self.assertEqual(self._run("next", "demo-topic"), 0)

        sub = self._topic_dir() / "subproblems"
        (sub / "01-storage-layout.md").write_text(
            make_dossier("storage-layout", "C01", extra="escalate: true\n"), encoding="utf-8"
        )
        (sub / "02-http-client.md").write_text(
            make_dossier("http-client", "C02"), encoding="utf-8"
        )

        self.assertEqual(self._run("next", "demo-topic"), 0)
        state = self._state()
        self.assertEqual(state["current_phase"], 3)
        axes = {a["slug"]: a for a in state["axes"]}
        self.assertEqual(axes["storage-layout"]["reversibility"], "HARD_TO_REVERSE")
        self.assertEqual(axes["http-client"]["reversibility"], "REVERSIBLE")

    def test_phase3_requires_compat_json_for_adopt_or_compose(self) -> None:
        self._advance_to_phase_3()
        (self._topic_dir() / "synthesis.md").write_text(
            "| Axis | Verdict |\n|---|---|\n| storage-layout | BUILD |\n| http-client | ADOPT |\n",
            encoding="utf-8",
        )
        # Missing compat.json must block Phase 3 -> 4
        self.assertEqual(self._run("next", "demo-topic"), 1)

        (self._topic_dir() / "compat.json").write_text('{"status": "RESOLVES"}\n', encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 0)
        self.assertEqual(self._state()["current_phase"], 4)

    def test_phase4_blocks_stale_verification_and_oversized_index(self) -> None:
        self._advance_to_phase_4()
        tdir = self._topic_dir()
        dossier = tdir / "subproblems" / "01-storage-layout.md"
        verif_path = tdir / "verification.json"
        verif_payload = {
            "topic": "demo-topic",
            "checked_at": "2026-11-25T12:00:00Z",
            "summary": {"total": 2, "verified": 2, "failed": 0},
            "claims": [
                {"id": "C01", "axis": "storage-layout", "status": "VERIFIED"},
                {"id": "C02", "axis": "http-client", "status": "VERIFIED"},
            ],
        }
        verif_path.write_text(json.dumps(verif_payload), encoding="utf-8")
        # Force verification.json mtime older than dossier
        dossier_mtime = dossier.stat().st_mtime
        os.utime(verif_path, (dossier_mtime - 10, dossier_mtime - 10))

        valid_index = "# Index\n\n## Recall Check\n- Checked 2 alternative framings.\n"
        (tdir / "INDEX.md").write_text(valid_index, encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 1)

        # Refresh verification.json mtime, but make INDEX.md >= 150 lines
        os.utime(verif_path, (dossier_mtime + 10, dossier_mtime + 10))
        oversized_index = valid_index + ("- filler line\n" * 150)
        (tdir / "INDEX.md").write_text(oversized_index, encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 1)

        # Restore compact INDEX.md -> completes cleanly
        (tdir / "INDEX.md").write_text(valid_index, encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 0)
        self.assertTrue(self._state()["completed"])

    def test_phase4_blocks_unverified_claim_on_adopt_and_missing_recall_check(self) -> None:
        self._advance_to_phase_4()
        tdir = self._topic_dir()
        verif_path = tdir / "verification.json"
        # http-client has verdict ADOPT, so ANCHOR_MISMATCH must block completion
        verif_payload = {
            "topic": "demo-topic",
            "checked_at": "2026-11-25T12:00:00Z",
            "summary": {"total": 2, "verified": 1, "failed": 1},
            "claims": [
                {"id": "C01", "axis": "storage-layout", "status": "VERIFIED"},
                {"id": "C02", "axis": "http-client", "status": "ANCHOR_MISMATCH"},
            ],
        }
        verif_path.write_text(json.dumps(verif_payload), encoding="utf-8")
        (tdir / "INDEX.md").write_text("# Index\n\nNo recall heading here.\n", encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 1)

        # Fix claim to VERIFIED, still missing ## Recall Check -> blocks
        verif_payload["claims"][1]["status"] = "VERIFIED"
        verif_path.write_text(json.dumps(verif_payload), encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 1)

    def test_root_flag_after_subcommand_and_status_json(self) -> None:
        self.assertEqual(research.main(["init", "post-root", "--root", str(self.root)]), 0)
        self.assertEqual(research.main(["status", "post-root", "--json", "--root", str(self.root)]), 0)

    def _advance_to_phase_3(self) -> None:
        self.assertEqual(self._run("init", "demo-topic"), 0)
        (self._topic_dir() / "decomposition.md").write_text(VALID_DECOMP, encoding="utf-8")
        self.assertEqual(self._run("approve", "demo-topic"), 0)
        self.assertEqual(self._run("next", "demo-topic"), 0)
        sub = self._topic_dir() / "subproblems"
        (sub / "01-storage-layout.md").write_text(make_dossier("storage-layout", "C01"), encoding="utf-8")
        (sub / "02-http-client.md").write_text(make_dossier("http-client", "C02"), encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 0)

    def _advance_to_phase_4(self) -> None:
        self._advance_to_phase_3()
        (self._topic_dir() / "synthesis.md").write_text(
            "| Axis | Verdict |\n|---|---|\n| storage-layout | BUILD |\n| http-client | ADOPT |\n",
            encoding="utf-8",
        )
        (self._topic_dir() / "compat.json").write_text('{"status": "RESOLVES"}\n', encoding="utf-8")
        self.assertEqual(self._run("next", "demo-topic"), 0)


if __name__ == "__main__":
    unittest.main()
