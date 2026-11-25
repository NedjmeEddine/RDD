# RDD_BUILD_SPEC.md — OpenCode Broad Research-Driven Development System (V0)

> **BUILDER RULES (READ FIRST — MANDATORY)**
> 1. Work **one milestone at a time** (Section 8). Do not skip ahead or one-shot the entire tree.
> 2. Run every verification command listed at the end of a milestone and inspect the actual output before moving to the next milestone.
> 3. If an OpenCode config check or automated test fails, fix it before proceeding.
> 4. **Do NOT implement V1-deferred features** listed in Section 0. Scope discipline is part of the acceptance criteria.
> 5. Never hardcode OS-specific paths (such as `/tmp`) or assume POSIX-only shells; all Python scripts must run cleanly on Windows, macOS, and Linux using Python 3.11+ stdlib.

---

## Section 0: Mission, Scope Boundary & Hard Invariants

### Mission
Build an OpenCode-native, script-gated **Broad Research-Driven Development (RDD)** system under `.opencode/`. Before any application code is written, the system decomposes a technical specification into orthogonal sub-problems, translates terms into mature adjacent domains, fans out read-only sub-agents across GitHub repositories, version-pinned documentation, and academic papers, verifies every claim deterministically via verbatim source anchors and registry APIs, audits package co-existence in a sandboxed dry run, checks recall for missed prior art, and distills the results into a modular knowledge base under `.research/<topic>/`.

### V0 Scope (Build Now)
- **State-machine CLI (`research.py`)** that gates every phase transition and prints the active phase playbook to stdout.
- **Deterministic citation verifier (`cite-check.py`)** supporting L1 HTTP + verbatim substring anchor verification and L2 metadata checks across npm, PyPI, crates.io, Go module proxy, arXiv, and OpenAlex.
- **Sandboxed Layer 1 compatibility checker (`compat-dryrun.py`)** covering `pip`/`uv` and `npm` dry-run resolution plus transitive license auditing.
- **Thin skill entry point (`SKILL.md`)** plus **4 phase playbooks** (`playbooks/01..04-*.md`).
- **4 read-only OpenCode sub-agents** (`research-repos`, `research-docs`, `research-papers`, `research-recall`).
- **Non-destructive MCP wiring** into `opencode.json` / `opencode.jsonc` (Octocode, Context7, arXiv MCP).
- **Automated `unittest` / `pytest` test suite** with positive and negative fixtures proving every gate fails when it should.

### V1 Scope (Explicitly Forbidden in V0 — Do Not Build)
- Dynamic L3 symbol execution or importing downloaded packages into Python/Node runtimes.
- Automatic Layer 3 execution spikes (V0 only outputs a human-opt-in spike proposal template).
- Cross-harness installers for Claude Code, Cursor, or Codex.
- C/C++ dependency resolvers (must explicitly report `NOT_CHECKED`).
- Auto-trigger prompt tuning or background daemons.

### Hard Engineering Invariants
1. **Zero third-party Python dependencies required for scripts:** All scripts in `.opencode/skills/research/scripts/` must run on stock Python 3.11+ standard library (`pathlib`, `tempfile`, `urllib.request`, `subprocess`, `json`, `re`, `html.parser`, `argparse`, `unittest`).
2. **Cross-platform safety:** Always use `pathlib.Path`, `tempfile.TemporaryDirectory()`, `subprocess.run(..., shell=False)`, and explicit UTF-8 encoding (`encoding="utf-8"`). Never hardcode `/tmp` or POSIX shell pipelines.
3. **Zero untrusted code execution:** Never install or import code from newly discovered repositories. Package dry runs must use scrubbed environments, `npm --ignore-scripts`, and `pip --only-binary=:all:`.
4. **Scripts own verification status:** LLMs are forbidden from writing verification status tags (e.g., `VERIFIED`). Agents emit only structured YAML claim records (`claim`, `url`, `anchor`, `receipt`); `cite-check.py` computes and writes all statuses to `verification.json`.
5. **Read-only toward application code:** The skill and its sub-agents may write only under `.research/<topic>/` during a research run.

---

## Section 1: Environment & OpenCode Discovery Gate (Mandatory Step 0)

Before creating or editing any file, run the following read-only probes and save a short summary to `.opencode/skills/research/ENV_PROBE.md` (or print it clearly in your milestone 0 report):

