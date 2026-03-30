# Auto Research — Claude Code 说明（exp 分支）

本分支提供一个最小可跑的 research pipeline：用 YAML 定义实验、`auto-research` 执行命令、写入 `experiments/runs/`，阈值反馈写入 `experiments/feedback/`。

## 常用命令

- 本地一键环境 + 试跑：`bash scripts/claude_code_bootstrap.sh`
- 跑线性回归实验：`auto-research run --cwd . -e experiments/linear_regression.yaml`

## 写新实验

在 `experiments/` 新增 `*.yaml`：`name`、`command`、可选 `success_threshold`（指标名含 `loss`/`error` 视为越小越好，否则越大越好）。
训练脚本需在仓库根目录写出 `metrics.json`（或通过 `metrics_path` 指定路径）。

## Vast.ai / GPU Runner

- 一键创建 Vast 实例：`bash scripts/deploy_vast_5080.sh`
- 在 GPU 机器上注册 self-hosted runner：`bash scripts/setup_github_runner.sh OWNER/REPO`
- 触发 `.github/workflows/gpu-research.yml`（在 GitHub 页面手动运行）

