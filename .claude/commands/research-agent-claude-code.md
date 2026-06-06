---
description: Run one agent turn via terminal, then read results and edit experiment YAML/scripts in the editor (Claude Code–driven loop)
---

You orchestrate a **Claude Code–only** loop: the pipeline runs in the terminal; **you** apply suggestions by editing files here. Do **not** assume `agent --llm` or `--apply-suggested-yaml` unless the user explicitly asks for those.

## 1. Confirm context

- Repo root should be the auto-research project. Ask which experiment YAML to use if unclear (e.g. `experiments/demo_smoke.yaml` or their MNIST demo).

## 2. Run the agent turn (terminal)

Propose a command for the user to approve (adjust path if needed):

```bash
cd <repo-root> && source .venv/bin/activate 2>/dev/null || true
python -m auto_research agent --cwd . -e experiments/<their>.yaml
```

Optional: if they want **terminal LLM text inside the brief**, add `--llm` and remind them to `source scripts/load_api_env.sh` first when keys live in `deploy/api.env`.

## 3. Read outputs

After the command succeeds:

- Open the **latest** agent brief under `experiments/agent_output/` (match the path printed as `Agent brief:`), or ask the user to `@` that file.
- Optionally skim the latest matching `experiments/feedback/*_feedback.json` for the same experiment name.

## 4. Give actionable suggestions

In your reply:

- State **thresholds_passed** and which metrics mattered.
- If something failed or could improve: **concrete edits** — which file, what to change (`command`, `success_threshold`, or training script).
- If helpful, show a **full replacement YAML** in a fenced `yaml` block for the user to paste (you may also **apply edits directly** with the editor tools if the user wants that).

## 5. Re-run when asked

If the user wants to verify: propose the same `agent` command again, or `python -m auto_research run --cwd . -e experiments/<their>.yaml`.

## Guardrails

- Never paste or store API keys in repo files.
- Prefer editing **experiment YAML** and **scripts under the repo**; do not invent paths outside the project.
- Remind them backups exist under `experiments/agent_output/yaml_backups/` if they need to undo an experiment YAML change.
