# OpenCode Broad Research-Driven Development (RDD)

A script-gated, OpenCode V2-native **Broad Research-Driven Development** workflow. Before writing application code, it decomposes a technical problem into orthogonal sub-problems, translates terms into mature adjacent domains, dispatches read-only sub-agents across GitHub repos, versioned docs, and academic papers, and deterministically verifies claims, verbatim anchors, and dependency/license compatibility.

## Quick Install via `uv`

Install into any project directory (zero `git clone` required):

```sh
uvx --from git+https://github.com/NedjmeEddine/RDD opencode-rdd install --target .
```

Or install globally into `~/.config/opencode/` (or install persistently with `uv tool install`):

```sh
uvx --from git+https://github.com/NedjmeEddine/RDD opencode-rdd install --global
```

Requirements: **OpenCode V2 (`v2.3+`)** and **Python 3.11+** (scripts use Python stdlib only).

## 4-Phase Workflow

1. **Phase 1 — Recon & Decompose (`research.py init <topic>`)**
   Inspects local manifests, defines binary `## Kill Criteria`, 3–6 orthogonal `## Sub-Problem Axes`, and an `## Adjacent-Domain Translation` table in `.research/<topic>/decomposition.md`, then **stops for human approval** (`research.py approve <topic>`).
2. **Phase 2 — Cross-Domain Fan-Out (`research.py next <topic>`)**
   Dispatches read-only sub-agents (`@research-repos`, `@research-docs`, `@research-papers`) to gather `yaml:claim` evidence with verbatim anchors and concrete receipts.
3. **Phase 3 — Synthesis & Co-Existence Audit (`compat-dryrun.py`)**
   Eliminates candidates failing kill criteria, assigns per-axis verdicts (`ADOPT`, `CLONE_OR_FORK`, `STEAL_PATTERN`, `COMPOSE`, `BUILD`), runs sandboxed `pip`/`npm` dry-runs + transitive license audits (`compat-dryrun.py`), and checks runtime/ownership boundaries.
4. **Phase 4 — Verification & Adversarial Recall (`cite-check.py` + `@research-recall`)**
   Deterministically verifies L1 HTTP + verbatim anchors and L2 registry/arXiv/OpenAlex metadata (`cite-check.py`), challenges winners via `@research-recall`, and writes a `<150`-line `.research/<topic>/INDEX.md`.

## Hard Invariants

- **Scripts own verification status:** LLMs may never write `status:` inside `yaml:claim` blocks (`SCHEMA_ERROR`).
- **Sandboxed compatibility checks:** `compat-dryrun.py` runs in a scrubbed `TemporaryDirectory()` with `pip --only-binary=:all:` and `npm --ignore-scripts`.
- **Read-only toward application code:** Research runs write only under `.research/<topic>/`.

## Running Tests

```sh
python -m unittest discover -s .opencode/skills/research/tests -v
python -m unittest discover -s tests -v
```
