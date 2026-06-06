# Auto Research Pipeline 功能介绍

## 概述

`auto-research` 是一个**自动化研究流水线**工具。用户用 YAML 定义实验，CLI 自动执行命令、收集指标、阈值判断、生成反馈，并可选用大模型（Anthropic / OpenAI）生成实验改进建议。

核心思路：**定义 → 执行 → 度量 → 反馈 → 迭代**。

---

## 一、CLI 命令一览

| 命令 | 用途 |
|------|------|
| `auto-research preflight` | 实验 YAML 门禁检查（运行前校验） |
| `auto-research run` | 执行单个或全部实验 |
| `auto-research cycle` | 一键流程：preflight → run → retro |
| `auto-research retro` | 汇总最近反馈记录，生成复盘报告 |
| `auto-research agent` | 运行实验 + 写 Markdown 简报，可选 `--llm` 自动调用大模型给改进建议 |
| `auto-research vast deploy` | 部署 Vast.ai GPU 云实例 |
| `auto-research version` | 查看版本号 |

---

## 二、实验执行流程

### 1. 定义实验（YAML）

在 `experiments/` 下创建 `*.yaml` 文件，最小模板：

```yaml
name: my_experiment
description: "实验描述"
command:
  - python
  - your_train_script.py
metrics_path: metrics.json
success_threshold:
  loss: 0.30
  accuracy: 0.90
```

**关键字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 实验名称 |
| `description` | 否 | 实验描述 |
| `command` | 否 | 要执行的命令列表（为空则跑一次干运行） |
| `env` | 否 | 额外环境变量 |
| `metrics_path` | 否 | 指标输出路径（默认 `metrics.json`） |
| `success_threshold` | 否 | 阈值字典。指标名含 `loss`/`error` 的越小越好，否则越大越好 |
| `hypothesis` | 否 | 实验假设 |
| `assumptions` | 否 | 前提条件列表 |
| `risks` | 否 | 已知风险列表 |
| `governance_phase` | 否 | 治理阶段标签（think/plan/build/review/test/ship/reflect） |

### 2. 运行前校验（preflight）

```bash
auto-research preflight -e experiments/your_experiment.yaml
```

校验内容包括：
- YAML 文件是否存在且格式合法
- `command` 是否为空（警告）
- `metrics_path` 是否为相对路径且不越出项目根目录
- `success_threshold` 是否为空（警告）
- `governance_phase` 是否为标准值

### 3. 执行实验（run）

```bash
# 单个实验
auto-research run --cwd . -e experiments/demo_smoke.yaml

# 全部实验（跳过 _ 开头的文件）
auto-research run --cwd .
```

执行过程：
1. 在 `experiments/runs/<run_id>/` 下生成 `manifest.json`（记录命令、时间、退出码、stdout/stderr 尾段、治理字段）
2. 执行 YAML 中定义的 `command`
3. 读取 `metrics.json`，写入 `experiments/runs/<run_id>/metrics.json`
4. 生成 `summary.json`

### 4. 阈值反馈

运行结束后自动比对指标与阈值，生成 `experiments/feedback/<run_id>_feedback.json`：

- 指标名含 `loss` 或 `error`：值 ≤ 阈值即通过
- 其他指标：值 ≥ 阈值即通过
- 逐个指标输出 pass/fail + 具体数值 + 方向

如果配置了 `ANTHROPIC_API_KEY`，还会**自动调用 Claude 生成 5 点英文摘要**并写入 `<run_id>_llm.txt`。

### 5. 一键流程（cycle）

```bash
# 单个实验：preflight → run → retro
auto-research cycle --cwd . -e experiments/demo_smoke.yaml --last 5

# 全部实验（跳过 _ 开头）
auto-research cycle --cwd .
```

cycle = preflight（门禁检查）+ run（执行）+ retro（复盘），适合不"中奖"地跑完整流程。

### 6. 复盘（retro）

```bash
auto-research retro --last 10
```

扫描 `experiments/feedback/*_feedback.json`，按时间倒序取最近 N 个，生成 Markdown 复盘报告，显示每个实验是否通过阈值，以及总体通过率。

---

## 三、Agent 模式（亮点功能）

```bash
# 无 LLM：跑实验 + 生成 Markdown 简报
auto-research agent --cwd . -e experiments/demo_smoke.yaml

# 有 LLM：额外让大模型分析反馈并给出改进建议
auto-research agent --cwd . -e experiments/demo_smoke.yaml --llm

# LLM + 自动应用建议的 YAML：模型输出直接回写到实验文件
auto-research agent --cwd . -e experiments/demo_smoke.yaml --llm --apply-suggested-yaml
```

Agent 模式做的事情：
1. **备份 YAML**：运行前把当前实验 YAML 复制到 `experiments/agent_output/yaml_backups/<name>_before_agent_run_<timestamp>.yaml`
2. **执行实验**（同 run）
3. **生成 Markdown 简报** 到 `experiments/agent_output/agent_round1_<timestamp>.md`，包含：
   - 实验名、阈值通过情况、反馈文件路径
   - 阈值详情 JSON
   - 指标快照 JSON
   - 如果 `--llm`：LLM 的改进建议（Markdown 原文）
   - 如果 `--apply-suggested-yaml`：YAML 自动修补状态
