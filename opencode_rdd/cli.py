#!/usr/bin/env python3
"""Install OpenCode Broad RDD agents, skills, scripts, and MCP config."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


def _bundle_root() -> Path:
    packaged = Path(__file__).resolve().parent / "bundle"
    if packaged.is_dir():
        return packaged
    # Editable / source-tree fallback
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / ".opencode").is_dir():
        return repo_root
    raise FileNotFoundError("Could not locate bundled .opencode assets")


def _ignore_pycache(_directory: str, names: list[str]) -> list[str]:
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc")]


def _merge_opencode_json(config_path: Path, bundle_mcp: dict[str, Any]) -> str:
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        action = "Merged"
    else:
        data = {"$schema": "https://opencode.ai/config.json"}
        action = "Created"

    mcp = data.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError(f"Expected object at 'mcp' in {config_path}")
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"Expected object at 'mcp.servers' in {config_path}")

    for name, cfg in bundle_mcp.items():
        servers[name] = cfg

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"{action} {config_path} (MCP servers: {', '.join(bundle_mcp.keys())})"


def install_rdd(
    target: Path | None = None,
    global_install: bool = False,
    with_mcp: bool = True,
    home_dir: Path | None = None,
) -> list[str]:
    bundle = _bundle_root()
    is_source_layout = (bundle / ".opencode").is_dir()
    src_agents = bundle / ".opencode" / "agents" if is_source_layout else bundle / "agents"
    src_skill = (
        bundle / ".opencode" / "skills" / "research"
        if is_source_layout
        else bundle / "skills" / "research"
    )
    src_opencode_json = bundle / "opencode.json"

    if global_install:
        base_home = home_dir if home_dir is not None else Path.home()
        opencode_dir = base_home / ".config" / "opencode"
        config_dir = opencode_dir
        script_prefix = "~/.config/opencode/skills/research/scripts/"
    else:
        proj = (target or Path.cwd()).resolve()
        opencode_dir = proj / ".opencode"
        config_dir = proj
        script_prefix = None

    dest_agents = opencode_dir / "agents"
    dest_agents.mkdir(parents=True, exist_ok=True)
    for agent_file in sorted(src_agents.glob("research-*.md")):
        shutil.copy2(agent_file, dest_agents / agent_file.name)

    dest_skill = opencode_dir / "skills" / "research"
    dest_skill.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_skill / "SKILL.md", dest_skill / "SKILL.md")
    for subdir in ("playbooks", "scripts"):
        shutil.copytree(
            src_skill / subdir,
            dest_skill / subdir,
            dirs_exist_ok=True,
            ignore=_ignore_pycache,
        )

    if script_prefix is not None:
        # Rewrite project-relative script paths for global ~/.config/opencode installs.
        for md_file in [dest_skill / "SKILL.md", *sorted((dest_skill / "playbooks").glob("*.md"))]:
            text = md_file.read_text(encoding="utf-8")
            updated = text.replace(".opencode/skills/research/scripts/", script_prefix)
            md_file.write_text(updated, encoding="utf-8")

    notes = [
        f"Installed agents to {dest_agents}",
        f"Installed research skill to {dest_skill}",
    ]

    if with_mcp and src_opencode_json.is_file():
        bundle_cfg = json.loads(src_opencode_json.read_text(encoding="utf-8"))
        bundle_servers = bundle_cfg.get("mcp", {}).get("servers", {})
        jsonc_path = config_dir / "opencode.jsonc"
        json_path = config_dir / "opencode.json"
        if jsonc_path.is_file() and not json_path.is_file():
            notes.append(
                f"Skipped {jsonc_path} (JSONC comments cannot be safely auto-merged); "
                f"add mcp.servers ({', '.join(bundle_servers.keys())}) manually."
            )
        else:
            notes.append(_merge_opencode_json(json_path, bundle_servers))

    return notes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenCode Broad RDD installer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inst = sub.add_parser("install", help="Install RDD agents, skill, scripts, and MCP servers")
    loc = p_inst.add_mutually_exclusive_group()
    loc.add_argument("--target", default=".", help="Target project directory (default: CWD)")
    loc.add_argument("--global", dest="is_global", action="store_true", help="Install into ~/.config/opencode/")
    p_inst.add_argument("--no-mcp", action="store_true", help="Skip merging MCP servers into opencode.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "install":
        notes = install_rdd(
            target=Path(args.target),
            global_install=args.is_global,
            with_mcp=not args.no_mcp,
        )
        for line in notes:
            print(line)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
