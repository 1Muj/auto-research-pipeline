# Auto Research (exp branch)

本分支 `exp` 只保留一个**可直接运行的真实小实验**：一维线性回归 \(y=ax+b\)（梯度下降），用于演示最小可用的 research pipeline（YAML → 执行 → `metrics.json` → 阈值反馈）。

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
auto-research run --cwd . -e experiments/linear_regression.yaml
```

## 你会得到什么

- `experiments/runs/<run_id>/`: `manifest.json` + `metrics.json` + `summary.json`
- `experiments/feedback/<run_id>_feedback.json`: 阈值通过/失败的反馈

## 文件说明

- `experiments/linear_regression.yaml`: 实验定义（命令、metrics 路径、成功阈值）
- `scripts/train_linear_regression.py`: 训练脚本（写出 `metrics.json`）
- `src/auto_research/`: pipeline 代码与 CLI（`auto-research`）
