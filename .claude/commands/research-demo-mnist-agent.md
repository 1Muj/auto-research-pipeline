---
description: Contrast demo — intentionally broken YAML vs real MNIST+CNN; repeatable agent turns; ask before editing files
---

You run a **two-part comparison** for the user, then optional repeats. Optimize for **few permission round-trips**.

## A. What this compares

| Step | Experiment | What happens |
|------|------------|--------------|
| **1** | `experiments/_demo_broken_intentional.yaml` | Inline Python writes **absurd** metrics (`val_loss` ~10, `val_accuracy` ~0.01). **Thresholds fail** — shows how the pipeline surfaces bad numbers. |
| **2** | `experiments/_demo_mnist_cnn.yaml` | Real **PyTorch MNIST+CNN** for ~**120s** wall time. Usually **thresholds pass** — same machinery, honest training. |

After both runs, **contrast in one short paragraph**: same preflight → run → metrics → feedback → agent brief; difference is **data quality / real model vs fake metrics**.

## 1. Critical: **repeatable** (do not stop after one pass)

- Finishing **both** steps does **not** end the assignment. Do not say “演示已完成、无需再操作”.
- After each reply, include **section 12 — Mandatory closing**.
- **Continuation** (loose match):  
  **再跑对比** / **全套** / **full contrast** / **再来全套** → run **section 6 — Combined contrast block** (both agents).  
  **再跑MNIST** / **mnist only** → **section 7** (MNIST only).  
  **再跑坏的** / **broken only** → **section 8** (broken only).  
  **再跑** with no qualifier → default to **section 6** (full contrast) so the teaching story stays intact.  
  **改好了再跑** → after approved edits, rerun whatever the user specifies (default **section 6**).  
  **结束** / **done** → then you may close.

## 2. Permission policy

1. **Implicit consent**: read files, run terminal blocks, analyze outputs without micro-asking.
2. **One terminal approval per block** below (combined contrast = one block = one approval).
3. **Skip install** if `python -m auto_research version` works after `source .venv`; otherwise use the `if ! version` branch inside **section 5 or 6**.
4. **Edits**: no writes to tracked files until explicit user approval.

## 3. Repo

Workspace root = this auto-research repo.

## 4. Environment repair only (if CLI broken)

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
pip install -e ".[demo]"
bash scripts/ensure_auto_research_on_path.sh
```

## 5. First time in thread — prefer **section 6** (contrast)

If the user has never run anything this session and `auto-research` may be missing, use **section 6** but prepend the `if ! python -m auto_research version` block from **section 6** (it includes install).

## 6. Combined contrast — **both** demos (one approval)

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
if ! python -m auto_research version >/dev/null 2>&1; then
  pip install -e ".[demo]"
  bash scripts/ensure_auto_research_on_path.sh
fi
python -m auto_research agent --cwd . -e experiments/_demo_broken_intentional.yaml
python -m auto_research agent --cwd . -e experiments/_demo_mnist_cnn.yaml
```

Optional: append ` --llm` to **each** last line if the user asked; they should `source scripts/load_api_env.sh` when keys live in `deploy/api.env`.

## 7. MNIST only — lean re-run

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
python -m auto_research agent --cwd . -e experiments/_demo_mnist_cnn.yaml
```

## 8. Broken demo only — lean re-run

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
python -m auto_research agent --cwd . -e experiments/_demo_broken_intentional.yaml
```

## 9. Wall-clock

- **Broken** run: seconds.  
- **MNIST**: ~**120s** training + possible first-time **download**.

## 10. Read outputs (after contrast)

Open the **two** latest agent briefs (or the two paths printed last). Summarize **in order**:  
(1) broken — **thresholds_passed: false**, which bounds failed;  
(2) MNIST — **thresholds_passed**, key metrics, epochs, device, duration.  
Then **one contrast sentence** (pipeline identical; signal differs).

## 11. Suggestions & edits

- Optional exercise: user may ask to **fix** `_demo_broken_intentional.yaml` so thresholds pass — stay in **chat** until approved, then edit.  
- For MNIST improvements, same rule.

## 12. Mandatory closing (never skip)

End with:

- **全套再来**：`再跑对比` / `全套`（执行 **section 6**）。  
- **只跑 MNIST**：`再跑MNIST`。  
- **只跑故意错的**：`再跑坏的`。  
- **先改再跑**：说明修改；确认后改文件，再说 **改好了再跑**。  
- **结束**：`结束` / `done`。

## 13. Guardrails

- Never put API keys in tracked files or paste secrets in chat.
- Surface stderr on failure.