1. **Inspect OpenCode version and active config schema:**
   ```bash
   opencode --version
   opencode debug config
   opencode debug agents
   opencode mcp list
   ```
   - Determine whether this OpenCode installation uses **V1 config syntax** (`permission` object map; `mcp.<name>` with `enabled: true`) or **V2 config syntax** (`permissions` ordered array of `{action, resource, effect}`; updated MCP server keys).
   - Check whether `OPENCODE_CONFIG_DIR` is set in the environment (if set, note that global `~/.config/opencode/` may be skipped).
   - Inspect any existing `opencode.json` or `opencode.jsonc` in the project root so MCP servers are merged non-destructively.
   - **Config safety rule:** Never mix V1 and V2 agent frontmatter keys in the same `.md` file. Avoid `{env:...}` interpolation inside local MCP `environment` blocks unless confirmed valid by `opencode debug config`.

2. **Inspect installed runtimes and helper CLIs:**
   ```bash
   python --version
   pip --version
   uv --version
   npm --version
   npx --version
   gh --version
   ```
   (Record missing optional tools such as `uv` or `gh` rather than failing; scripts must handle fallbacks cleanly.)

3. **Verify current npm package names for MCP servers before editing config:**
   ```bash
   npm view octocode-mcp version
   npm view octocode version
   npm view @octocodeai/mcp version
   npm view @upstash/context7-mcp version
   ```
   Use the verified active package names in Section 7.

---

## Section 2: Target File Tree & Ownership Matrix

Create **only** the following files under `.opencode/` (plus project `opencode.json` / `opencode.jsonc` updates):

```text
.opencode/
├── agents/
│   ├── research-repos.md
│   ├── research-docs.md
│   ├── research-papers.md
│   └── research-recall.md
└── skills/
    └── research/
        ├── SKILL.md
        ├── playbooks/
        │   ├── 01-recon-decompose.md
        │   ├── 02-fanout.md
        │   ├── 03-synthesis-compat.md
        │   └── 04-recall-verify.md
        ├── scripts/
        │   ├── research.py
        │   ├── cite-check.py
        │   └── compat-dryrun.py
        └── tests/
            ├── test_research.py
            ├── test_cite_check.py
            └── test_compat_dryrun.py
```

### Ownership & Naming Constraints
| Path | Role | Hard Constraint |
|---|---|---|
| `.opencode/skills/research/SKILL.md` | Skill entry point | Filename MUST be uppercase `SKILL.md`; frontmatter `name` MUST be `research` (matching parent directory); max 80 lines |
| `.opencode/skills/research/playbooks/01..04-*.md` | Phase playbooks | Never loaded all at once; printed on demand by `research.py` |
| `.opencode/skills/research/scripts/research.py` | State-machine CLI | Gates every phase transition; refuses to advance on failed validation |
| `.opencode/skills/research/scripts/cite-check.py` | Citation & anchor verifier | Parses `yaml:claim` blocks; runs L1 + anchor + L2 checks; writes `verification.json` |
| `.opencode/skills/research/scripts/compat-dryrun.py` | Layer 1 resolver | Sandboxed `pip`/`uv` and `npm` dry-run + transitive license audit |
| `.opencode/agents/research-*.md` | Read-only sub-agents | `mode: subagent`; edit/write denied; pure V1 or pure V2 frontmatter matching Step 0 |
| `.opencode/skills/research/tests/` | Automated test suite | Must cover positive and negative gate cases offline (mocked HTTP / local fixtures) |

### Runtime Output Layout (Created Per Research Topic)
```text
.research/
└── <topic-slug>/
    ├── state.json                  # Owned by research.py
    ├── decomposition.md            # Written in Phase 1, approved by human before Phase 2
    ├── subproblems/
    │   ├── 01-<axis-slug>.md       # Evidence dossier for Axis 1 (with yaml:claim blocks)
    │   └── 02-<axis-slug>.md       # Evidence dossier for Axis 2
    ├── compat.json                 # Written by compat-dryrun.py in Phase 3
    ├── verification.json           # Written by cite-check.py in Phase 4
    └── INDEX.md                    # Distilled <150-line synthesis written in Phase 4
```

---

## Section 3: Canonical Data Contracts & Enums

All scripts, playbooks, and tests MUST obey these exact contracts.

### 3.1 Embedded `yaml:claim` Block Schema
Every factual claim in `.research/<topic>/subproblems/*.md` (and any new claims added to `INDEX.md`) must be recorded in a fenced code block tagged `yaml:claim`. To keep `cite-check.py` 100% stdlib-only, use a strict flat-plus-one-nested YAML subset (no anchors, no multiline fold operators, double-quote any value containing `:` or `#`).

**Required Fields:**
- `id`: Unique claim ID within the topic (e.g., `C01`, `C02`).
- `axis`: Slug matching an axis in `state.json`.
- `claim`: Concise single-line technical claim.
- `url`: Primary source HTTP/HTTPS URL (repo file/issue, docs page, registry, arXiv, or OpenAlex/paper URL).
- `anchor`: Short verbatim substring (12–140 characters) copied directly from the fetched page/API response that proves the claim.
- `receipt`: Concrete tool-call artifact proving real inspection (e.g., `commit:a1b2c3d`, `issue:#412`, `version:2.4.1`, `arxiv:2401.12345`, `openalex:W2741809807`, `docs:2026-10`).

