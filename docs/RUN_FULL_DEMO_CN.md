# 从头开始运行四个自动化科研智能体 demo

这份文档用于完整演示：

1. Sakana AI Scientist-v2 的简化 `idea -> experiment -> review` loop。
2. Google AI Co-Scientist 的简化多假设/评审机制。
3. OpenAI PaperBench 的简化 `paper -> code -> rubric` 评分机制。
4. Hugging Face ML Intern 的简化 ML engineer agent loop。

## A. 本地先跑一遍

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
```

如果环境缺包：

```bash
pip install -e ".[dev,demo]"
```

运行四个 demo：

```bash
auto-research run --cwd . -e experiments/_demo_ai_scientist_lite.yaml --brief
auto-research run --cwd . -e experiments/_demo_co_scientist_lite.yaml --brief
auto-research run --cwd . -e experiments/_demo_paperbench_lite.yaml --brief
auto-research run --cwd . -e experiments/_demo_ml_intern_lite.yaml --brief
```

生成四份 reviewer brief、可视化 dashboard、系统对比文档：

```bash
auto-research review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_co_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_paperbench_lite.yaml
auto-research review --cwd . -e experiments/_demo_ml_intern_lite.yaml
auto-research visualize --cwd .
auto-research compare-systems --cwd .
```

检查输出：

```bash
ls experiments/agent_output/review_demo_*_lite_*.md
open experiments/agent_output/vast_demo_dashboard.html
open docs/comparison_auto_research_agents.md
```

## B. 用 Claude Code 在 Vast 上跑

先手动在 Vast 租好机器，把 SSH 命令复制出来，例如：

```bash
ssh -p 48476 root@213.181.123.92
```

然后在 Claude Code 里说：

```text
请严格按照 .claude/commands/research-vast-demo-report.md 执行。

我已经手动租好了 Vast，不要自动租服务器，不要用 GitHub。
SSH 是：ssh -p 48476 root@213.181.123.92
请从本地上传代码，跑四个 demo，生成 review 和 dashboard。
```

Claude Code 会按顺序跑：

```bash
auto-research vast push --cwd . --ssh "ssh -p 48476 root@213.181.123.92" -e experiments/_demo_ai_scientist_lite.yaml
auto-research vast push --cwd . --ssh "ssh -p 48476 root@213.181.123.92" -e experiments/_demo_co_scientist_lite.yaml --skip-install
auto-research vast push --cwd . --ssh "ssh -p 48476 root@213.181.123.92" -e experiments/_demo_paperbench_lite.yaml --skip-install
auto-research vast push --cwd . --ssh "ssh -p 48476 root@213.181.123.92" -e experiments/_demo_ml_intern_lite.yaml --skip-install
```

然后本地生成：

```bash
auto-research review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_co_scientist_lite.yaml
auto-research review --cwd . -e experiments/_demo_paperbench_lite.yaml
auto-research review --cwd . -e experiments/_demo_ml_intern_lite.yaml
auto-research visualize --cwd .
auto-research compare-systems --cwd .
```

## C. 汇报时展示什么

建议展示顺序：

1. `docs/AUTO_RESEARCH_AGENT_REPORT_CN.md`
2. `docs/comparison_auto_research_agents.md`
3. `experiments/agent_output/vast_demo_dashboard.html`
4. 最新四个 `experiments/agent_output/review_demo_*_lite_*.md`
5. 随便打开一个 `experiments/feedback/*_feedback.json` 说明原始证据

## D. 注意

- 本地没有 GPU 时，metrics 里可能显示 `device=python-only` 或 `cuda_available=false`。
- Vast 上如果安装了 PyTorch 且 CUDA 可用，会显示 GPU 名称。
- 跑完 Vast 一定要 Stop 或 Destroy，避免继续计费。
