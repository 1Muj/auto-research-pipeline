# Auto Research Pipeline (core)

This branch keeps **only the core pipeline code** and does not include any example experiments.
Instructors/users can add their own `*.yaml` experiments under `experiments/` and run them.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# If `auto-research` fails with ModuleNotFoundError (common on macOS + Python 3.14), run:
#   source .venv/bin/activate && bash scripts/ensure_auto_research_on_path.sh
# That reinstalls a small `bin/auto-research` wrapper (PYTHONPATH + `python -m auto_research`).
# Re-run it after each `pip install -e .` if the CLI breaks again.
```

Or one-step (same as above + CLI check):

```bash
chmod +x one_click.sh scripts/*.sh
./one_click.sh local
```

## Run your own experiment

Bundled **smoke demo** (same as CI): `experiments/demo_smoke.yaml`

**One shot** (preflight → run → retro):

```bash
auto-research cycle --cwd . -e experiments/demo_smoke.yaml --last 5
```

All `experiments/*.yaml` in sorted order (skips `_*.yaml`, same as `run` without `-e`):

```bash
auto-research cycle --cwd . --last 10
```

Or step by step:

```bash
auto-research preflight -e experiments/demo_smoke.yaml
auto-research run --cwd . -e experiments/demo_smoke.yaml
auto-research retro --last 5
```

Create more YAMLs under `experiments/` (template: `experiments/README.md`), then run:

```bash
auto-research run --cwd . -e experiments/your_experiment.yaml
```

Optional LLM feedback: `pip install -e ".[anthropic]"` and set `ANTHROPIC_API_KEY`.

**~10 min MNIST+CNN demo** (PyTorch): `pip install -e ".[demo]"` then `auto-research run --cwd . -e experiments/_demo_mnist_cnn.yaml` (skipped by bulk `cycle` because of `_` prefix).

## API keys (placeholder for Claude / Vast / future endpoints)

1. Copy `deploy/api.env.example` → `deploy/api.env` (gitignored).
2. Fill keys when you have them (`ANTHROPIC_API_KEY`, `VAST_API_KEY`, optional `OPENAI_*`, `CUSTOM_INFERENCE_*`).
3. In a terminal: `source scripts/load_api_env.sh` (or rely on `deploy_vast_5080.sh` / `claude_code_bootstrap.sh` auto-loading `deploy/api.env` when present).

## Governance (gstack-style workflow, optional)

Structured research gates and Claude “roles” without copying external products:

- **Doc**: `docs/RESEARCH_GOVERNANCE.md`
- **Claude Code prompts**: `.claude/commands/research-*.md`
- **CLI**: `auto-research preflight -e experiments/your_experiment.yaml` then `auto-research run ...`; `auto-research retro --last 10`
- **YAML**: optional `hypothesis`, `assumptions`, `risks`, `governance_phase` (stored under `manifest.json` → `governance`)

## Vast.ai RTX 5080

1. Put `VAST_API_KEY` (and optional `VAST_GPU_QUERY`, …) in `deploy/api.env` from `deploy/api.env.example`, **or** `pip install vastai && vastai set api-key YOUR_KEY` manually.
2. `./one_click.sh vast` runs `scripts/deploy_vast_5080.sh`, which auto-`source`s `deploy/api.env` when it exists and runs `vastai set api-key` if `VAST_API_KEY` is set.
3. Override GPU search if needed: `export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'` (if unavailable, try `RTX_4090`, etc.)
4. SSH into the instance and run `bash scripts/setup_github_runner.sh YOUR_ORG/YOUR_REPO`.
   Get the runner registration token from Repo → Settings → Actions → Runners and put it in `deploy/api.env` as `GITHUB_TOKEN` or export for one session.

## GitHub Actions

- **CI**: runs lint + pytest on push/PR (core quality gate).
- **GPU Research**: `workflow_dispatch`, requires a runner labeled `self-hosted` + `gpu`. Set the `experiment` input to your own YAML.

## Claude Code

`CLAUDE.md` at repo root is for Claude Code. Local dev entrypoint matches `scripts/claude_code_bootstrap.sh` (loads `deploy/api.env` when present so future API keys are available in that shell session).
