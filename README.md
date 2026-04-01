# Auto Research Pipeline (core)

This branch keeps **only the core pipeline code** and does not include any example experiments.
Instructors/users can add their own `*.yaml` experiments under `experiments/` and run them.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Or one-step (same as above + CLI check):

```bash
chmod +x one_click.sh scripts/*.sh
./one_click.sh local
```

## Run your own experiment

Create a YAML under `experiments/` (template: `experiments/README.md`), then run:

```bash
auto-research run --cwd . -e experiments/your_experiment.yaml
```

Optional LLM feedback: `pip install -e ".[anthropic]"` and set `ANTHROPIC_API_KEY`.

## Governance (gstack-style workflow, optional)

Structured research gates and Claude “roles” without copying external products:

- **Doc**: `docs/RESEARCH_GOVERNANCE.md`
- **Claude Code prompts**: `.claude/commands/research-*.md`
- **CLI**: `auto-research preflight -e experiments/your_experiment.yaml` then `auto-research run ...`; `auto-research retro --last 10`
- **YAML**: optional `hypothesis`, `assumptions`, `risks`, `governance_phase` (stored under `manifest.json` → `governance`)

## Vast.ai RTX 5080

1. `pip install vastai && vastai set api-key YOUR_KEY`
2. `export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'` (if unavailable, try `RTX_4090`, etc.)
3. `./one_click.sh vast`
4. SSH into the instance and run `bash scripts/setup_github_runner.sh YOUR_ORG/YOUR_REPO`.
   Get the runner registration token from Repo → Settings → Actions → Runners and export it as `GITHUB_TOKEN`.

## GitHub Actions

- **CI**: runs lint + pytest on push/PR (core quality gate).
- **GPU Research**: `workflow_dispatch`, requires a runner labeled `self-hosted` + `gpu`. Set the `experiment` input to your own YAML.

## Claude Code

`CLAUDE.md` at repo root is for Claude Code. Local dev entrypoint matches `scripts/claude_code_bootstrap.sh`.
