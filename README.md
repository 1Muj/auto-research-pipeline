# Auto Research (exp branch)

本分支 `exp` 只保留一个**可直接运行的真实小实验**：一维线性回归 \(y=ax+b\)（梯度下降），用于演示最小可用的 research pipeline（YAML → 执行 → `metrics.json` → 阈值反馈）。

## 部署到 Claude Code

1. **克隆并切到本分支**：`git clone <仓库地址>` 后执行 `git checkout exp`（若默认分支不是 `exp`）。
2. **用 Claude Code 打开仓库根目录**（把整个 `auto-research-pipeline` 文件夹作为工作区打开）。
3. **项目说明给 AI 读**：根目录 `CLAUDE.md` 约定常用命令、实验路径与 Vast/runner 相关入口；Claude Code 会自动参考该文件。
4. **一键装好环境并跑通示例实验**（终端在项目根执行）：
   ```bash
   chmod +x one_click.sh scripts/*.sh
   ./one_click.sh local
   ```
   等价于执行 `scripts/claude_code_bootstrap.sh`：创建 `.venv`、安装依赖、并运行 `experiments/linear_regression.yaml`。

之后在 Claude Code 里继续开发时，激活环境：`source .venv/bin/activate`，再按需 `auto-research run ...`。

## 一键运行

```bash
chmod +x one_click.sh scripts/*.sh
./one_click.sh local
```

（Vast.ai：`./one_click.sh vast`）

## 手动运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
auto-research run --cwd . -e experiments/linear_regression.yaml
```

## 结果

- `experiments/runs/<run_id>/`: `manifest.json` + `metrics.json` + `summary.json`
- `experiments/feedback/<run_id>_feedback.json`: 阈值通过/失败的反馈

## 文件说明

- `experiments/linear_regression.yaml`: 实验定义（命令、metrics 路径、成功阈值）
- `scripts/train_linear_regression.py`: 训练脚本（写出 `metrics.json`）
- `src/auto_research/`: pipeline 代码与 CLI（`auto-research`）
