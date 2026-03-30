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