4. `--llm --apply-suggested-yaml`：从 LLM 输出中提取第一个 ` ```yaml ` 代码块，校验后**覆盖写回实验文件**（同时生成 `*_pre_patch_<timestamp>.yaml` 备份）

### LLM 提供商选择逻辑

- 先看 `AUTO_RESEARCH_LLM_PROVIDER` 环境变量（`anthropic` 或 `openai`）
- 未设置则优先 Anthropic（`ANTHROPIC_API_KEY`），其次 OpenAI（`OPENAI_API_KEY`）
- Anthropic 使用 Messages API（默认 `claude-sonnet-4-20250514`，可通过 `ANTHROPIC_MODEL` 覆盖）
- OpenAI 使用 Chat Completions API（默认 `gpt-4o-mini`，可通过 `OPENAI_MODEL` + `OPENAI_BASE_URL` 覆盖，兼容任意 OpenAI 格式网关）

---

## 四、自带演示实验

| 文件 | 说明 |
|------|------|
| `demo_smoke.yaml` | CI 烟测，内联 Python 写 metrics，双指标 loss+accuracy |
| `demo_baseline_linear.yaml` | 回归风格，val_loss + r2 |
| `demo_ablation_stub.yaml` | 分类风格，accuracy + f1，含治理字段示例 |
| `demo_threshold_miss.yaml` | **故意不达标**，用于演示阈值失败与 retro |
| `demo_latency_stub.yaml` | sleep + 合格指标，对比 duration_sec |
| `_demo_mnist_cnn.yaml` | MNIST CNN 训练（约 10 分钟），需 `pip install -e ".[demo]"`。`_` 前缀不会被 `cycle` 批量跑 |

---

## 五、研究治理（Governance）

借鉴 gstack 思路，将工程「角色/阶段」概念映射到本仓库：

| 阶段 | 落点 |
|------|------|
| Think | `.claude/commands/research-office-hours.md`：跑前挑战需求与假设 |
| Plan | `.claude/commands/research-plan-eng.md`：锁定命令、指标契约、失败模式 |
| Build | `experiments/*.yaml` + 训练脚本 + `auto-research run` |
| Review | 阈值反馈 `experiments/feedback/` + 可选 LLM 摘要 |
| Test | CI（lint/pytest）+ `auto-research preflight` |
| Ship | Git push + GPU workflow + artifact |
| Reflect | `auto-research retro` + `.claude/commands/research-retro.md` |

Claude Code 项目级 slash 命令（`.claude/commands/research-*.md`）：
- `research-office-hours`：挑战需求
- `research-plan-eng`：制定实验计划
- `research-review-metrics`：审查指标
- `research-retro`：复盘
- `research-agent-claude-code`：agent 模式完整说明
- `research-demo-mnist-agent`：MNIST+CNN 对比演示
- `research-deploy-vast`：Vast GPU 部署说明

---

## 六、Vast.ai GPU 云部署

```bash
# CLI 方式
auto-research vast deploy --cwd .

# 或直接脚本
bash scripts/deploy_vast_5080.sh
```

流程：
1. 在 `deploy/api.env` 中填写 `VAST_API_KEY`（模板：`deploy/api.env.example`）
2. 可选：`export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'` 自定义 GPU 搜索
3. 创建实例后 SSH 进去，运行 `bash scripts/setup_github_runner.sh <ORG>/<REPO>` 注册 self-hosted runner
4. 在 GitHub Actions 中手动触发 `GPU Research` workflow

---

## 七、CI/CD

- **GitHub Actions CI**：push/PR 时自动跑 lint（ruff）+ pytest
- **GPU Research workflow**：`workflow_dispatch` 手动触发，需要标签为 `self-hosted` + `gpu` 的 runner

---

## 八、环境安装

```bash
# 标准安装
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 一键安装
chmod +x one_click.sh scripts/*.sh
./one_click.sh local

# 如果需要 LLM 功能
pip install -e ".[anthropic]"

# 如果需要跑 MNIST demo
pip install -e ".[demo]"
```

API 密钥管理：
- 复制 `deploy/api.env.example` → `deploy/api.env`
- 填写 `ANTHROPIC_API_KEY`、`VAST_API_KEY`、可选 `OPENAI_*`、`CUSTOM_INFERENCE_*`
- 加载到当前 shell：`source scripts/load_api_env.sh`

---

## 九、项目结构总览

```
auto/
├── src/auto_research/     # 核心 Python 包
│   ├── cli.py             # Typer CLI 入口，6 个子命令
│   ├── config.py          # 实验规格模型（Pydantic）
│   ├── pipeline.py        # 流水线编排（运行 + 反馈 + LLM）
│   ├── experiments.py     # 实验执行器（subprocess + manifest）
│   ├── preflight.py       # 实验 YAML 门禁校验
│   ├── feedback.py        # 阈值评估 + 反馈写入 + LLM 摘要
│   ├── retro.py           # 复盘报告生成
│   └── agent_loop.py      # Agent 模式（备份 + 运行 + LLM + YAML 回写）
├── experiments/           # 实验定义 + 运行时输出
│   ├── *.yaml             # 实验定义文件
│   ├── runs/              # 运行产物（manifest、metrics、summary）
│   ├── feedback/          # 阈值反馈 JSON
│   └── agent_output/      # Agent 模式 Markdown 简报 + YAML 备份
├── scripts/               # Shell 辅助脚本
│   ├── claude_code_bootstrap.sh
│   ├── deploy_vast_5080.sh
│   ├── load_api_env.sh
│   ├── setup_github_runner.sh
│   └── ensure_auto_research_on_path.sh
├── deploy/                # 部署配置
│   ├── api.env.example
│   ├── vast.env.example
│   └── Dockerfile.gpu-runner
├── docs/                  # 文档
├── tests/                 # pytest 测试
├── .github/workflows/     # CI/CD
└── .claude/commands/      # Claude Code 项目级命令
```
