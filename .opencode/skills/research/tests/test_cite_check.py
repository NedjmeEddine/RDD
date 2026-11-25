#!/usr/bin/env python3
"""Offline unit tests for cite-check.py (L1, anchor, retries, and all 6 L2 verifiers)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("cite_check", SCRIPTS_DIR / "cite-check.py")
assert SPEC and SPEC.loader
cite_check = importlib.util.module_from_spec(SPEC)
sys.modules["cite_check"] = cite_check
SPEC.loader.exec_module(cite_check)


def _write_claim_dossier(tdir: Path, filename: str, block: str) -> None:
    sub = tdir / "subproblems"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / filename).write_text(f"# Dossier\n\n```yaml:claim\n{block.strip()}\n```\n", encoding="utf-8")


class CiteCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tdir = Path(self.tmpdir.name) / ".research" / "sample-topic"
        self.tdir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_forbidden_status_key_exits_2_with_schema_error(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-storage.md",
            """
id: C01
axis: storage
claim: "Library X is fast."
url: "https://example.com/libx"
anchor: "Library X documentation"
receipt: "docs:2026-10"
status: VERIFIED
""",
        )
        payload, rc = cite_check.verify_topic(self.tdir, fetcher=lambda *_: cite_check.HttpResponse(200, {}, ""))
        self.assertEqual(rc, 2)
        self.assertEqual(payload["claims"][0]["status"], "SCHEMA_ERROR")

    def test_missing_receipt_exits_2(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-storage.md",
            """
id: C01
axis: storage
claim: "Library X supports WAL."
url: "https://example.com/libx"
anchor: "supports write-ahead logging"
""",
        )
        payload, rc = cite_check.verify_topic(self.tdir, fetcher=lambda *_: cite_check.HttpResponse(200, {}, ""))
        self.assertEqual(rc, 2)
        self.assertEqual(payload["claims"][0]["status"], "MISSING_RECEIPT")

    def test_l1_html_stripping_anchor_match_and_mismatch(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-storage.md",
            """
id: C01
axis: storage
claim: "OPFS SyncAccessHandle is worker-only."
url: "https://example.com/opfs"
anchor: "only available inside dedicated Web Workers"
receipt: "docs:mdn"
""",
        )
        html_ok = (
            "<html><head><title>OPFS</title><style>.x{}</style></head>"
            "<body><script>var ignore='nope';</script>"
            "<p>It is <strong>only   available\n inside</strong> dedicated Web Workers.</p></body></html>"
        )
        payload, rc = cite_check.verify_topic(
            self.tdir,
            fetcher=lambda u, t, h: cite_check.HttpResponse(200, {"content-type": "text/html"}, html_ok),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(payload["claims"][0]["status"], "VERIFIED")
        self.assertTrue(payload["claims"][0]["anchor_found"])

        # Case-sensitive mismatch or absent anchor on 200 page -> exit 1, ANCHOR_MISMATCH
        html_miss = "<html><head><title>OPFS</title></head><body><p>Unrelated text here.</p></body></html>"
        payload2, rc2 = cite_check.verify_topic(
            self.tdir,
            fetcher=lambda u, t, h: cite_check.HttpResponse(200, {"content-type": "text/html"}, html_miss),
        )
        self.assertEqual(rc2, 1)
        self.assertEqual(payload2["claims"][0]["status"], "ANCHOR_MISMATCH")

        # Soft-404 detection
        html_404 = "<html><head><title>404 Page Not Found</title></head><body><p>Missing.</p></body></html>"
        payload3, rc3 = cite_check.verify_topic(
            self.tdir,
            fetcher=lambda u, t, h: cite_check.HttpResponse(200, {"content-type": "text/html"}, html_404),
        )
        self.assertEqual(rc3, 1)
        self.assertEqual(payload3["claims"][0]["status"], "FETCH_FAILED")

    def test_retry_on_429_and_503(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-storage.md",
            """
id: C01
axis: storage
claim: "Retry succeeds on transient error."
url: "https://example.com/retry"
anchor: "transient recovery verified"
receipt: "docs:2026-10"
""",
        )
        attempts = {"n": 0}
        sleeps: list[float] = []

        def flaky_fetcher(url: str, timeout: float, headers: dict[str, str]):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return cite_check.HttpResponse(429, {}, "rate limited")
            if attempts["n"] == 2:
                return cite_check.HttpResponse(503, {}, "unavailable")
            return cite_check.HttpResponse(200, {"content-type": "text/plain"}, "transient recovery verified")

        payload, rc = cite_check.verify_topic(self.tdir, fetcher=flaky_fetcher, sleep_fn=sleeps.append)
        self.assertEqual(rc, 0)
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(sleeps, [0.5, 1.0])
        self.assertEqual(payload["claims"][0]["status"], "VERIFIED")

    def test_all_six_l2_verifiers(self) -> None:
        sub = self.tdir / "subproblems"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "01-all-ecosystems.md").write_text(
            """# All 6 Ecosystems
```yaml:claim
id: C01
axis: pkg
claim: "npm scoped package exists."
url: "https://example.com/npm"
anchor: "npm scoped package anchor"
receipt: "version:1.2.3"
package:
  ecosystem: npm
  name: "@scope/pkg"
  version: 1.2.3
```

```yaml:claim
id: C02
axis: pkg
claim: "pypi package exists."
url: "https://example.com/pypi"
anchor: "pypi httpx anchor text"
receipt: "version:0.27.2"
package:
  ecosystem: pypi
  name: httpx
  version: 0.27.2
```

