# Experiments

在 `experiments/` 下新增你的 `*.yaml` 实验定义，然后运行：

```bash
auto-research run --cwd . -e experiments/your_experiment.yaml
```

或运行整个目录下所有 `*.yaml`：

```bash
auto-research run --cwd .
```

## YAML 最小模板

```yaml
name: my_experiment
description: "what this experiment is"
command:
  - python
  - path/to/your_train_script.py
metrics_path: metrics.json
success_threshold:
  loss: 0.30
  accuracy: 0.90
```

训练脚本需要在仓库根目录写出 `metrics.json`（或写到 `metrics_path` 指定的路径），其中包含你要阈值判断的指标键。

## 治理字段（可选，对应 docs/RESEARCH_GOVERNANCE.md）

可与 gstack 类「先想清楚再跑」流程配合，写入 `manifest.json` 的 `governance` 字段：

- `hypothesis`：要验证的一句话
- `assumptions`：前提列表
- `risks`：风险列表
- `governance_phase`：`think` / `plan` / `build` / `review` / `test` / `ship` / `reflect`

示例见 `experiments/_template.governance.yaml.example`。

跑之前可做门禁：

```bash
auto-research preflight -e experiments/your_experiment.yaml
```

复盘最近反馈：

```bash
auto-research retro --last 10
```

