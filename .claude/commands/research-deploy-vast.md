---
description: Deploy GPU experiments to Vast.ai and connect self-hosted GitHub Actions runner
---

You help the user **rent a Vast.ai GPU instance** for this repo and **optionally** hook it to **GitHub Actions** (`GPU Research` workflow). Vast bills by uptime — state that clearly once.

## Preconditions (check or ask)

1. **`deploy/api.env`** (from `deploy/api.env.example`) with at least **`VAST_API_KEY`**. Never echo keys into the transcript; confirm `deploy/api.env` is gitignored.
2. **`vastai` CLI**: `pip install vastai` (script will call `vastai set api-key` if `VAST_API_KEY` is set).
3. Optional overrides in `deploy/api.env`: `VAST_GPU_QUERY`, `VAST_IMAGE`, `VAST_DISK_GB`, `VAST_OFFER_ID` (see `deploy/vast.env.example` / comments in `api.env.example`).

## What to run (from repo root)

Prefer the wrapped CLI (same as the shell script):

```bash
source scripts/load_api_env.sh   # if keys are only in deploy/api.env
auto-research vast deploy --cwd .
```

Equivalent:

```bash
bash scripts/deploy_vast_5080.sh
```

(`deploy_vast_5080.sh` auto-sources `deploy/api.env` when present.)

## After the instance is created

Give a short **checklist** tailored to their goal:

1. **SSH** using Vast console / `vastai show instance ...` output (script prints raw CLI output).
2. On the instance: **clone this repo** (HTTPS or SSH), install **Python 3.10+**, `pip install -e ".[dev,demo]"` or whatever their experiment needs.
3. **Self-hosted runner** (for `GPU Research` workflow): on the instance run  
   `bash scripts/setup_github_runner.sh OWNER/REPO`  
   with a **short-lived** `GITHUB_TOKEN` from GitHub → Settings → Actions → Runners → New self-hosted runner. Labels should include `self-hosted` and `gpu` (default in script).
4. Start the runner (`./run.sh` in the runner directory), then in GitHub **Actions → GPU Research → Run workflow**, set **experiment** to e.g. `experiments/your_experiment.yaml`.
5. **Without GitHub**: they can run directly on the box:  
   `auto-research run --cwd . -e experiments/<file>.yaml` or `auto-research agent ...`.

## Guardrails

- Do **not** fabricate offer IDs or SSH host strings; use script output or ask the user to paste **non-secret** lines from Vast UI.
- If search returns no offers, suggest relaxing `VAST_GPU_QUERY` (e.g. `RTX_4090`) or setting `VAST_OFFER_ID` manually after they pick one in the Vast UI.
- Remind them to **stop/destroy** the instance when done to avoid charges.
