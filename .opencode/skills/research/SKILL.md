---
name: research
description: >
  Use when starting unfamiliar or niche technical work, evaluating architecture
  trade-offs, hunting cross-domain prior art across GitHub repos, versioned
  docs, and academic papers, or preventing reinvention before implementation.
---

# Broad Research-Driven Development (RDD)

## Hard Invariants
- **Read-only toward application code:** Never edit application source files during a research run. Write research artifacts only under `.research/<topic>/`.
- **Scripts own verification status:** Never write a `status:` key inside any `yaml:claim` block. Only `cite-check.py` computes verification statuses.
- **One phase at a time:** Strictly follow only the single phase playbook printed to stdout by `research.py`. Do not bulk-read `playbooks/*.md`.

## Entry Commands
- Start a new topic:
  `python .opencode/skills/research/scripts/research.py init <topic>`
- Check current phase and blocking gates:
  `python .opencode/skills/research/scripts/research.py status <topic>`
- Approve Phase 1 decomposition (human gate):
  `python .opencode/skills/research/scripts/research.py approve <topic>`
- Validate exit criteria and advance to the next phase:
  `python .opencode/skills/research/scripts/research.py next <topic>`
