---
name: auto-research-pipeline
description: YAML-driven experiment runner with metrics, threshold feedback, preflight, and retro. Use when editing experiments/, auto_research package, or Claude commands under .claude/commands/research-*.md.
---

# Auto Research Pipeline

- Run one experiment: `auto-research run --cwd . -e experiments/<file>.yaml`
- Validate before run: `auto-research preflight -e experiments/<file>.yaml`
- Summarize recent feedback: `auto-research retro --last 10`
- Governance fields in YAML (optional): `hypothesis`, `assumptions`, `risks`, `governance_phase` → appear in `experiments/runs/<id>/manifest.json` under `governance`.
- Full narrative: `docs/RESEARCH_GOVERNANCE.md`