**Optional Fields:**
- `package`: 1-level nested map with `ecosystem` (`npm` | `pypi` | `crates` | `go` | `arxiv` | `openalex`), `name` (or paper ID), and `version` (optional for `arxiv`/`openalex`).
- `escalate`: `true` | `false` (signals orchestrator to bump axis reversibility to `HARD_TO_REVERSE`).

**Forbidden Field:**
- `status`: Agents MUST NEVER write a `status` key. Presence of `status` inside a `yaml:claim` block is a hard `SCHEMA_ERROR`.

#### Valid `yaml:claim` Example
```yaml:claim
id: C01
axis: storage-layout
claim: "OPFS FileSystemSyncAccessHandle is only available inside Dedicated Web Workers."
url: "[https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle](https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle)"
anchor: "only available inside dedicated Web Workers"
receipt: "docs:mdn-fs-sync-handle"
```

#### Valid `yaml:claim` Example with Package Metadata
```yaml:claim
id: C02
axis: http-server
claim: "httpx 0.27.2 supports HTTP/2 via optional h2 dependency."
url: "[https://pypi.org/project/httpx/0.27.2/](https://pypi.org/project/httpx/0.27.2/)"
anchor: "httpx 0.27.2"
receipt: "version:0.27.2"
package:
  ecosystem: pypi
  name: httpx
  version: 0.27.2
```

#### Invalid `yaml:claim` Example (MUST FAIL Validation)
```yaml:claim
id: C99
axis: storage-layout
claim: "Library X is fast and well maintained."
url: "[https://example.com/libx](https://example.com/libx)"
anchor: "fast"
status: VERIFIED
```
*(Must fail with `SCHEMA_ERROR` due to forbidden `status` key and `MISSING_RECEIPT` due to missing `receipt` and overly short/missing anchor rules.)*

### 3.2 Canonical Enums
- **Citation Statuses** (computed by `cite-check.py`):
  `VERIFIED` | `ANCHOR_MISMATCH` | `FETCH_FAILED` | `REGISTRY_NOT_FOUND` | `MISSING_RECEIPT` | `SCHEMA_ERROR`
- **Compatibility Statuses** (computed by `compat-dryrun.py`):
  `RESOLVES` | `CONFLICT` | `LICENSE_BLOCK` | `LICENSE_UNKNOWN` | `NOT_CHECKED`
- **Per-Axis Verdicts:**
  `ADOPT` | `CLONE_OR_FORK` | `STEAL_PATTERN` | `COMPOSE` | `BUILD`
- **Reversibility Tiers:**
  `REVERSIBLE` | `MODERATE` *(default when uncertain)* | `HARD_TO_REVERSE`

### 3.3 `state.json` Schema (Owned by `research.py`)
```json
{
  "topic": "example-topic",
  "current_phase": 1,
  "completed": false,
  "decomposition_approved": false,
  "approved_at": null,
  "axes": [
    {
      "slug": "storage-layout",
      "reversibility": "HARD_TO_REVERSE",
      "verdict": null
    }
  ],
  "last_verification_at": null,
  "updated_at": "2026-11-25T12:00:00Z"
}
```

### 3.4 `verification.json` Schema (Owned by `cite-check.py`)
```json
{
  "topic": "example-topic",
  "checked_at": "2026-11-25T12:15:00Z",
  "summary": {
    "total": 2,
    "verified": 1,
    "failed": 1
  },
  "claims": [
    {
      "id": "C01",
      "file": "subproblems/01-storage-layout.md",
      "axis": "storage-layout",
      "url": "[https://example.com](https://example.com)",
      "http_status": 200,
      "anchor_found": false,
      "l2_status": "SKIPPED",
      "l2_metadata": null,
      "status": "ANCHOR_MISMATCH",
      "error": "Verbatim anchor not found in normalized response body"
    }
  ]
}
```

---

## Section 4: Deterministic Script Specifications

All scripts live in `.opencode/skills/research/scripts/` and support `--root <repo-root>` (defaulting to current working directory) so tests can run cleanly against temporary directories.

### 4.1 `scripts/research.py` (State Machine & Gatekeeper)
**CLI Interface:**
- `python .opencode/skills/research/scripts/research.py init <topic>`
  - Validates `<topic>` slug (`^[a-z0-9]+(-[a-z0-9]+)*$`).
  - Creates `.research/<topic>/` and `.research/<topic>/subproblems/`.
  - Writes initial `state.json` (`current_phase: 1`, `decomposition_approved: false`).
  - Prints `playbooks/01-recon-decompose.md` to stdout.
