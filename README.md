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

**Agent turn** (run + feedback → markdown brief for Claude Code; optional `--llm`). Each successful agent run also copies the experiment YAML to `experiments/agent_output/yaml_backups/*_before_agent_run_<timestamp>.yaml` so you can restore the pre-run version.

```bash
auto-research agent --cwd . -e experiments/demo_smoke.yaml
# With API: pip install -e ".[anthropic]" && export ANTHROPIC_API_KEY=...
auto-research agent --cwd . -e experiments/demo_smoke.yaml --llm
# With --llm, optionally apply the model's first YAML fence back to the experiment file:
auto-research agent --cwd . -e experiments/demo_smoke.yaml --llm --apply-suggested-yaml
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
2. Create an instance: `auto-research vast deploy --cwd .` (same as `bash scripts/deploy_vast_5080.sh`). In **Claude Code**, use the `research-deploy-vast` command (see `.claude/commands/research-deploy-vast.md`).
3. `./one_click.sh vast` runs `scripts/deploy_vast_5080.sh`, which auto-`source`s `deploy/api.env` when it exists and runs `vastai set api-key` if `VAST_API_KEY` is set.
4. Override GPU search if needed: `export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'` (if unavailable, try `RTX_4090`, etc.)
5. SSH into the instance and run `bash scripts/setup_github_runner.sh YOUR_ORG/YOUR_REPO`.
   Get the runner registration token from Repo → Settings → Actions → Runners and put it in `deploy/api.env` as `GITHUB_TOKEN` or export for one session.

### Vast.ai existing instance: upload local code directly

If you rent the Vast instance manually and do **not** want to push code to GitHub, copy the SSH command from Vast and run:

```bash
auto-research vast push --cwd . \
  --ssh "ssh -p 12345 root@23.158.136.85" \
  -e experiments/_demo_mnist_cnn.yaml
```

This syncs the local project to `/root/auto-research`, installs a remote venv, runs the experiment, and pulls `experiments/runs/` plus `experiments/feedback/` back to your local machine.

### Paper / Project To Video MVP

This branch includes a runnable paper/project-to-video MVP. It turns a paper PDF/Markdown file or a local project folder into inspectable workflow artifacts and a rendered `video.mp4`.

Pipeline:

```text
paper/project input
→ ingest
→ slide builder
→ subtitle builder
→ cursor builder
→ talker plan
→ judge agent
→ module-level revise loop
→ renderer
→ video.mp4
```

Run the built-in demo:

```bash
auto-research video demo --fps 12
```

Run a custom paper:

```bash
auto-research video build \
  --input "inputs/papers/your_paper.pdf" \
  --kind paper \
  --out-dir experiments/video_output/your_paper_demo \
  --use-api \
  --fps 12 \
  --min-revisions 1 \
  --max-revisions 2
```

For DeepSeek-compatible text generation:

```bash
export OPENAI_API_KEY="YOUR_KEY"
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_MODEL="deepseek-chat"
```

Main outputs:

- `video.mp4`: rendered video
- `slides.md`: generated slides
- `subtitles.srt`: narration subtitles
- `cursor_plan.json`: cursor movement plan
- `judge_feedback.json`: module-level judge feedback
- `revision_history.json`: judge → revise loop history
- `flowmesh_spec.json`: FlowMesh-style DAG blueprint
- `metrics.json`: run metrics

Optional VLM cursor grounding:

```bash
auto-research video build \
  --input examples/paper_to_video/sample_paper.md \
  --kind paper \
  --out-dir experiments/video_output/paper_vlm_demo \
  --use-vlm-cursor \
  --fps 12
```

Configure a vision-capable OpenAI-compatible model with:

```bash
OPENAI_VISION_API_KEY=
OPENAI_VISION_BASE_URL=
OPENAI_VISION_MODEL=
```

More details:

- `docs/PAPER_PROJECT_TO_VIDEO_IMPLEMENTATION_CN.md`
- `docs/CURRENT_PROGRESS_AND_LIMITATIONS_CN.md`
- `paper_project_video_mvp/README.md`

## GitHub Actions

- **CI**: runs lint + pytest on push/PR (core quality gate).
- **GPU Research**: `workflow_dispatch`, requires a runner labeled `self-hosted` + `gpu`. Set the `experiment` input to your own YAML.

## Claude Code

`CLAUDE.md` at repo root is for Claude Code. Local dev entrypoint matches `scripts/claude_code_bootstrap.sh` (loads `deploy/api.env` when present so future API keys are available in that shell session).
