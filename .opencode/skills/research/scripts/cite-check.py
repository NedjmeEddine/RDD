#!/usr/bin/env python3
"""Deterministic L1 (HTTP + verbatim anchor) and L2 (registry/paper) claim verifier."""

from __future__ import annotations

import argparse
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import research  # noqa: E402

USER_AGENT = "rdd-cite-check/0.1 (research-verifier)"
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


Fetcher = Callable[[str, float, dict[str, str]], HttpResponse]
SleepFn = Callable[[float], None]


class _TextExtractor(html.parser.HTMLParser):
    """Strip HTML tags/scripts/styles and capture <title> text using stdlib only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        low = tag.lower()
        if low in ("script", "style", "noscript"):
            self._skip_depth += 1
        elif low == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif low == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._skip_depth == 0:
            self.text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_html(content_type: str, body: str) -> bool:
    ct = content_type.lower()
    if "html" in ct:
        return True
    if not ct:
        stripped = body.lstrip()[:256].lower()
        return stripped.startswith("<!doctype html") or stripped.startswith("<html")
    return False


def strip_html(body: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(body)
    parser.close()
    return parser.text, parser.title


def default_fetcher(url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return HttpResponse(status=resp.status, headers=resp_headers, body=body)
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        body = raw.decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return HttpResponse(status=exc.code, headers=resp_headers, body=body)


def make_fixture_fetcher(fixture_path: Path) -> Fetcher:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    counters: dict[str, int] = {}

    def _fetch(url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
        if url not in raw:
            return HttpResponse(status=404, headers={"content-type": "text/plain"}, body="Not in fixture")
        entry = raw[url]
        if isinstance(entry, list):
            idx = counters.get(url, 0)
            counters[url] = idx + 1
            entry = entry[min(idx, len(entry) - 1)]
        resp_headers = {k.lower(): v for k, v in entry.get("headers", {}).items()}
        return HttpResponse(
            status=int(entry.get("status", 200)),
            headers=resp_headers,
            body=str(entry.get("body", "")),
        )

    return _fetch


def fetch_with_retries(
    url: str,
    timeout: float,
    fetcher: Fetcher,
    sleep_fn: SleepFn = time.sleep,
    max_retries: int = 2,
) -> HttpResponse:
    headers = {"User-Agent": USER_AGENT}
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = fetcher(url, timeout, headers)
            if resp.status in RETRYABLE_STATUSES and attempt < max_retries:
                sleep_fn(0.5 * (2**attempt))
                continue
            return resp
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_retries:
                sleep_fn(0.5 * (2**attempt))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def escape_go_module(module_path: str) -> str:
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module_path)


def verify_l2(
    pkg: dict[str, Any],
    timeout: float,
    fetcher: Fetcher,
    sleep_fn: SleepFn = time.sleep,
) -> tuple[str, dict[str, Any] | None, str | None]:
    eco = str(pkg["ecosystem"]).strip()
    name = str(pkg["name"]).strip()
    version = str(pkg.get("version", "")).strip()

    try:
        if eco == "npm":
            url = (
                f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='')}/"
                f"{urllib.parse.quote(version, safe='')}"
            )
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"npm registry returned HTTP {resp.status}"
            data = json.loads(resp.body)
            lic = data.get("license")
            if isinstance(lic, dict):
                lic = lic.get("type")
            return "VERIFIED", {"ecosystem": "npm", "name": name, "version": version, "license": lic}, None

        if eco == "pypi":
            url = (
                f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/"
                f"{urllib.parse.quote(version, safe='')}/json"
            )
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"PyPI returned HTTP {resp.status}"
            data = json.loads(resp.body)
            info = data.get("info", {})
            lic = info.get("license_expression") or info.get("license")
            urls = data.get("urls") or []
            upload_time = urls[0].get("upload_time_iso_8601") if urls and isinstance(urls[0], dict) else None
            return (
                "VERIFIED",
                {
                    "ecosystem": "pypi",
                    "name": name,
                    "version": version,
                    "license": lic,
                    "upload_time": upload_time,
                },
                None,
            )

        if eco == "crates":
            url = (
                f"https://crates.io/api/v1/crates/{urllib.parse.quote(name, safe='')}/"
                f"{urllib.parse.quote(version, safe='')}"
            )
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"crates.io returned HTTP {resp.status}"
            data = json.loads(resp.body)
            ver_obj = data.get("version", data)
            if ver_obj.get("yanked") is True:
                return "REGISTRY_NOT_FOUND", {"yanked": True}, "Crate version is yanked"
            return (
                "VERIFIED",
                {
                    "ecosystem": "crates",
                    "name": name,
                    "version": version,
                    "license": ver_obj.get("license"),
                    "crate_size": ver_obj.get("crate_size"),
                    "yanked": bool(ver_obj.get("yanked", False)),
                },
                None,
            )

        if eco == "go":
            escaped = escape_go_module(name)
            url = f"https://proxy.golang.org/{escaped}/@v/{urllib.parse.quote(version, safe='')}.info"
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"Go module proxy returned HTTP {resp.status}"
            data = json.loads(resp.body)
            return (
                "VERIFIED",
                {
                    "ecosystem": "go",
                    "name": name,
                    "version": data.get("Version", version),
                    "time": data.get("Time"),
                },
                None,
            )

        if eco == "arxiv":
            url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(name, safe='')}"
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"arXiv API returned HTTP {resp.status}"
            root = ET.fromstring(resp.body)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return "REGISTRY_NOT_FOUND", None, f"arXiv entry not found for '{name}'"
            entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            title = normalize_ws(entry.findtext("atom:title", default="", namespaces=ns) or "")
            if not entry_id or name not in entry_id:
                return "REGISTRY_NOT_FOUND", None, f"arXiv entry ID mismatch for '{name}'"
            return "VERIFIED", {"ecosystem": "arxiv", "id": entry_id, "title": title}, None

        if eco == "openalex":
            url = f"https://api.openalex.org/works/{urllib.parse.quote(name, safe='/:')}"
            resp = fetch_with_retries(url, timeout, fetcher, sleep_fn)
            if resp.status != 200:
                return "REGISTRY_NOT_FOUND", None, f"OpenAlex returned HTTP {resp.status}"
            data = json.loads(resp.body)
            return (
                "VERIFIED",
                {
                    "ecosystem": "openalex",
                    "id": data.get("id", name),
                    "title": data.get("title"),
                    "publication_year": data.get("publication_year"),
                    "primary_location": data.get("primary_location"),
                },
                None,
            )

        return "REGISTRY_NOT_FOUND", None, f"Unsupported L2 ecosystem '{eco}'"
    except (json.JSONDecodeError, ET.ParseError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return "REGISTRY_NOT_FOUND", None, f"L2 check failed: {exc}"


def collect_markdown_files(topic_path: Path) -> list[Path]:
    files: list[Path] = []
    sub_dir = topic_path / "subproblems"
    if sub_dir.is_dir():
        files.extend(sorted(p for p in sub_dir.iterdir() if p.is_file() and p.suffix == ".md"))
    index_path = topic_path / "INDEX.md"
    if index_path.is_file():
        files.append(index_path)
    return files


def verify_topic(
    topic_path: Path,
    timeout: float = 15.0,
    fetcher: Fetcher | None = None,
    sleep_fn: SleepFn = time.sleep,
) -> tuple[dict[str, Any], int]:
    active_fetcher = fetcher or default_fetcher

    state_file = topic_path / "state.json"
    topic_name = topic_path.name
    declared_axes: set[str] | None = None
    if state_file.is_file():
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        topic_name = state_data.get("topic", topic_name)
        axes_list = state_data.get("axes")
        if isinstance(axes_list, list) and axes_list:
            declared_axes = {ax["slug"] for ax in axes_list if isinstance(ax, dict) and "slug" in ax}

    md_files = collect_markdown_files(topic_path)
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    has_schema_error = False
    has_verify_failure = False

    for md_path in md_files:
        rel_file = md_path.relative_to(topic_path).as_posix()
        text = md_path.read_text(encoding="utf-8")
        try:
            blocks = research.extract_claim_blocks(text)
        except ValueError as exc:
            has_schema_error = True
            results.append(
                {
                    "id": None,
                    "file": rel_file,
                    "axis": None,
                    "url": None,
                    "http_status": None,
                    "anchor_found": False,
                    "l2_status": "SKIPPED",
                    "l2_metadata": None,
                    "status": "SCHEMA_ERROR",
                    "error": str(exc),
                }
            )
            continue

        for _start_line, block_body in blocks:
            try:
                claim = research.parse_claim_yaml(block_body)
            except ValueError as exc:
                has_schema_error = True
                results.append(
                    {
                        "id": None,
                        "file": rel_file,
                        "axis": None,
                        "url": None,
                        "http_status": None,
                        "anchor_found": False,
                        "l2_status": "SKIPPED",
                        "l2_metadata": None,
                        "status": "SCHEMA_ERROR",
                        "error": str(exc),
                    }
                )
                continue

            cid = claim.get("id") if isinstance(claim.get("id"), str) else None
            axis = claim.get("axis") if isinstance(claim.get("axis"), str) else None
            url = claim.get("url") if isinstance(claim.get("url"), str) else None

            err_code, err_msg = research.validate_claim_dict(claim, declared_axes=declared_axes)
            if err_code is None and cid is not None and cid in seen_ids:
                err_code = "SCHEMA_ERROR"
                err_msg = f"Duplicate claim id '{cid}'"
            if cid is not None:
                seen_ids.add(cid)

            if err_code is not None:
                has_schema_error = True
                results.append(
                    {
                        "id": cid,
                        "file": rel_file,
                        "axis": axis,
                        "url": url,
                        "http_status": None,
                        "anchor_found": False,
                        "l2_status": "SKIPPED",
                        "l2_metadata": None,
                        "status": err_code,
                        "error": err_msg,
                    }
                )
                continue

            assert url is not None
            norm_anchor = normalize_ws(str(claim["anchor"]))
            http_status: int | None = None
            anchor_found = False
            l2_status = "SKIPPED"
            l2_metadata: dict[str, Any] | None = None
            final_status = "VERIFIED"
            error_detail: str | None = None

            try:
                resp = fetch_with_retries(url, timeout, active_fetcher, sleep_fn)
                http_status = resp.status
                if not (200 <= resp.status < 300):
                    final_status = "FETCH_FAILED"
                    error_detail = f"HTTP {resp.status} fetching {url}"
                else:
                    ct = resp.headers.get("content-type", "")
                    if _is_html(ct, resp.body):
                        plain_text, title = strip_html(resp.body)
                    else:
                        plain_text, title = resp.body, ""
                    norm_body = normalize_ws(plain_text)
                    anchor_found = norm_anchor in norm_body

                    low_title = title.lower()
                    if not anchor_found and ("404" in low_title or "page not found" in low_title):
                        final_status = "FETCH_FAILED"
                        error_detail = f"Soft-404 page detected (title: {normalize_ws(title)})"
                    elif not anchor_found:
                        final_status = "ANCHOR_MISMATCH"
                        error_detail = "Verbatim anchor not found in normalized response body"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                final_status = "FETCH_FAILED"
                error_detail = f"Network error fetching {url}: {exc}"

            if final_status == "VERIFIED" and "package" in claim:
                l2_status, l2_metadata, l2_err = verify_l2(claim["package"], timeout, active_fetcher, sleep_fn)
                if l2_status != "VERIFIED":
                    final_status = "REGISTRY_NOT_FOUND"
                    error_detail = l2_err

            if final_status != "VERIFIED":
                has_verify_failure = True

            results.append(
                {
                    "id": cid,
                    "file": rel_file,
                    "axis": axis,
                    "url": url,
                    "http_status": http_status,
                    "anchor_found": anchor_found,
                    "l2_status": l2_status,
                    "l2_metadata": l2_metadata,
                    "status": final_status,
                    "error": error_detail,
                }
            )

    verified_count = sum(1 for item in results if item["status"] == "VERIFIED")
    failed_count = len(results) - verified_count
    payload = {
        "topic": topic_name,
        "checked_at": research.utc_now_iso(),
        "summary": {
            "total": len(results),
            "verified": verified_count,
            "failed": failed_count,
        },
        "claims": results,
    }

    out_path = topic_path / "verification.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if has_schema_error:
        return payload, 2
    if has_verify_failure:
        return payload, 1
    return payload, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify yaml:claim blocks (L1 + anchor + L2)")
    parser.add_argument("topic_dir", help="Path to .research/<topic> directory")
    parser.add_argument("--root", default=None, help="Repository root for resolving relative paths")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds (default: 15)")
    parser.add_argument("--offline-fixture", default=None, help="Optional JSON fixture mapping URLs to responses")
    return parser


def main(argv: list[str] | None = None, fetcher: Fetcher | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    base_root = Path(args.root).resolve() if args.root else Path.cwd()
    raw_topic = Path(args.topic_dir)
    topic_path = raw_topic if raw_topic.is_absolute() else (base_root / raw_topic)
    if not topic_path.is_dir():
        print(f"Error: topic directory not found: {topic_path}", file=sys.stderr)
        return 2

    active_fetcher = fetcher
    if active_fetcher is None and args.offline_fixture:
        fix_raw = Path(args.offline_fixture)
        fix_path = fix_raw if fix_raw.is_absolute() else (base_root / fix_raw)
        if not fix_path.is_file():
            print(f"Error: offline fixture not found: {fix_path}", file=sys.stderr)
            return 2
        active_fetcher = make_fixture_fetcher(fix_path)

    payload, exit_code = verify_topic(topic_path, timeout=args.timeout, fetcher=active_fetcher)
    s = payload["summary"]
    print(
        f"Verified {s['verified']}/{s['total']} claims for '{payload['topic']}' "
        f"(failed: {s['failed']}). Wrote {topic_path / 'verification.json'}."
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