- `python .opencode/skills/research/scripts/research.py status <topic>`
  - Prints current phase, approval flag, discovered files, and any blocking validation errors as human-readable text (or `--json`).
- `python .opencode/skills/research/scripts/research.py approve <topic>`
  - Validates `decomposition.md` structure (required headings: `## Kill Criteria`, `## Sub-Problem Axes`, `## Adjacent-Domain Translation`).
  - Parses axis slugs and reversibility tiers from `decomposition.md` into `state.json`, sets `decomposition_approved: true`, records `approved_at`.
  - Exits `0` on success, `1` if `decomposition.md` is missing or incomplete.
- `python .opencode/skills/research/scripts/research.py next <topic>`
  - Validates exit criteria for `current_phase`:
    - **Phase 1 → 2:** `decomposition.md` exists, contains required headings, and `state.json["decomposition_approved"]` is `true`. *(MUST exit `1` with clear message if unapproved.)*
    - **Phase 2 → 3:** At least one `.md` file exists under `subproblems/` for each declared axis; every dossier contains at least one syntactically valid `yaml:claim` block with a non-empty `receipt` and no forbidden `status` key. If any claim sets `escalate: true`, automatically upgrades that axis's reversibility in `state.json` to `HARD_TO_REVERSE`.
    - **Phase 3 → 4:** Synthesis/verdicts section exists (either in `INDEX.md` draft or `synthesis.md`) with valid verdict enums for every axis, AND if any axis has verdict `ADOPT` or `COMPOSE`, `compat.json` exists.
    - **Phase 4 → Complete:** `verification.json` exists and its mtime is newer than or equal to all `subproblems/*.md` files; zero claims have `SCHEMA_ERROR` or `MISSING_RECEIPT`; no axis with verdict `ADOPT` or `CLONE_OR_FORK` has failed/unverified claims; `INDEX.md` exists, is under 150 lines, and contains a `## Recall Check` section. Sets `completed: true`.
  - On pass: increments `current_phase` (or marks `completed: true`), persists `state.json`, and prints the next phase playbook to stdout.
  - **Exit Codes:** `0` success, `1` gate validation failed, `2` CLI/usage/missing topic error.

### 4.2 `scripts/cite-check.py` (Deterministic Verifier)
**CLI Interface:**
- `python .opencode/skills/research/scripts/cite-check.py <research-topic-dir> [--timeout 15] [--offline-fixture <json>]`
  - Reads all `.md` files in `<research-topic-dir>` (`INDEX.md` and `subproblems/*.md`), extracts every fenced `yaml:claim` block, validates schema, verifies each claim, and writes `<research-topic-dir>/verification.json`.

**Exact Algorithm:**
1. **Schema Check:** Enforce required fields (`id`, `axis`, `claim`, `url`, `anchor`, `receipt`), reject forbidden `status` key, require `len(anchor.strip()) >= 8`, require unique `id` across the topic. On violation, emit `SCHEMA_ERROR` or `MISSING_RECEIPT`.
2. **L1 Fetch + Verbatim Anchor Match:**
   - HTTP GET `url` with explicit `User-Agent: rdd-cite-check/0.1 (research-verifier)` and timeout.
   - Retry up to 2 times with exponential backoff on HTTP `429` or `5xx`.
   - Reject non-2xx responses and obvious soft-404 pages (e.g., `<title>` containing `404` / `Page not found` when anchor is absent) as `FETCH_FAILED`.
   - Strip HTML tags/scripts/styles via stdlib `html.parser.HTMLParser` when `Content-Type` is HTML (keep raw body for JSON/Markdown/plain text).
   - Normalize whitespace (`re.sub(r"\s+", " ", text).strip()`) on both body and `anchor`, then perform a **case-sensitive substring match**.
   - If the anchor is absent, emit `ANCHOR_MISMATCH`.
