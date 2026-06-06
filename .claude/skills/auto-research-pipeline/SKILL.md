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
- **Vast.ai GPU**: Claude command `.claude/commands/research-deploy-vast.md` — rent instance + optional self-hosted runner; CLI `auto-research vast deploy --cwd .` (same as `bash scripts/deploy_vast_5080.sh`).
- **Claude Code 驱动改文件**: `research-agent-claude-code` — run `agent`, edit from brief. **Contrast demo** (broken intentional YAML + MNIST CNN): `research-demo-mnist-agent`.
