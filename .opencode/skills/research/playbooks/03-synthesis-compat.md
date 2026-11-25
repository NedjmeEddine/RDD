# Phase 3 Playbook — Synthesis, Verdicts & Co-Existence Audit

## Step 1: Binary Elimination
Drop any candidate violating `## Kill Criteria` from `decomposition.md` with a one-line cited reason.

## Step 2: Normalized Survivor Comparison
Compare the top 2–3 surviving candidates per axis on:
1. Spec Coverage
2. Exit Cost (Reversibility)
3. Maintenance & Issue Radar (cited open blocking issues / commit cadence)
4. Cross-Domain Transferability

## Step 3: Per-Axis Compositional Verdicts
Write `.research/<topic>/synthesis.md` (or an `INDEX.md` draft) with a Markdown table assigning **every** declared axis exactly one verdict from:
`ADOPT` | `CLONE_OR_FORK` | `STEAL_PATTERN` | `COMPOSE` | `BUILD`

Format: `| <axis-slug> | <VERDICT> | <primary sources> | <reversibility> |`

## Step 4: Co-Existence Audit
- **Layer 1 (Deterministic):** For any `ADOPT` or `COMPOSE` packages, run:
  `python .opencode/skills/research/scripts/compat-dryrun.py --ecosystem <eco> --add <pkg>... --forbidden-licenses GPL,AGPL --output .research/<topic>/compat.json`
  (Pass `--manifest <path>` when checking against local manifests.)
- **Layer 2 (Runtime & Ownership Boundary Checklist):** Audit pairwise boundaries lockfiles miss: ESM vs. CJS, sync vs. async event-loop contention, OS/Node syscalls in browser/WASM, native extension build requirements, and duplicate ownership (migrations, auth, bundler AST, MCP tool name collisions). Mark each boundary `CLEAR`, `BOUNDARY_RISK`, or `INCOMPATIBLE`.
- **Layer 3 (Opt-In Spike Proposal Only):** For any `HARD_TO_REVERSE` axis or `BOUNDARY_RISK`, write a 15–30 line **Proposed Spike Plan** (to run in a temp dir) for human approval. **Do NOT execute untrusted spikes automatically in V0.**

## Step 5: Advance
Run `python .opencode/skills/research/scripts/research.py next <topic>`