3. **L2 Registry / Paper Verification (when `package` block is present):**
   - `npm`: `GET https://registry.npmjs.org/{quote(name, safe='')}/{quote(version)}` — confirm 200, extract `license` and `time` / publish metadata.
   - `pypi`: `GET https://pypi.org/pypi/{quote(name)}/{quote(version)}/json` — confirm 200, extract `info.license` / classifiers and upload time.
   - `crates`: `GET https://crates.io/api/v1/crates/{quote(name)}/{quote(version)}` (polite `User-Agent` required by crates.io) — confirm 200, extract `crate_size`, `license`, `yanked`. If `yanked == true`, flag as failed (`REGISTRY_NOT_FOUND` with error `"Crate version is yanked"`).
   - `go`: Escape uppercase letters in module path (`A` → `!a` per Go module proxy spec) and `GET https://proxy.golang.org/{escaped_mod}/@v/{quote(version)}.info` — confirm 200, extract `Version` and `Time`.
   - `arxiv`: `GET https://export.arxiv.org/api/query?id_list={quote(name)}` — confirm 200 and XML `<entry>` contains matching ID/title.
   - `openalex`: `GET https://api.openalex.org/works/{quote(name)}` (supports Work ID `W...` or DOI) — confirm 200, extract `title`, `publication_year`, `primary_location`.
   - Any 404 or missing version emits `REGISTRY_NOT_FOUND`.
4. **Final Claim Status:** `VERIFIED` if and only if Schema, L1 + Anchor, and L2 (when applicable) all pass.
5. **Exit Codes:** `0` all claims `VERIFIED`; `1` one or more claims failed L1/L2/anchor; `2` schema/parse/CLI error.
6. **Testability:** Inject a pluggable HTTP fetcher (or `--offline-fixture`) so unit tests run deterministically with zero network calls.

### 4.3 `scripts/compat-dryrun.py` (Sandboxed Layer 1 Resolver + License Audit)
**CLI Interface:**
- `python .opencode/skills/research/scripts/compat-dryrun.py --ecosystem <pypi|npm|go|crates|cpp> --add <pkg-spec>... [--manifest <path>] [--forbidden-licenses GPL,AGPL] [--python-version 3.11] [--output <compat.json>]`

**Exact Algorithm & Security Controls:**
1. **Scrubbed Subprocess Environment:** Construct a minimal env dict passing ONLY safe variables (`PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`) — strip tokens, API keys, SSH agents, and proxy credentials.
2. **Scratch Workspace:** Always copy existing manifests (`pyproject.toml`, `requirements.txt`, `package.json`, `package-lock.json`, `go.mod`, `Cargo.toml`) into `tempfile.TemporaryDirectory()`. Never modify the user's real manifests or lockfiles.
3. **Ecosystem Handling:**
   - `pypi`: Prefer `pip install --dry-run --ignore-installed --only-binary=:all: --report -` (passing `--python-version <ver>` if provided). If `pip` fails specifically because no wheel exists for a package, DO NOT fall back to building an sdist automatically—report `CONFLICT` with detail `"sdist build blocked by --only-binary=:all: safety policy"`. Parse JSON report for resolved packages and fetch/inspect license metadata.
   - `npm`: Merge `--add` dependencies into scratch `package.json` and run `npm install --package-lock-only --ignore-scripts --dry-run` (or generate lockfile inside scratch dir with `--package-lock-only --ignore-scripts` and parse resolved tree + licenses).
   - `go` / `crates`: Support scratch manifest copy dry-check where safe (`go list` / `cargo metadata --no-deps` if toolchain present), otherwise report `NOT_CHECKED` with reason.
   - `cpp`: Always emit `NOT_CHECKED` with reason `"C/C++ dependency resolution is out of V0 scope"`.
4. **Transitive License Audit:**
   - Check every newly resolved direct and transitive package against `--forbidden-licenses` (case-insensitive substring match against SPDX expression).
   - If a forbidden license is matched → emit `LICENSE_BLOCK` and exit `1`.
   - If ANY resolved package has missing, empty, or `"UNKNOWN"` license metadata → emit `LICENSE_UNKNOWN` and exit `1` (NEVER silently treat unknown licenses as `RESOLVES`).
   - Only emit `RESOLVES` (exit `0`) when solver succeeds AND all resolved licenses are known and permitted.

---

## Section 5: Skill & Phase Playbook Specifications

### 5.1 `.opencode/skills/research/SKILL.md` (Max 80 Lines)
- Frontmatter MUST include:
  ```yaml
  ---
  name: research
  description: >
    Use when starting unfamiliar or niche technical work, evaluating architecture
    trade-offs, hunting cross-domain prior art across GitHub repos, versioned
    docs, and academic papers, or preventing reinvention before implementation.
  ---
  ```
- Body MUST stay concise:
  1. State the read-only invariant (no application code edits).
  2. Instruct the agent to run `python .opencode/skills/research/scripts/research.py init <topic>` (for a new topic) or `status <topic>` / `next <topic>` (to resume).
  3. Instruct the agent to strictly follow only the playbook printed to stdout by `research.py`, never skipping the Phase 1 human approval gate.

