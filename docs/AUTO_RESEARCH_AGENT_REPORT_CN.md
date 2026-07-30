# 自动化科研智能体简化实现与 Vast Demo 汇报

## 目标

教授提出“做背景调研，看看最新工作怎么做，对比实现一下”。本仓库现在补了一个
可运行的简化版本：不完整复现大型系统，而是复现它们的关键机制，并用 Vast GPU
跑 demo 产生可检查的 artifacts。

本次交付覆盖四个方向：

1. 背景调研与功能对比。
2. 简化 reviewer/critic loop。
3. Vast 上可跑的四个 demo：AI Scientist-lite、Co-Scientist-lite、PaperBench-lite、ML Intern-lite。
4. HTML 可视化 dashboard，便于汇报。

## 调研对象

| 工作 | 核心定位 | 值得借鉴的机制 | 本仓库对应实现 |
|---|---|---|---|
| AI Scientist-v2 | 端到端自动化 ML 科研 | 假设、实验、分析、可视化、论文、reviewer loop | `auto-research review` + `visualize` |
| Google AI Co-Scientist | 科学家在环的假设生成系统 | 多 agent 生成、反思、排序、演化假设 | YAML `hypothesis` + reviewer recommendations |
| OpenAI PaperBench | 评估 agent 复现论文能力 | 分层 rubric、可评分任务、复制实验结果 | `success_threshold` + `threshold_detail` |
| Hugging Face ML Intern | 开源 ML engineer agent | 读文档/论文/数据集、写代码、工具路由、local/sandbox runtime、trace | `ml-intern-lite` demo + Vast/local artifacts |

## 为什么不完整复现

这些系统完整复现成本很高：

- AI Scientist-v2 包含 ideation、agentic tree search、实验管理、论文生成和 reviewer。
- Co-Scientist 偏多智能体假设生成和科学证据整合。
- PaperBench 是完整 benchmark，包含 20 篇 ICML 论文和 8316 个可评分子任务。
- ML Intern 是完整 agent CLI + Hugging Face ecosystem 工具链。

因此这里采用“机制复现”：把最新系统里的关键 loop 压缩进当前 `auto-research`
pipeline，保证能在本地和 Vast 上真实运行。

## 新增代码

### 1. Reviewer / Critic Loop

命令：

```bash
auto-research review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
```

输出：

```text
experiments/agent_output/review_<experiment>_<timestamp>.md
```

它读取：

- experiment YAML
- `experiments/runs/<run_id>/manifest.json`
- `experiments/runs/<run_id>/metrics.json`
- `experiments/feedback/<run_id>_feedback.json`

然后生成：

- 本轮是否达标
- hypothesis 是否与 metrics 对齐
- threshold/rubric 检查
- 下一轮实验建议
- 与 AI Scientist / Co-Scientist / PaperBench / ML Intern 的对应关系

### 2. 可视化 Dashboard

命令：

```bash
auto-research visualize --cwd .
```

输出：

```text
experiments/agent_output/vast_demo_dashboard.html
```

这个 HTML 不依赖服务器，直接打开即可展示：

- run 数量
- pass/fail
- pass rate
- 每次实验的 run_id、device、duration
- 最新 metrics 和 threshold detail

### 3. 系统对比文档生成

命令：

```bash
auto-research compare-systems --cwd .
```

输出：

```text
docs/comparison_auto_research_agents.md
```

## 新增 Vast Demo

### AI Scientist-lite

```bash
auto-research run --cwd . -e experiments/_demo_ai_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
auto-research visualize --cwd .
```

对应机制：

- hypothesis quality
- experiment success
- reviewer score
- visualization readiness
- GPU probe

### Co-Scientist-lite

```bash
auto-research run --cwd . -e experiments/_demo_co_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_co_scientist_lite.yaml
auto-research visualize --cwd .
```

对应机制：

- hypothesis generation score
- multi-agent critique score
- ranking confidence
- human-in-loop readiness

### PaperBench-lite

```bash
auto-research run --cwd . -e experiments/_demo_paperbench_lite.yaml
auto-research review --cwd . -e experiments/_demo_paperbench_lite.yaml
auto-research visualize --cwd .
```

对应机制：

- paper understanding
- code reproduction
- rubric score
- artifact completeness

### ML Intern-lite

```bash
auto-research run --cwd . -e experiments/_demo_ml_intern_lite.yaml
auto-research review --cwd . -e experiments/_demo_ml_intern_lite.yaml
auto-research visualize --cwd .
```

对应机制：

- task plan score
- tool trace events
- artifact score
- shipping readiness
- local/Vast runtime

## Vast + Claude Code 跑法

用户手动租 Vast 实例后，把 Vast SSH 命令给 Claude Code：

```text
请严格按照 .claude/commands/research-vast-demo-report.md 执行。

我已经手动租好了 Vast，不要自动租服务器，不要用 GitHub。
SSH 是：ssh -p <PORT> root@<HOST>
请从本地上传代码，跑四个 demo，生成 review 和 dashboard。
```

Claude Code 会执行：

```bash
auto-research vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_ai_scientist_lite.yaml

auto-research vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_co_scientist_lite.yaml \
  --skip-install

auto-research vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_paperbench_lite.yaml \
  --skip-install

auto-research vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_ml_intern_lite.yaml \
  --skip-install

auto-research review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_co_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_paperbench_lite.yaml
auto-research review --cwd . -e experiments/_demo_ml_intern_lite.yaml
auto-research visualize --cwd .
auto-research compare-systems --cwd .
```

## 汇报时可以展示的文件

| 文件 | 用途 |
|---|---|
| `docs/AUTO_RESEARCH_AGENT_REPORT_CN.md` | 本汇报说明 |
| `docs/comparison_auto_research_agents.md` | 自动生成的对比表 |
| `experiments/agent_output/review_*.md` | 每次 demo 的 reviewer brief |
| `experiments/agent_output/vast_demo_dashboard.html` | 可视化结果 |
| `experiments/feedback/*_feedback.json` | 原始 pass/fail 证据 |
| `experiments/runs/*/manifest.json` | 命令、时间、stdout/stderr 证据 |

## 参考资料

- AI Scientist-v2: https://arxiv.org/abs/2504.08066
- Google AI Co-Scientist: https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/
- PaperBench: https://arxiv.org/abs/2504.01848
- Hugging Face ML Intern: https://github.com/huggingface/ml-intern
