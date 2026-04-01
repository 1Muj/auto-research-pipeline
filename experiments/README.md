# Experiments

## 一键演示（CI 与本机）

仓库自带 **`demo_smoke.yaml`**：内联 Python 写入 `metrics.json`，用于验证整条流水线（与 GitHub Actions 中步骤一致）。

**一条命令**（preflight → run → retro）：

```bash
auto-research cycle --cwd . -e experiments/demo_smoke.yaml --last 5
```

**跑完目录里所有实验**（`experiments/*.yaml` 按文件名排序，跳过 `_` 开头的模板）：

```bash
auto-research cycle --cwd . --last 10
```

分步：

```bash
auto-research preflight -e experiments/demo_smoke.yaml
auto-research run --cwd . -e experiments/demo_smoke.yaml
auto-research retro --last 5
```

注意：`auto-research run`（不带 `-e`）会跑 `experiments/` 下**所有** `*.yaml`，因此会**同时**跑 `demo_smoke` 和你的实验；开发时多用 `-e` 指定单个文件。

---

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