### 5.2 `playbooks/01-recon-decompose.md`
- **Step 1 (Fast Recon):** Inspect local repo manifests, runtime versions, target platform, and license. Do a light initial search to validate problem vocabulary before committing to axes.
- **Step 2 (Write `.research/<topic>/decomposition.md`):** Must include three exact headings:
  - `## Kill Criteria`: Binary pass/fail constraints (license policy, runtime/OS/WASM constraints, memory/latency bounds, forbidden dependencies).
  - `## Sub-Problem Axes`: 3–6 orthogonal technical mechanisms (not the app as a monolith), each formatted as `- <axis-slug> | <REVERSIBLE|MODERATE|HARD_TO_REVERSE> | <core question>`. Default to `MODERATE` when uncertain.
  - `## Adjacent-Domain Translation`: Markdown table mapping each axis to search vocabulary in mature adjacent fields (OS kernels, databases, compilers, game engines, distributed systems, networking) and cross-language ecosystems.
- **Step 3 (Mandatory Human Gate):** Present `decomposition.md` to the user and **STOP**. Tell the user to review/edit it and approve running `research.py approve <topic>` before any heavy fan-out begins.

### 5.3 `playbooks/02-fanout.md`
- Dispatch `.opencode/agents/research-*.md` sub-agents **only for lanes needed by each axis** (`REVERSIBLE` axes may run inline without sub-agents).
- Pass each sub-agent ONLY its axis question, adjacent-domain keywords, and kill criteria.
- Enforce the **Evidence-Only Rule**: workers return raw facts formatted as `yaml:claim` blocks with `url`, verbatim `anchor`, and `receipt`—never final project recommendations.
- Enforce the **Escalation Rule**: if a worker uncovers hidden lock-in or architectural coupling, it sets `escalate: true` in its claim block.
- Include fallback note: if an Octocode MCP call fails inside a sub-agent, fall back to read-only `npx octocode` CLI or `gh` CLI and still record exact commit SHAs/issue numbers in `receipt`.
- Save one dossier per axis to `.research/<topic>/subproblems/0N-<axis-slug>.md`, then run `research.py next <topic>`.

### 5.4 `playbooks/03-synthesis-compat.md`
- **Step 1 — Binary Elimination:** Drop any candidate violating `## Kill Criteria` with a one-line cited reason.
- **Step 2 — Normalized Survivor Comparison:** Compare top 2–3 survivors per axis on: Spec Coverage, Exit Cost (Reversibility), Maintenance & Issue Radar (cited open issues/commit cadence), and Cross-Domain Transferability.
- **Step 3 — Per-Axis Compositional Verdicts:** Assign each axis exactly one of `ADOPT`, `CLONE_OR_FORK`, `STEAL_PATTERN`, `COMPOSE`, or `BUILD`.
- **Step 4 — Co-Existence Audit:**
  - **Layer 1 (Deterministic):** Run `compat-dryrun.py` for all `ADOPT`/`COMPOSE` packages against local manifests and save output to `.research/<topic>/compat.json`.
  - **Layer 2 (Runtime & Ownership Boundary Checklist):** Explicitly audit pairwise boundaries lockfiles miss: ESM vs. CJS, sync vs. async event-loop contention, OS/Node syscalls in browser/WASM, native extension build requirements, and duplicate ownership (migrations, auth, bundler AST, MCP tool name collisions). Mark each boundary `CLEAR`, `BOUNDARY_RISK`, or `INCOMPATIBLE`.
  - **Layer 3 (Opt-In Spike Proposal Only):** For any `HARD_TO_REVERSE` axis or Layer 2 `BOUNDARY_RISK`, write a short **Proposed Spike Plan** (15–30 line test to run in a temp dir) for human approval. **Do NOT execute untrusted spikes automatically in V0.**
- Run `research.py next <topic>`.

### 5.5 `playbooks/04-recall-verify.md`
- **Step 1 — Deterministic Verification:** Run `python .opencode/skills/research/scripts/cite-check.py .research/<topic>/`. Fix or remove any claim failing L1, verbatim anchor, or L2 checks, or mark the claim `[UNVERIFIED]` (which blocks `ADOPT` and `CLONE_OR_FORK`).
- **Step 2 — Adversarial Recall Pass:** Dispatch `@research-recall` per `MODERATE` / `HARD_TO_REVERSE` axis, passing **only** the axis problem statement and the winning verdict/candidate (no full dossier history). It must search with deliberately different vocabulary for stronger prior art and stop after 2 searches yielding no stronger candidate.
- **Step 3 — Write `.research/<topic>/INDEX.md` (strictly under 150 lines):**
  - Compositional Architecture Map (Axis | Verdict | Primary Sources | Reversibility)
  - Co-Existence Matrix (Layer 1 `compat.json` status + Layer 2 boundary status + any opt-in Layer 3 spike proposals)
  - Top Cross-Domain Insights (what papers/other languages changed about the original assumptions)
  - `## Recall Check` (summary of `@research-recall` queries and outcome)
  - `[DECISION-REQUIRED]` items for the human
  - File links to `.research/<topic>/subproblems/*.md`
