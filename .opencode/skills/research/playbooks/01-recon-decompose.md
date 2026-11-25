# Phase 1 Playbook — Fast Recon & Problem Decomposition

## Step 1: Fast Recon
1. Inspect local repository manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`), runtime versions, target OS/platform, and project license.
2. Perform a light initial search to validate problem terminology before locking in axes.

## Step 2: Write `.research/<topic>/decomposition.md`
Include **all three exact headings** below:

- `## Kill Criteria`
  List binary pass/fail constraints (license policy, runtime/OS/WASM restrictions, memory/latency bounds, forbidden dependencies).
- `## Sub-Problem Axes`
  List 3–6 orthogonal technical mechanisms (never the whole app as a monolith), each formatted as:
  `- <axis-slug> | <REVERSIBLE|MODERATE|HARD_TO_REVERSE> | <core question>`
  *(Use lowercase kebab-case for `<axis-slug>`. Default to `MODERATE` when uncertain.)*
- `## Adjacent-Domain Translation`
  Provide a Markdown table mapping each axis to search vocabulary in mature adjacent fields (OS kernels, databases, compilers, game engines, distributed systems, networking) and cross-language ecosystems.

## Step 3: Mandatory Human Gate (STOP)
Present `.research/<topic>/decomposition.md` to the user and **STOP**.
Tell the user to review/edit it and approve before any fan-out begins by running:
- `python .opencode/skills/research/scripts/research.py approve <topic>`
- `python .opencode/skills/research/scripts/research.py next <topic>`