```yaml:claim
id: C03
axis: pkg
claim: "crates package exists."
url: "https://example.com/crates"
anchor: "crates serde anchor text"
receipt: "version:1.0.210"
package:
  ecosystem: crates
  name: serde
  version: 1.0.210
```

```yaml:claim
id: C04
axis: pkg
claim: "go module escapes uppercase."
url: "https://example.com/go"
anchor: "go Azure module anchor"
receipt: "version:v1.0.0"
package:
  ecosystem: go
  name: "github.com/Azure/go-autorest"
  version: v1.0.0
```

```yaml:claim
id: C05
axis: pkg
claim: "arxiv paper exists."
url: "https://example.com/arxiv"
anchor: "arxiv attention anchor text"
receipt: "arxiv:1706.03762"
package:
  ecosystem: arxiv
  name: "1706.03762"
```

```yaml:claim
id: C06
axis: pkg
claim: "openalex work exists."
url: "https://example.com/openalex"
anchor: "openalex work anchor text"
receipt: "openalex:W2741809807"
package:
  ecosystem: openalex
  name: W2741809807
```
""",
            encoding="utf-8",
        )

        responses = {
            "https://example.com/npm": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "npm scoped package anchor"),
            "https://example.com/pypi": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "pypi httpx anchor text"),
            "https://example.com/crates": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "crates serde anchor text"),
            "https://example.com/go": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "go Azure module anchor"),
            "https://example.com/arxiv": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "arxiv attention anchor text"),
            "https://example.com/openalex": cite_check.HttpResponse(200, {"content-type": "text/plain"}, "openalex work anchor text"),
            "https://registry.npmjs.org/%40scope%2Fpkg/1.2.3": cite_check.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps({"name": "@scope/pkg", "version": "1.2.3", "license": "MIT"})
            ),
            "https://pypi.org/pypi/httpx/0.27.2/json": cite_check.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps({"info": {"license": "BSD-3-Clause"}, "urls": [{"upload_time_iso_8601": "2024-09-03T00:00:00Z"}]})
            ),
            "https://crates.io/api/v1/crates/serde/1.0.210": cite_check.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps({"version": {"license": "MIT OR Apache-2.0", "crate_size": 78000, "yanked": False}})
            ),
            "https://proxy.golang.org/github.com/!azure/go-autorest/@v/v1.0.0.info": cite_check.HttpResponse(
                200, {"content-type": "application/json"}, json.dumps({"Version": "v1.0.0", "Time": "2024-01-01T00:00:00Z"})
            ),
            "https://export.arxiv.org/api/query?id_list=1706.03762": cite_check.HttpResponse(
                200,
                {"content-type": "application/atom+xml"},
                '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1706.03762v7</id><title>Attention Is All You Need</title></entry></feed>',
            ),
            "https://api.openalex.org/works/W2741809807": cite_check.HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"id": "https://openalex.org/W2741809807", "title": "Paper Title", "publication_year": 2017, "primary_location": {"source": {"display_name": "NeurIPS"}}}),
            ),
        }

        def map_fetcher(url: str, timeout: float, headers: dict[str, str]):
            return responses.get(url, cite_check.HttpResponse(404, {}, f"Unexpected URL {url}"))

        payload, rc = cite_check.verify_topic(self.tdir, fetcher=map_fetcher, sleep_fn=lambda _: None)
        self.assertEqual(rc, 0)
        self.assertEqual(payload["summary"], {"total": 6, "verified": 6, "failed": 0})
        self.assertTrue((self.tdir / "verification.json").is_file())

    def test_crates_yanked_fails_with_registry_not_found(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-crate.md",
            """
id: C01
axis: crate
claim: "Old crate version."
url: "https://example.com/crate"
anchor: "crate version documentation"
receipt: "version:0.1.0"
package:
  ecosystem: crates
  name: oldcrate
  version: 0.1.0
""",
        )

        def yanked_fetcher(url: str, timeout: float, headers: dict[str, str]):
            if url == "https://example.com/crate":
                return cite_check.HttpResponse(200, {"content-type": "text/plain"}, "crate version documentation")
            if url == "https://crates.io/api/v1/crates/oldcrate/0.1.0":
                return cite_check.HttpResponse(
                    200, {"content-type": "application/json"}, json.dumps({"version": {"yanked": True, "license": "MIT"}})
                )
            return cite_check.HttpResponse(404, {}, "missing")

        payload, rc = cite_check.verify_topic(self.tdir, fetcher=yanked_fetcher)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["claims"][0]["status"], "REGISTRY_NOT_FOUND")
        self.assertIn("yanked", payload["claims"][0]["error"].lower())

    def test_offline_fixture_cli_flag(self) -> None:
        _write_claim_dossier(
            self.tdir,
            "01-fix.md",
            """
id: C01
axis: fix
claim: "Offline fixture test works."
url: "https://example.com/fix"
anchor: "fixture body verified"
receipt: "docs:fixture"
""",
        )
        fixture_file = Path(self.tmpdir.name) / "fixture.json"
        fixture_file.write_text(
            json.dumps(
                {
                    "https://example.com/fix": {
                        "status": 200,
                        "headers": {"Content-Type": "text/plain"},
                        "body": "fixture body verified here",
                    }
                }
            ),
            encoding="utf-8",
        )
        rc = cite_check.main([str(self.tdir), "--offline-fixture", str(fixture_file)])
        self.assertEqual(rc, 0)
        verif = json.loads((self.tdir / "verification.json").read_text(encoding="utf-8"))
        self.assertEqual(verif["summary"]["verified"], 1)


if __name__ == "__main__":
    unittest.main()
