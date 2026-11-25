# Phase 2 Playbook — Cross-Domain Sub-Agent Fan-Out

## Step 1: Dispatch Read-Only Sub-Agents
- Dispatch `@research-repos`, `@research-docs`, and `@research-papers` **only for the lanes needed by each axis** (`REVERSIBLE` axes may run inline without sub-agents).
- Pass each sub-agent **only** its axis question, adjacent-domain translation keywords, and `## Kill Criteria`.

## Step 2: Evidence-Only & Escalation Rules
- Workers return raw technical facts in fenced `yaml:claim` blocks—**never** final project verdicts.
- Required fields per `yaml:claim` block:
  - `id` (unique across topic, e.g. `C01`), `axis`, `claim`, `url` (plain `http://` or `https://`), `anchor` (12–140 char verbatim substring from source), `receipt` (`commit:<sha>`, `issue:#<n>`, `version:<ver>`, `arxiv:<id>`, `openalex:<W-id>`, or `docs:<tag>`).
  - Optional: `package` (`ecosystem`, `name`, `version`) and `escalate: true`.
  - **Forbidden:** Never write a `status:` key. Double-quote values containing `:` or `#`.
- **Escalation Rule:** If a worker uncovers hidden lock-in or architectural coupling, set `escalate: true` in its `yaml:claim` block; `research.py` will automatically upgrade that axis to `HARD_TO_REVERSE`.
- **MCP Fallback:** If an Octocode MCP call fails inside a sub-agent, fall back to read-only `npx octocode` or `gh` CLI and still record exact commit SHAs or issue numbers in `receipt`.

## Step 3: Save Dossiers & Advance
Save one dossier per declared axis to `.research/<topic>/subproblems/0N-<axis-slug>.md`, then run:
`python .opencode/skills/research/scripts/research.py next <topic>`