- **Step 4 — Final Gate:** Run `research.py next <topic>` to confirm completion, present `INDEX.md`, and **STOP** (do not start coding).

---

## Section 6: OpenCode Sub-Agent Specifications

Create 4 read-only sub-agents under `.opencode/agents/`. Use **exclusively** the V1 or V2 frontmatter syntax detected in Section 1—never mix keys from both versions. Every sub-agent MUST:
- Set `mode: subagent`.
- Have a concise role `description`.
- **Deny** file editing/writing (`edit`, `write`) and **deny** nested sub-agent spawning (`task` / `subagent`).
- **Allow** read-only filesystem inspection, web fetch, relevant MCP tools, and read-only CLI fallbacks.

### Sub-Agent Roster & Skeptical Heuristics
1. **`.opencode/agents/research-repos.md`**
   - Tools: Octocode MCP (`octocode*`), read-only Bash (`gh`, `npx octocode`), web fetch.
   - Rules: Never stop at README marketing copy. Inspect actual source layout, core implementation files, commit recency, release cadence, and open blocking issues/PRs. Actively search cross-language repos when looking for algorithms/data structures (`STEAL_PATTERN`). Always record real commit SHAs or issue numbers in `receipt`.
2. **`.opencode/agents/research-docs.md`**
   - Tools: Context7 MCP (`context7*`), web fetch.
   - Rules: Pin every API claim to an exact version. Prioritize official documentation, RFCs, `llms.txt`, and breaking changelogs. Ignore undated blog posts and SEO tutorials. Extract exact verbatim anchors from docs pages.
3. **`.opencode/agents/research-papers.md`**
   - Tools: arXiv MCP (`arxiv*`), web fetch (for OpenAlex REST API `https://api.openalex.org/works?search=...`, USENIX, ACM, VLDB, and systems proceedings not hosted on arXiv).
   - Rules: Never paraphrase an abstract and stop. Extract the actual algorithm/mechanism, explicit assumptions (hardware, dataset scale, synthetic vs. production workloads), complexity bounds, and stated limitations/failure modes. Record `arxiv:<id>` or `openalex:<W-id>` in `receipt`.
4. **`.opencode/agents/research-recall.md`**
   - Tools: Octocode MCP, web fetch, read-only `gh` / OpenAlex lookup.
   - Rules: Fresh-context adversarial recall hunter. Given ONLY an axis problem and the proposed winner, invent 2 alternative search framings (different domain terminology or older foundational literature) to test whether a substantially better library, repo, or paper was missed. Hard stop after 2 searches if no stronger candidate emerges.

Immediately after writing these 4 files, run `opencode debug agents` to confirm all 4 register with `mode: subagent` and effective write/edit permissions denied.

---

## Section 7: MCP Configuration Plan

Merge MCP server entries **non-destructively** into the project's `opencode.json` (or `opencode.jsonc`) using the exact schema confirmed in Section 1:

1. **Octocode (GitHub & ecosystem code search):**
   - Local command using the active npm package verified in Step 0 (e.g., `["npx", "-y", "octocode-mcp@latest"]` or `@octocodeai/mcp` if newer).
   - Keep GitHub authentication via `gh auth` / host environment—do NOT hardcode tokens in `opencode.json`.
2. **Context7 (version-pinned docs):**
   - Local command `["npx", "-y", "@upstash/context7-mcp"]` (or remote `https://mcp.context7.com/mcp` if an API key is configured outside version control).
3. **arXiv MCP (`blazickjp/arxiv-mcp-server`):**
   - Local command `["uvx", "arxiv-mcp-server", "--storage-path", "<resolved-local-cache-dir>"]` (only enable if `uvx` is available; otherwise document manual install note and rely on direct arXiv + OpenAlex HTTP in `research-papers.md`).
4. **OpenAlex:** No MCP server needed; queried directly over plain HTTPS JSON (`https://api.openalex.org/works`).

After editing config, run `opencode debug config` and `opencode mcp list` to verify zero schema errors and healthy server registration.

---

## Section 8: Phased Build Sequence (5 Milestones)

Execute strictly in order. Stop and report verification output after each milestone.

