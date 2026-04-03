# Experiments

## 一键演示（CI 与本机）

仓库自带若干 **`demo_*.yaml`**（内联 Python 写 `metrics.json`，无外部数据依赖）：

| 文件 | 说明 |
|------|------|
| `demo_smoke.yaml` | CI 烟测默认用这个；双指标 loss + accuracy |
| `demo_baseline_linear.yaml` | 回归风格：`val_loss` + `r2` |
| `demo_ablation_stub.yaml` | 分类风格：`accuracy` + `f1_score`，含治理字段示例 |
| `demo_threshold_miss.yaml` | **故意不达标**：`feedback` 里 `thresholds_passed=false`，便于讲阈值与 retro |
| `demo_latency_stub.yaml` | 短暂 `sleep` + 合格指标，便于对比 `duration_sec` |
| `_demo_mnist_cnn.yaml` | **MNIST + CNN**，默认 **约 10 分钟**（`--max-seconds 600`）；需 `pip install -e ".[demo]"`；`_` 前缀避免被 `cycle` 无 `-e` 批量跑 |

`auto-research cycle --cwd .` 会按文件名排序依次跑全部 `*.yaml`（**跳过 `_` 开头**，因此不会误跑 MNIST 长任务）。

**一条命令**（preflight → run → retro）：

```bash
auto-research cycle --cwd . -e experiments/demo_smoke.yaml --last 5
```

**跑完目录里所有实验**（`experiments/*.yaml` 按文件名排序，跳过 `_` 开头的模板）：

```bash
auto-research cycle --cwd . --last 10
```

**深度学习长演示（约 10 分钟）**：

```bash
pip install -e ".[demo]"
auto-research run --cwd . -e experiments/_demo_mnist_cnn.yaml
```

试跑可把 yaml 里 `command` 中的 `"600"` 改成 `"60"`。

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

