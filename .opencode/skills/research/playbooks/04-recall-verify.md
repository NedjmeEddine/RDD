# Phase 4 Playbook — Deterministic Verification, Recall & Final Index

## Step 1: Deterministic Citation Verification
Run:
`python .opencode/skills/research/scripts/cite-check.py .research/<topic>/`
- Fix or remove any claim failing L1, verbatim anchor, or L2 registry checks, or mark it `[UNVERIFIED]`.
- Note: Any failed/unverified claim on an `ADOPT` or `CLONE_OR_FORK` axis blocks completion. Re-run `cite-check.py` after any dossier edit so `verification.json` stays newer than all `subproblems/*.md`.

## Step 2: Adversarial Recall Pass
Dispatch `@research-recall` for each `MODERATE` or `HARD_TO_REVERSE` axis, passing **only** the axis problem statement and winning candidate/verdict (no full dossier history). It must try 2 alternative domain framings and stop after 2 searches if no stronger prior art appears.

## Step 3: Write `.research/<topic>/INDEX.md` (Strictly Under 150 Lines)
Include:
- Compositional Architecture Map (`Axis | Verdict | Primary Sources | Reversibility`)
- Co-Existence Matrix (Layer 1 `compat.json` status + Layer 2 boundary status + any Layer 3 opt-in spike proposals)
- Top Cross-Domain Insights (what papers or adjacent ecosystems changed about initial assumptions)
- `## Recall Check` (summary of `@research-recall` queries and outcomes)
- `[DECISION-REQUIRED]` items for the human
- Links to `.research/<topic>/subproblems/*.md`

## Step 4: Final Gate (STOP)
Run `python .opencode/skills/research/scripts/research.py next <topic>` to verify completion (`completed: true`), present `INDEX.md` to the user, and **STOP** without editing application code.