### Milestone 1 — State Machine & Contracts
- Create `.opencode/skills/research/scripts/research.py` and `.opencode/skills/research/tests/test_research.py`.
- Implement `init`, `status`, `approve`, `next`, strict `yaml:claim` structural checks, and `escalate: true` auto-upgrade.
- **Verify:**
  ```bash
  python -m unittest .opencode/skills/research/tests/test_research.py -v
  ```
  Must prove: Phase 1 → 2 fails without `approve`; Phase 2 → 3 fails on missing `receipt` or forbidden `status` key; `escalate: true` upgrades axis to `HARD_TO_REVERSE`; Phase 4 fails on stale `verification.json` or oversized `INDEX.md`.

### Milestone 2 — Deterministic Verification & Compatibility Scripts
- Create `cite-check.py`, `compat-dryrun.py`, `tests/test_cite_check.py`, and `tests/test_compat_dryrun.py`.
- Implement L1 + normalized verbatim anchor matching, all 6 L2 endpoints (npm, PyPI, crates.io, Go proxy with `!`-escaping, arXiv, OpenAlex), scrubbed env sandbox, `--only-binary=:all:`, `--ignore-scripts`, and `LICENSE_UNKNOWN` / `LICENSE_BLOCK` enforcement.
- **Verify:**
  ```bash
  python -m unittest .opencode/skills/research/tests/test_cite_check.py .opencode/skills/research/tests/test_compat_dryrun.py -v
  ```
  Must run completely offline via mocked HTTP / subprocess fixtures and pass every positive and negative assertion.

### Milestone 3 — Skill Entry Point & 4 Phase Playbooks
- Create `.opencode/skills/research/SKILL.md` (verify line count < 80) and `playbooks/01-recon-decompose.md` through `04-recall-verify.md`.
- **Verify:** Run a scripted smoke walk through `research.py init smoke-test` → write valid fixture `decomposition.md` → `approve` → `next` → write valid fixture dossier → `next` → write `compat.json` + synthesis → `next` → write `verification.json` + `INDEX.md` → `next` (confirms `completed: true`), then clean up `.research/smoke-test/`.

### Milestone 4 — OpenCode Sub-Agents & MCP Wiring
- Create `.opencode/agents/research-{repos,docs,papers,recall}.md` using the exact V1/V2 schema from Step 0.
- Non-destructively merge MCP servers into `opencode.json` / `opencode.jsonc`.
- **Verify:**
  ```bash
  opencode debug config
  opencode debug agents
  opencode mcp list
  ```
  Confirm zero config parse errors, all 4 `research-*` sub-agents registered with `mode: subagent` and write/edit denied, and MCP servers visible.

### Milestone 5 — End-to-End Validation & Final Cleanup
- Run the complete test suite:
  ```bash
  python -m unittest discover -s .opencode/skills/research/tests -v
  ```
- Perform one end-to-end CLI gate demonstration on a temporary topic directory confirming both a blocked failure (`ANCHOR_MISMATCH` exiting non-zero) and a clean verified pass, then delete the temporary topic directory so the repo stays clean.

---

## Section 9: Acceptance Criteria (Definition of Done)

The build is complete **only** when every single box below passes with captured terminal evidence:

- [ ] **Zero third-party Python dependencies** required by `research.py`, `cite-check.py`, or `compat-dryrun.py`.
- [ ] **Cross-platform compliance:** Zero hardcoded `/tmp` paths or `shell=True` calls across all scripts.
- [ ] **Human gate enforced:** `research.py next` from Phase 1 without `approve` exits non-zero (`1`).
- [ ] **No self-reported status:** `cite-check.py` exits non-zero (`2`) with `SCHEMA_ERROR` if a `yaml:claim` block includes a `status:` key.
- [ ] **Anchor verification works:** `cite-check.py` on an HTTP `200` page whose body lacks the verbatim `anchor` exits non-zero (`1`) with `ANCHOR_MISMATCH`.
- [ ] **All 6 L2 verifiers tested:** Unit tests cover npm, PyPI, crates.io (including yanked detection), Go module proxy (including uppercase `!`-escaping), arXiv, and OpenAlex.
- [ ] **Sandbox & license discipline:** `compat-dryrun.py` passes `--only-binary=:all:` (pip) and `--ignore-scripts` (npm) inside a scrubbed temp directory, emits `LICENSE_UNKNOWN` (non-zero) when license metadata is missing, emits `LICENSE_BLOCK` (non-zero) on forbidden licenses, and emits `NOT_CHECKED` for `cpp`.
- [ ] **Skill spec valid:** `.opencode/skills/research/SKILL.md` is uppercase, matches directory name `research`, and is under 80 lines.
- [ ] **OpenCode agents valid:** `opencode debug agents` lists all 4 `research-*` sub-agents with `mode: subagent` and edit/write permissions denied.
- [ ] **Full test suite green:** `python -m unittest discover -s .opencode/skills/research/tests -v` passes with 0 errors and 0 skipped security/gate tests.