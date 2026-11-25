#!/usr/bin/env python3
"""State-machine CLI and phase gatekeeper for OpenCode Broad RDD."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOPIC_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REVERSIBILITY_TIERS = {"REVERSIBLE", "MODERATE", "HARD_TO_REVERSE"}
VERDICT_ENUMS = {"ADOPT", "CLONE_OR_FORK", "STEAL_PATTERN", "COMPOSE", "BUILD"}
VALID_ECOSYSTEMS = {"npm", "pypi", "crates", "go", "arxiv", "openalex"}
REQUIRED_DECOMP_HEADINGS = (
    "## Kill Criteria",
    "## Sub-Problem Axes",
    "## Adjacent-Domain Translation",
)
PHASE_PLAYBOOKS = {
    1: "01-recon-decompose.md",
    2: "02-fanout.md",
    3: "03-synthesis-compat.md",
    4: "04-recall-verify.md",
}
CLAIM_FENCE_RE = re.compile(r"^```yaml:claim[ \t]*\r?$", re.MULTILINE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def topic_dir(root: Path, topic: str) -> Path:
    return root / ".research" / topic


def state_path(root: Path, topic: str) -> Path:
    return topic_dir(root, topic) / "state.json"


def load_state(root: Path, topic: str) -> dict[str, Any]:
    path = state_path(root, topic)
    if not path.is_file():
        raise FileNotFoundError(f"Topic '{topic}' not found (missing {path})")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(root: Path, topic: str, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now_iso()
    path = state_path(root, topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def read_playbook(phase: int) -> str:
    filename = PHASE_PLAYBOOKS[phase]
    playbook_path = Path(__file__).resolve().parent.parent / "playbooks" / filename
    if playbook_path.is_file():
        return playbook_path.read_text(encoding="utf-8")
    return f"[Playbook pending creation: {playbook_path}]\n"


def _extract_section(markdown: str, heading: str) -> str | None:
    lines = markdown.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start_idx = idx + 1
            break
    if start_idx is None:
        return None
    end_idx = len(lines)
    for idx in range(start_idx, len(lines)):
        if re.match(r"^##\s+\S", lines[idx]):
            end_idx = idx
            break
    return "\n".join(lines[start_idx:end_idx])


def parse_decomposition(markdown: str) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    for heading in REQUIRED_DECOMP_HEADINGS:
        section = _extract_section(markdown, heading)
        if section is None:
            errors.append(f"Missing required heading: {heading}")
        elif not section.strip():
            errors.append(f"Section '{heading}' is empty")

    axes: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    axes_section = _extract_section(markdown, "## Sub-Problem Axes")
    if axes_section is not None:
        for raw_line in axes_section.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("<!--"):
                continue
            if not (line.startswith("- ") or line.startswith("* ")):
                continue
            parts = [part.strip() for part in line[2:].split("|")]
            if len(parts) < 2:
                errors.append(
                    f"Malformed axis line '{line}': expected '- <slug> | <REVERSIBLE|MODERATE|HARD_TO_REVERSE> | <question>'"
                )
                continue
            slug = parts[0]
            tier = parts[1].upper() if parts[1] else "MODERATE"
            if not TOPIC_SLUG_RE.match(slug):
                errors.append(f"Invalid axis slug '{slug}' (must match ^[a-z0-9]+(-[a-z0-9]+)*$)")
                continue
            if tier not in REVERSIBILITY_TIERS:
                errors.append(
                    f"Invalid reversibility tier '{parts[1]}' for axis '{slug}' "
                    f"(expected one of {sorted(REVERSIBILITY_TIERS)})"
                )
                continue
            if slug in seen_slugs:
                errors.append(f"Duplicate axis slug '{slug}' in decomposition.md")
                continue
            seen_slugs.add(slug)
            axes.append({"slug": slug, "reversibility": tier, "verdict": None})

        if not axes and not errors:
            errors.append("No axes declared under '## Sub-Problem Axes'")
        elif not axes:
            errors.append("At least one valid axis is required under '## Sub-Problem Axes'")

    return axes, errors


def _unquote_scalar(raw: str) -> Any:
    val = raw.strip()
    if not val:
        return ""
    if val[0] in ("|", ">"):
        raise ValueError("Multiline YAML fold operators ('|', '>') are not allowed")
    if val[0] in ("&", "*"):
        raise ValueError("YAML anchors/aliases are not allowed")
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        if len(val) < 2:
            raise ValueError("Unterminated quoted string")
        inner = val[1:-1]
        if val[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    # Strip trailing inline comment separated by whitespace
    comment_match = re.search(r"\s+#", val)
    if comment_match:
        val = val[: comment_match.start()].strip()
    lower = val.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return val


def extract_claim_blocks(markdown: str) -> list[tuple[int, str]]:
    """Return list of (1-based start line, block body) for ```yaml:claim blocks."""
    blocks: list[tuple[int, str]] = []
    lines = markdown.splitlines()
    idx = 0
    while idx < len(lines):
        if re.match(r"^```yaml:claim[ \t]*$", lines[idx]):
            start_line = idx + 1
            body_lines: list[str] = []
            idx += 1
            closed = False
            while idx < len(lines):
                if re.match(r"^```[ \t]*$", lines[idx]):
                    closed = True
                    break
                body_lines.append(lines[idx])
                idx += 1
            if not closed:
                raise ValueError(f"Unclosed yaml:claim block starting at line {start_line}")
            blocks.append((start_line, "\n".join(body_lines)))
        idx += 1
    return blocks


