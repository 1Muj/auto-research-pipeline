---
description: Upload local auto-research code to an already-rented Vast.ai instance over SSH, install, run, and pull results back
---

You help the user deploy this repo to an **already-rented Vast.ai instance** by syncing local files over SSH. Do **not** create/rent a Vast instance. Do **not** require GitHub or push code to GitHub.

Vast bills while instances run. Remind the user once: **stop** pauses GPU compute charges but may keep storage charges; **destroy** removes the instance/data and stops storage charges.

## 1. What You Need From The User

Ask for the Vast SSH command if it is not already provided. It usually looks like:

```bash
ssh -p 12345 root@23.158.136.85
```

This SSH command is not an API key, but still avoid printing unnecessary sensitive account details. Never ask for or paste Vast API keys, GitHub tokens, or private keys into tracked files.

Ask which experiment to run only if unclear. Default to:

```text
experiments/_demo_mnist_cnn.yaml
```

## 2. Preconditions To Check

From repo root:

1. Confirm this is the auto-research repo.
2. Confirm `scripts/deploy_existing_vast.sh` exists.
3. Confirm the selected experiment YAML exists.
4. Prefer `.venv/bin/auto-research` if the shell `auto-research` command is missing.

Useful checks:

```bash
pwd
test -f scripts/deploy_existing_vast.sh
test -f experiments/_demo_mnist_cnn.yaml
```

## 3. Main Command

Run this from the local repo, replacing the SSH command and experiment path:

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
if [[ -x .venv/bin/auto-research ]]; then
  .venv/bin/auto-research vast push --cwd . \
    --ssh "ssh -p 12345 root@23.158.136.85" \
    -e experiments/_demo_mnist_cnn.yaml
else
  python -m auto_research vast push --cwd . \
    --ssh "ssh -p 12345 root@23.158.136.85" \
    -e experiments/_demo_mnist_cnn.yaml
fi
```

What this does:

1. Connects to the already-running Vast machine.
2. Installs remote basics if missing: `rsync`, `git`, `curl`, `tar`, `python3`, `python3-pip`, `python3-venv`.
3. Syncs local repo files to `/root/auto-research`.
4. Excludes `.git/`, `.venv/`, caches, prior run artifacts, `.data/`, `deploy/api.env`, and `deploy/vast.env`.
5. Creates a remote virtualenv and installs `.[dev,anthropic,demo]`.
6. Runs the selected experiment remotely.
7. Pulls `experiments/runs/` and `experiments/feedback/` back to the local repo.

## 4. Upload And Install Only

If the user wants to set up the server but not run the experiment yet:

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
CMD=".venv/bin/auto-research"
if [[ ! -x "$CMD" ]]; then CMD="python -m auto_research"; fi
$CMD vast push --cwd . \
  --ssh "ssh -p 12345 root@23.158.136.85" \
  --no-run
```

Then tell them the remote project path is:

```text
/root/auto-research
```

## 5. Re-run After Upload

If the code is already uploaded and installed, but the user only wants another run:

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
CMD=".venv/bin/auto-research"
if [[ ! -x "$CMD" ]]; then CMD="python -m auto_research"; fi
$CMD vast push --cwd . \
  --ssh "ssh -p 12345 root@23.158.136.85" \
  -e experiments/_demo_mnist_cnn.yaml \
  --skip-install
```

This still syncs local edits before running.

## 6. Read Results

After success, inspect local results:

```bash
find experiments/runs -maxdepth 2 -name summary.json | tail
find experiments/feedback -maxdepth 1 -name "*_feedback.json" | tail
```

Summarize:

- Whether the remote command completed.
- Which GPU appeared in `nvidia-smi` output, if visible.
- The latest run id.
- Key metrics and threshold status from feedback JSON.
- Where artifacts were pulled locally.

## 7. Failure Handling

If SSH fails:

- Ask the user to confirm the instance is running.
- Ask them to copy the exact SSH command from Vast.
- If first connection prompts host verification, tell them to answer `yes`.

If `Permission denied` appears:

- Ask whether Vast requires a specific SSH key.
- Re-run with `--identity-file /path/to/key` if needed.

If `rsync` fails:

- The script should install `rsync` on Ubuntu-like images. If not, SSH manually and run:

```bash
apt-get update
apt-get install -y rsync python3 python3-pip python3-venv
```

If PyTorch/CUDA is not detected:

- Check `nvidia-smi`.
- Confirm the Vast image has NVIDIA runtime access.
- Keep the current instance if it is only an install issue; destroy/re-rent only if the GPU is not exposed.

If disk fills up:

- Tell the user this instance was created with too little disk.
- Clean caches or re-rent with more disk, usually 64GB or 128GB.

## 8. Guardrails

- Do not run `auto-research vast deploy`; this command is for already-rented instances.
- Do not clone from GitHub unless the user explicitly changes their mind.
- Do not sync local secrets: the script already excludes `deploy/api.env` and `deploy/vast.env`.
- Do not destroy or stop the Vast instance automatically unless the user explicitly asks.
- Always remind the user to stop/destroy the Vast instance after they are done.
