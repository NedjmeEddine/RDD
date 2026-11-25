#!/usr/bin/env python3
"""Sandboxed Layer 1 dependency dry-run resolver and transitive license auditor."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SAFE_ENV_KEYS = (
    "PATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
)
VALID_ECOSYSTEMS = ("pypi", "npm", "go", "crates", "cpp")


@dataclass
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], Path, dict[str, str]], CmdResult]


def build_scrubbed_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    src = os.environ if base_env is None else base_env
    return {k: src[k] for k in SAFE_ENV_KEYS if k in src and src[k]}


def default_runner(cmd: list[str], cwd: Path, env: dict[str, str]) -> CmdResult:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return CmdResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _split_npm_spec(spec: str) -> tuple[str, str]:
    s = spec.strip()
    if s.startswith("@"):
        at_idx = s.find("@", 1)
        if at_idx != -1:
            return s[:at_idx], s[at_idx + 1 :] or "*"
        return s, "*"
    if "@" in s:
        name, ver = s.split("@", 1)
        return name, ver or "*"
    return s, "*"


def _extract_pypi_license(meta: dict[str, Any]) -> str:
    expr = meta.get("license_expression")
    if isinstance(expr, str) and expr.strip() and expr.strip().upper() != "UNKNOWN":
        return expr.strip()

    lic = meta.get("license")
    if isinstance(lic, str) and lic.strip() and lic.strip().upper() != "UNKNOWN":
        first_line = lic.strip().splitlines()[0].strip()
        if len(first_line) <= 120:
            return first_line

    classifiers = meta.get("classifier") or meta.get("classifiers") or []
    lic_classifiers = [
        c.split("::")[-1].strip()
        for c in classifiers
        if isinstance(c, str) and c.startswith("License ::")
    ]
    specific = [c for c in lic_classifiers if c and c.lower() != "osi approved"]
    if specific:
        return ", ".join(specific)
    if lic_classifiers:
        return ", ".join(lic_classifiers)
    return ""


def audit_licenses(
    packages: list[dict[str, Any]],
    forbidden_licenses: list[str],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str]:
    blocked: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []

    for pkg in packages:
        lic = str(pkg.get("license") or "").strip()
        if not lic or lic.upper() == "UNKNOWN":
            unknown.append(pkg)
            continue
        low_lic = lic.lower()
        for forb in forbidden_licenses:
            if forb and forb.lower() in low_lic:
                blocked.append({**pkg, "matched_forbidden": forb})
                break

    if blocked:
        names = ", ".join(f"{p['name']} ({p['license']})" for p in blocked)
        return "LICENSE_BLOCK", blocked, unknown, f"Forbidden license detected: {names}"
    if unknown:
        names = ", ".join(str(p["name"]) for p in unknown)
        return "LICENSE_UNKNOWN", blocked, unknown, f"Missing or UNKNOWN license metadata for: {names}"
    return "RESOLVES", blocked, unknown, f"Resolved {len(packages)} package(s) with permitted licenses"


def _copy_manifest_context(manifest: Path, scratch: Path) -> Path:
    dest = scratch / manifest.name
    shutil.copy2(manifest, dest)
    # Copy companion lockfile if present
    companions = {
        "package.json": ["package-lock.json"],
        "Cargo.toml": ["Cargo.lock"],
        "go.mod": ["go.sum"],
    }
    for companion in companions.get(manifest.name, []):
        comp_src = manifest.parent / companion
        if comp_src.is_file():
            shutil.copy2(comp_src, scratch / companion)
    return dest


def _run_pypi(
    scratch: Path,
    add_specs: list[str],
    manifest_copy: Path | None,
    python_version: str | None,
    env: dict[str, str],
    runner: Runner,
) -> tuple[str, list[dict[str, Any]], str]:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "--dry-run",
        "--ignore-installed",
        "--only-binary=:all:",
        "--report",
        "-",
    ]
    if python_version:
        cmd.extend(["--python-version", python_version])

    req_specs = list(add_specs)
    if manifest_copy is not None:
        if manifest_copy.name == "pyproject.toml":
            data = tomllib.loads(manifest_copy.read_text(encoding="utf-8"))
            deps = data.get("project", {}).get("dependencies", [])
            if isinstance(deps, list):
                req_specs = [str(d) for d in deps] + req_specs
        else:
            cmd.extend(["-r", str(manifest_copy)])

    if not req_specs and manifest_copy is None:
        return "CONFLICT", [], "No packages or manifest specified for pypi dry-run"

    cmd.extend(req_specs)
    res = runner(cmd, scratch, env)
    if res.returncode != 0:
        combined = f"{res.stderr}\n{res.stdout}".lower()
        if any(
            marker in combined
            for marker in ("only-binary", "no matching distribution", "sdist", "source distribution")
        ):
            return (
                "CONFLICT",
                [],
                "sdist build blocked by --only-binary=:all: safety policy",
            )
        detail = (res.stderr or res.stdout).strip().splitlines()
        msg = detail[-1] if detail else f"pip exited {res.returncode}"
        return "CONFLICT", [], f"pip dry-run failed: {msg}"

    try:
        report = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        return "CONFLICT", [], f"Failed to parse pip --report JSON: {exc}"

    packages: list[dict[str, Any]] = []
    for item in report.get("install", []):
        meta = item.get("metadata", {})
        packages.append(
            {
                "name": meta.get("name", ""),
                "version": meta.get("version", ""),
                "license": _extract_pypi_license(meta),
            }
        )
    return "OK", packages, ""


def _run_npm(
    scratch: Path,
    add_specs: list[str],
    manifest_copy: Path | None,
    env: dict[str, str],
    runner: Runner,
) -> tuple[str, list[dict[str, Any]], str]:
    pkg_json_path = scratch / "package.json"
    if manifest_copy is not None and manifest_copy.name == "package.json":
        pkg_data = json.loads(manifest_copy.read_text(encoding="utf-8"))
    else:
        pkg_data = {"name": "rdd-compat-check", "version": "0.0.0", "private": True, "dependencies": {}}

    deps = pkg_data.setdefault("dependencies", {})
    for spec in add_specs:
        name, ver = _split_npm_spec(spec)
        deps[name] = ver
    pkg_json_path.write_text(json.dumps(pkg_data, indent=2) + "\n", encoding="utf-8")

    cmd = ["npm", "install", "--package-lock-only", "--ignore-scripts"]
    res = runner(cmd, scratch, env)
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip().splitlines()
        msg = detail[-1] if detail else f"npm exited {res.returncode}"
        return "CONFLICT", [], f"npm lockfile resolution failed: {msg}"

    lock_path = scratch / "package-lock.json"
    packages: list[dict[str, Any]] = []
    if lock_path.is_file():
        lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
        pkg_map = lock_data.get("packages", {})
        for key, info in pkg_map.items():
            if not key or not isinstance(info, dict):
                continue
            pkg_name = info.get("name") or key.split("node_modules/")[-1]
            lic = info.get("license", "")
            if isinstance(lic, dict):
                lic = lic.get("type", "")
            packages.append(
                {
                    "name": pkg_name,
                    "version": str(info.get("version", "")),
                    "license": str(lic or "").strip(),
                }
            )
        # Fallback for lockfile v1 'dependencies' if 'packages' absent
        if not packages and isinstance(lock_data.get("dependencies"), dict):
            for name, info in lock_data["dependencies"].items():
                if isinstance(info, dict):
                    packages.append(
                        {
                            "name": name,
                            "version": str(info.get("version", "")),
                            "license": str(info.get("license", "") or "").strip(),
                        }
                    )
    elif res.stdout.strip().startswith("{"):
        parsed = json.loads(res.stdout)
        for item in parsed.get("packages", []):
            packages.append(
                {
                    "name": item.get("name", ""),
                    "version": str(item.get("version", "")),
                    "license": str(item.get("license", "") or "").strip(),
                }
            )
    else:
        return "CONFLICT", [], "npm succeeded without producing package-lock.json"

    return "OK", packages, ""


def _run_crates(
    scratch: Path,
    add_specs: list[str],
    manifest_copy: Path | None,
    env: dict[str, str],
    runner: Runner,
) -> tuple[str, list[dict[str, Any]], str]:
    if add_specs:
        return "NOT_CHECKED", [], "Adding new Cargo crates without Cargo.lock requires network resolution (out of V0 dry-run scope)"
    if manifest_copy is None or manifest_copy.name != "Cargo.toml":
        return "NOT_CHECKED", [], "Cargo check requires a Cargo.toml manifest"
    if shutil.which("cargo", path=env.get("PATH")) is None:
        return "NOT_CHECKED", [], "cargo toolchain not found on PATH"

    cmd = ["cargo", "metadata", "--no-deps", "--format-version", "1"]
    res = runner(cmd, scratch, env)
    if res.returncode != 0:
        return "CONFLICT", [], f"cargo metadata failed: {res.stderr.strip()}"
    meta = json.loads(res.stdout)
    packages = [
        {
            "name": p.get("name", ""),
            "version": p.get("version", ""),
            "license": str(p.get("license") or "").strip(),
        }
        for p in meta.get("packages", [])
    ]
    return "OK", packages, ""


def run_compat(
    ecosystem: str,
    add_specs: list[str] | None = None,
    manifest: Path | None = None,
    forbidden_licenses: list[str] | None = None,
    python_version: str | None = None,
    runner: Runner | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    eco = ecosystem.strip().lower()
    adds = list(add_specs or [])
    forb = [f.strip() for f in (forbidden_licenses or []) if f.strip()]
    active_runner = runner or default_runner
    scrubbed_env = build_scrubbed_env(base_env)

    if eco == "cpp":
        payload = {
            "ecosystem": eco,
            "status": "NOT_CHECKED",
            "reason": "C/C++ dependency resolution is out of V0 scope",
            "forbidden_licenses": forb,
            "packages": [],
            "blocked_packages": [],
            "unknown_license_packages": [],
        }
        return payload, 0

    if eco == "go":
        payload = {
            "ecosystem": eco,
            "status": "NOT_CHECKED",
            "reason": "Go module dry-run license audit requires external registry inspection (NOT_CHECKED in V0 sandbox)",
            "forbidden_licenses": forb,
            "packages": [],
            "blocked_packages": [],
            "unknown_license_packages": [],
        }
        return payload, 0

    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = Path(tmpdir)
        manifest_copy = _copy_manifest_context(manifest, scratch) if manifest is not None else None

        if eco == "pypi":
            stage_status, packages, detail = _run_pypi(
                scratch, adds, manifest_copy, python_version, scrubbed_env, active_runner
            )
        elif eco == "npm":
            stage_status, packages, detail = _run_npm(
                scratch, adds, manifest_copy, scrubbed_env, active_runner
            )
        elif eco == "crates":
            stage_status, packages, detail = _run_crates(
                scratch, adds, manifest_copy, scrubbed_env, active_runner
            )
        else:
            stage_status, packages, detail = "NOT_CHECKED", [], f"Unsupported ecosystem '{eco}'"

    if stage_status == "NOT_CHECKED":
        return (
            {
                "ecosystem": eco,
                "status": "NOT_CHECKED",
                "reason": detail,
                "forbidden_licenses": forb,
                "packages": [],
                "blocked_packages": [],
                "unknown_license_packages": [],
            },
            0,
        )

    if stage_status != "OK":
        return (
            {
                "ecosystem": eco,
                "status": "CONFLICT",
                "reason": detail,
                "forbidden_licenses": forb,
                "packages": [],
                "blocked_packages": [],
                "unknown_license_packages": [],
            },
            1,
        )

    final_status, blocked, unknown, reason = audit_licenses(packages, forb)
    exit_code = 0 if final_status == "RESOLVES" else 1
    return (
        {
            "ecosystem": eco,
            "status": final_status,
            "reason": reason,
            "forbidden_licenses": forb,
            "packages": packages,
            "blocked_packages": blocked,
            "unknown_license_packages": unknown,
        },
        exit_code,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sandboxed Layer 1 dependency & license compatibility checker")
    parser.add_argument("--ecosystem", required=True, choices=VALID_ECOSYSTEMS, help="Target ecosystem")
    parser.add_argument("--add", nargs="+", action="extend", default=[], help="Package specs to add")
    parser.add_argument("--manifest", default=None, help="Path to existing manifest file")
    parser.add_argument("--forbidden-licenses", default="", help="Comma-separated forbidden license substrings")
    parser.add_argument("--python-version", default=None, help="Target Python version for pypi dry-run")
    parser.add_argument("--output", default=None, help="Optional output path for compat JSON")
    parser.add_argument("--root", default=None, help="Repository root for resolving relative paths")
    return parser


def main(argv: list[str] | None = None, runner: Runner | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    base_root = Path(args.root).resolve() if args.root else Path.cwd()

    manifest_path: Path | None = None
    if args.manifest:
        raw_m = Path(args.manifest)
        manifest_path = raw_m if raw_m.is_absolute() else (base_root / raw_m)
        if not manifest_path.is_file():
            print(f"Error: manifest not found: {manifest_path}", file=sys.stderr)
            return 2

    forbidden = [s.strip() for s in args.forbidden_licenses.split(",") if s.strip()]
    payload, exit_code = run_compat(
        ecosystem=args.ecosystem,
        add_specs=args.add,
        manifest=manifest_path,
        forbidden_licenses=forbidden,
        python_version=args.python_version,
        runner=runner,
    )

    rendered = json.dumps(payload, indent=2) + "\n"
    if args.output:
        raw_out = Path(args.output)
        out_path = raw_out if raw_out.is_absolute() else (base_root / raw_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")

    sys.stdout.write(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