def parse_claim_yaml(block_text: str) -> dict[str, Any]:
    """Parse strict flat-plus-one-nested YAML subset for yaml:claim blocks."""
    result: dict[str, Any] = {}
    current_map_key: str | None = None

    for line_no, raw_line in enumerate(block_text.splitlines(), start=1):
        if "\t" in raw_line:
            raise ValueError(f"Tab indentation not allowed in yaml:claim (line {line_no})")
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            current_map_key = None
            if ":" not in stripped:
                raise ValueError(f"Expected 'key: value' on line {line_no}: {stripped}")
            key, rest = stripped.split(":", 1)
            key = key.strip()
            if not key:
                raise ValueError(f"Empty key on line {line_no}")
            if key in result:
                raise ValueError(f"Duplicate key '{key}' in yaml:claim")
            rest_stripped = rest.strip()
            if not rest_stripped or rest_stripped.startswith("#"):
                result[key] = {}
                current_map_key = key
            else:
                result[key] = _unquote_scalar(rest_stripped)
        else:
            if current_map_key is None or not isinstance(result.get(current_map_key), dict):
                raise ValueError(f"Unexpected indented line {line_no}: {stripped}")
            if ":" not in stripped:
                raise ValueError(f"Expected nested 'key: value' on line {line_no}: {stripped}")
            subkey, rest = stripped.split(":", 1)
            subkey = subkey.strip()
            if not subkey:
                raise ValueError(f"Empty nested key on line {line_no}")
            if subkey in result[current_map_key]:
                raise ValueError(f"Duplicate nested key '{current_map_key}.{subkey}'")
            result[current_map_key][subkey] = _unquote_scalar(rest)

    return result


