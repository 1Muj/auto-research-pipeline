# Auto Research Pipeline

Python 流水线：实验（YAML）→ 执行 → `metrics.json` → 阈值反馈 → 可选 Claude 文字总结。CI 跑在 GitHub Actions；GPU 任务通过 **self-hosted runner**（例如 Vast.ai 上的 RTX 5080 机器）执行。

## 一键脚本

```bash
chmod +x one_click.sh scripts/*.sh
./one_click.sh local   # 本机：venv + 示例实验（Claude Code 可直接用此仓库）
./one_click.sh vast    # Vast：搜索 GPU 并创建实例（需 vastai CLI）
```

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
auto-research run --cwd . -e experiments/example.yaml
```

可选 LLM 反馈：`pip install -e ".[anthropic]"`，并设置 `ANTHROPIC_API_KEY`。

## Vast.ai RTX 5080

1. `pip install vastai && vastai set api-key YOUR_KEY`
2. `export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'`（无货时可改为 `RTX_4090` 等）
3. `./one_click.sh vast`
4. SSH 进实例后执行 `bash scripts/setup_github_runner.sh YOUR_ORG/YOUR_REPO`，在仓库 Settings → Actions → Runners 取 registration token 作为 `GITHUB_TOKEN`。

## GitHub Actions

- **CI**：推送即跑 lint、pytest、示例实验。
- **GPU Research**：`workflow_dispatch`，需带标签 `self-hosted` + `gpu` 的 runner；可上传 `experiments/runs` 与 `experiments/feedback` 为 artifact。

## Claude Code

仓库根目录 `CLAUDE.md` 供 Claude Code 阅读；本地开发路径与 `scripts/claude_code_bootstrap.sh` 一致即可。