def validate_claim_dict(data: dict[str, Any], declared_axes: set[str] | None = None) -> tuple[str | None, str | None]:
    """Return (status_code, error_message) or (None, None) if structurally valid."""
    if "status" in data:
        return "SCHEMA_ERROR", "Forbidden 'status' key present in yaml:claim block"

    for field in ("id", "axis", "claim", "url", "anchor"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            return "SCHEMA_ERROR", f"Missing or empty required field '{field}'"

    receipt = data.get("receipt")
    if not isinstance(receipt, str) or not receipt.strip():
        return "MISSING_RECEIPT", "Missing or empty required field 'receipt'"

    anchor = data["anchor"].strip()
    if len(anchor) < 8:
        return "SCHEMA_ERROR", f"Anchor too short ({len(anchor)} chars; minimum is 8)"

    url = data["url"].strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return "SCHEMA_ERROR", f"Invalid URL '{url}' (must start with http:// or https://)"

    if declared_axes is not None and data["axis"].strip() not in declared_axes:
        return "SCHEMA_ERROR", f"Unknown axis '{data['axis']}' (not declared in state.json)"

    if "escalate" in data and not isinstance(data["escalate"], bool):
        return "SCHEMA_ERROR", "Optional field 'escalate' must be boolean true/false"

    if "package" in data:
        pkg = data["package"]
        if not isinstance(pkg, dict):
            return "SCHEMA_ERROR", "'package' must be a nested mapping"
        eco = pkg.get("ecosystem")
        name = pkg.get("name")
        version = pkg.get("version")
        if not isinstance(eco, str) or eco not in VALID_ECOSYSTEMS:
            return "SCHEMA_ERROR", f"Invalid package.ecosystem '{eco}'"
        if not isinstance(name, str) or not name.strip():
            return "SCHEMA_ERROR", "Missing package.name"
        if eco not in {"arxiv", "openalex"}:
            if not isinstance(version, str) or not version.strip():
                return "SCHEMA_ERROR", f"Missing package.version for ecosystem '{eco}'"

    return None, None


def _dossier_matches_axis(filename: str, axis_slug: str) -> bool:
    return bool(re.match(rf"^(?:\d+-)?{re.escape(axis_slug)}\.md$", filename))


def validate_phase_1(tdir: Path, state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    decomp_path = tdir / "decomposition.md"
    if not decomp_path.is_file():
        errors.append(f"Missing {decomp_path}")
        return errors
    _, decomp_errors = parse_decomposition(decomp_path.read_text(encoding="utf-8"))
    errors.extend(decomp_errors)
    if not state.get("decomposition_approved"):
        errors.append("Decomposition has not been approved yet; run 'research.py approve <topic>' first.")
    return errors


def validate_phase_2(tdir: Path, state: dict[str, Any]) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    escalated_axes: set[str] = set()
    sub_dir = tdir / "subproblems"
    if not sub_dir.is_dir():
        return [f"Missing subproblems directory: {sub_dir}"], escalated_axes

    dossier_files = sorted(p for p in sub_dir.iterdir() if p.is_file() and p.suffix == ".md")
    if not dossier_files:
        return [f"No dossier .md files found in {sub_dir}"], escalated_axes

    declared_axes = {ax["slug"] for ax in state.get("axes", [])}
    seen_claim_ids: set[str] = set()
    axes_with_claims: set[str] = set()

    for md_path in dossier_files:
        text = md_path.read_text(encoding="utf-8")
        try:
            blocks = extract_claim_blocks(text)
        except ValueError as exc:
            errors.append(f"{md_path.name}: {exc}")
            continue
        if not blocks:
            errors.append(f"{md_path.name}: dossier must contain at least one yaml:claim block")
            continue
        for start_line, block_body in blocks:
            try:
                parsed = parse_claim_yaml(block_body)
            except ValueError as exc:
                errors.append(f"{md_path.name}:{start_line}: {exc}")
                continue
            err_code, err_msg = validate_claim_dict(parsed, declared_axes)
            if err_code is not None:
                errors.append(f"{md_path.name}:{start_line}: [{err_code}] {err_msg}")
                continue
            cid = parsed["id"].strip()
            if cid in seen_claim_ids:
                errors.append(f"{md_path.name}:{start_line}: Duplicate claim id '{cid}'")
                continue
            seen_claim_ids.add(cid)
            axis = parsed["axis"].strip()
            axes_with_claims.add(axis)
            if parsed.get("escalate") is True:
                escalated_axes.add(axis)

    for slug in sorted(declared_axes):
        has_file = any(_dossier_matches_axis(p.name, slug) for p in dossier_files)
        if not has_file:
            errors.append(f"Missing dossier file under subproblems/ for declared axis '{slug}'")
        elif slug not in axes_with_claims:
            errors.append(f"No valid yaml:claim block recorded for axis '{slug}'")

    return errors, escalated_axes


def parse_synthesis_verdicts(tdir: Path, declared_axes: list[str]) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    verdicts: dict[str, str] = {}
    candidates = [tdir / "synthesis.md", tdir / "INDEX.md"]
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return verdicts, ["Missing synthesis.md or INDEX.md draft with per-axis verdicts"]

    axis_set = set(declared_axes)
    for path in existing:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Markdown table row: | axis | VERDICT | ...
            if line.startswith("|"):
                cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
                if len(cells) >= 2 and cells[0] in axis_set:
                    verdict = cells[1].upper()
                    if verdict in VERDICT_ENUMS:
                        verdicts[cells[0]] = verdict
                    else:
                        errors.append(f"{path.name}: Invalid verdict '{cells[1]}' for axis '{cells[0]}'")
            # Bullet line: - axis | VERDICT ...
            elif line.startswith("- ") or line.startswith("* "):
                parts = [p.strip().strip("`") for p in line[2:].split("|")]
                if len(parts) >= 2 and parts[0] in axis_set:
                    verdict = parts[1].upper()
                    if verdict in VERDICT_ENUMS:
                        verdicts[parts[0]] = verdict
                    else:
                        errors.append(f"{path.name}: Invalid verdict '{parts[1]}' for axis '{parts[0]}'")

    for slug in declared_axes:
        if slug not in verdicts:
            errors.append(f"Missing valid verdict ({', '.join(sorted(VERDICT_ENUMS))}) for axis '{slug}'")

    return verdicts, errors


def validate_phase_3(tdir: Path, state: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    declared_axes = [ax["slug"] for ax in state.get("axes", [])]
    verdicts, errors = parse_synthesis_verdicts(tdir, declared_axes)
    if any(v in {"ADOPT", "COMPOSE"} for v in verdicts.values()):
        compat_path = tdir / "compat.json"
        if not compat_path.is_file():
            errors.append("compat.json is required when any axis has verdict ADOPT or COMPOSE")
        else:
            try:
                json.loads(compat_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"compat.json is not valid JSON: {exc}")
    return errors, verdicts


def validate_phase_4(tdir: Path, state: dict[str, Any]) -> tuple[list[str], str | None]:
    errors: list[str] = []
    verif_path = tdir / "verification.json"
    checked_at: str | None = None

    if not verif_path.is_file():
        errors.append("Missing verification.json; run cite-check.py first")
    else:
        try:
            verif = json.loads(verif_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"verification.json is invalid JSON: {exc}")
            verif = None

        if isinstance(verif, dict):
            checked_at = verif.get("checked_at")
            verif_mtime = verif_path.stat().st_mtime_ns
            sub_dir = tdir / "subproblems"
            if sub_dir.is_dir():
                for md_path in sorted(sub_dir.iterdir()):
                    if md_path.is_file() and md_path.suffix == ".md":
                        if verif_mtime < md_path.stat().st_mtime_ns:
                            errors.append(
                                f"verification.json is stale (older than {md_path.name}); re-run cite-check.py"
                            )

            strict_axes = {
                ax["slug"]
                for ax in state.get("axes", [])
                if ax.get("verdict") in {"ADOPT", "CLONE_OR_FORK"}
            }
            claims = verif.get("claims", [])
            if not isinstance(claims, list):
                errors.append("verification.json 'claims' must be a list")
            else:
                verified_by_strict_axis: dict[str, int] = {slug: 0 for slug in strict_axes}
                for claim in claims:
                    status = claim.get("status")
                    cid = claim.get("id", "?")
                    axis = claim.get("axis")
                    if status in {"SCHEMA_ERROR", "MISSING_RECEIPT"}:
                        errors.append(f"Claim {cid} has blocking status {status}")
                    if axis in strict_axes:
                        if status == "VERIFIED":
                            verified_by_strict_axis[axis] += 1
                        else:
                            errors.append(
                                f"Axis '{axis}' (verdict ADOPT/CLONE_OR_FORK) has unverified claim {cid} ({status})"
                            )
                for axis, count in verified_by_strict_axis.items():
                    if count == 0:
                        errors.append(
                            f"Axis '{axis}' (verdict ADOPT/CLONE_OR_FORK) has no verified claims in verification.json"
                        )

    index_path = tdir / "INDEX.md"
    if not index_path.is_file():
        errors.append("Missing INDEX.md")
    else:
        index_text = index_path.read_text(encoding="utf-8")
        line_count = len(index_text.splitlines())
        if line_count >= 150:
            errors.append(f"INDEX.md must be under 150 lines (got {line_count})")
        if _extract_section(index_text, "## Recall Check") is None:
            errors.append("INDEX.md is missing required '## Recall Check' section")

    return errors, checked_at


def cmd_init(root: Path, topic: str) -> int:
    if not TOPIC_SLUG_RE.match(topic):
        print(f"Error: invalid topic slug '{topic}' (expected lowercase kebab-case)", file=sys.stderr)
        return 2
    s_path = state_path(root, topic)
    if s_path.exists():
        print(f"Error: topic '{topic}' already exists at {s_path}", file=sys.stderr)
        return 1
    tdir = topic_dir(root, topic)
    (tdir / "subproblems").mkdir(parents=True, exist_ok=True)
    state = {
        "topic": topic,
        "current_phase": 1,
        "completed": False,
        "decomposition_approved": False,
        "approved_at": None,
        "axes": [],
        "last_verification_at": None,
        "updated_at": utc_now_iso(),
    }
    save_state(root, topic, state)
    sys.stdout.write(read_playbook(1))
    return 0


def cmd_approve(root: Path, topic: str) -> int:
    try:
        state = load_state(root, topic)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    decomp_path = topic_dir(root, topic) / "decomposition.md"
    if not decomp_path.is_file():
        print(f"Error: missing {decomp_path}", file=sys.stderr)
        return 1

    axes, errors = parse_decomposition(decomp_path.read_text(encoding="utf-8"))
    if errors:
        for err in errors:
            print(f"Validation error: {err}", file=sys.stderr)
        return 1

    existing_verdicts = {ax["slug"]: ax.get("verdict") for ax in state.get("axes", [])}
    for ax in axes:
        if ax["slug"] in existing_verdicts:
            ax["verdict"] = existing_verdicts[ax["slug"]]

    state["axes"] = axes
    state["decomposition_approved"] = True
    state["approved_at"] = utc_now_iso()
    save_state(root, topic, state)
    print(f"Approved decomposition for '{topic}' ({len(axes)} axes).")
    return 0


def cmd_status(root: Path, topic: str, as_json: bool) -> int:
    try:
        state = load_state(root, topic)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    tdir = topic_dir(root, topic)
    phase = state.get("current_phase", 1)
    blocking: list[str] = []
    if not state.get("completed"):
        if phase == 1:
            blocking = validate_phase_1(tdir, state)
        elif phase == 2:
            blocking, _ = validate_phase_2(tdir, state)
        elif phase == 3:
            blocking, _ = validate_phase_3(tdir, state)
        elif phase == 4:
            blocking, _ = validate_phase_4(tdir, state)

    sub_dir = tdir / "subproblems"
    dossiers = sorted(p.name for p in sub_dir.iterdir() if p.is_file()) if sub_dir.is_dir() else []
    files = {
        "decomposition.md": (tdir / "decomposition.md").is_file(),
        "subproblems": dossiers,
        "compat.json": (tdir / "compat.json").is_file(),
        "verification.json": (tdir / "verification.json").is_file(),
        "INDEX.md": (tdir / "INDEX.md").is_file(),
    }

    payload = {
        "topic": topic,
        "current_phase": phase,
        "completed": state.get("completed", False),
        "decomposition_approved": state.get("decomposition_approved", False),
        "axes": state.get("axes", []),
        "files": files,
        "blocking_errors": blocking,
    }

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Topic: {topic} | Phase: {phase} | Completed: {payload['completed']}")
        print(f"Decomposition approved: {payload['decomposition_approved']}")
        print(f"Axes: {len(payload['axes'])} | Dossiers: {len(dossiers)}")
        if blocking:
            print("Blocking errors:")
            for err in blocking:
                print(f"  - {err}")
        else:
            print("Blocking errors: none")
    return 0


def cmd_next(root: Path, topic: str) -> int:
    try:
        state = load_state(root, topic)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if state.get("completed"):
        print(f"Topic '{topic}' is already completed.")
        return 0

    tdir = topic_dir(root, topic)
    phase = state.get("current_phase", 1)

    if phase == 1:
        errors = validate_phase_1(tdir, state)
        if errors:
            for err in errors:
                print(f"Gate blocked (Phase 1 -> 2): {err}", file=sys.stderr)
            return 1
        state["current_phase"] = 2
        save_state(root, topic, state)
        sys.stdout.write(read_playbook(2))
        return 0

    if phase == 2:
        errors, escalated_axes = validate_phase_2(tdir, state)
        if errors:
            for err in errors:
                print(f"Gate blocked (Phase 2 -> 3): {err}", file=sys.stderr)
            return 1
        for ax in state.get("axes", []):
            if ax["slug"] in escalated_axes:
                ax["reversibility"] = "HARD_TO_REVERSE"
        state["current_phase"] = 3
        save_state(root, topic, state)
        sys.stdout.write(read_playbook(3))
        return 0

    if phase == 3:
        errors, verdicts = validate_phase_3(tdir, state)
        if errors:
            for err in errors:
                print(f"Gate blocked (Phase 3 -> 4): {err}", file=sys.stderr)
            return 1
        for ax in state.get("axes", []):
            if ax["slug"] in verdicts:
                ax["verdict"] = verdicts[ax["slug"]]
        state["current_phase"] = 4
        save_state(root, topic, state)
        sys.stdout.write(read_playbook(4))
        return 0

    if phase == 4:
        errors, checked_at = validate_phase_4(tdir, state)
        if errors:
            for err in errors:
                print(f"Gate blocked (Phase 4 -> Complete): {err}", file=sys.stderr)
            return 1
        if checked_at:
            state["last_verification_at"] = checked_at
        state["completed"] = True
        save_state(root, topic, state)
        print(f"Research topic '{topic}' completed. Review {tdir / 'INDEX.md'}.")
        return 0

    print(f"Error: invalid current_phase '{phase}' in state.json", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=argparse.SUPPRESS,
        help="Repository root directory (defaults to CWD)",
    )

    parser = argparse.ArgumentParser(description="OpenCode Broad RDD state-machine CLI", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", parents=[common], help="Initialize a new research topic")
    p_init.add_argument("topic", help="Topic slug (lowercase kebab-case)")

    p_status = sub.add_parser("status", parents=[common], help="Show topic status and blocking errors")
    p_status.add_argument("topic", help="Topic slug")
    p_status.add_argument("--json", action="store_true", help="Output status as JSON")

    p_approve = sub.add_parser("approve", parents=[common], help="Approve Phase 1 decomposition.md")
    p_approve.add_argument("topic", help="Topic slug")

    p_next = sub.add_parser("next", parents=[common], help="Validate current phase gate and advance")
    p_next.add_argument("topic", help="Topic slug")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_root = getattr(args, "root", None)
    root = Path(raw_root).resolve() if raw_root else Path.cwd()

    if args.command == "init":
        return cmd_init(root, args.topic)
    if args.command == "status":
        return cmd_status(root, args.topic, args.json)
    if args.command == "approve":
        return cmd_approve(root, args.topic)
    if args.command == "next":
        return cmd_next(root, args.topic)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
