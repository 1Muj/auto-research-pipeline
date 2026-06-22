# 从头运行 AutoTune-Control demo

## 1. 本地运行

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
pip install -e ".[dev]"
```

运行控制系统自动调参实验：

```bash
auto-research run --cwd . -e experiments/_demo_control_autotune.yaml --brief
```

生成 review brief：

```bash
auto-research review --cwd . -e experiments/_demo_control_autotune.yaml
```

打开控制系统专属 dashboard：

```bash
open experiments/agent_output/control_autotune_dashboard.html
```

可选：生成通用 dashboard：

```bash
auto-research visualize --cwd .
```

## 2. 在 Vast 上运行

手动租好 Vast 后，从 Vast 页面复制 SSH，例如：

```bash
ssh -p 48476 root@213.181.123.92
```

然后在本地运行：

```bash
auto-research vast push --cwd . \
  --ssh "ssh -p 48476 root@213.181.123.92" \
  -e experiments/_demo_control_autotune.yaml
```

如果 `auto-research` 找不到，用：

```bash
.venv/bin/auto-research vast push --cwd . \
  --ssh "ssh -p 48476 root@213.181.123.92" \
  -e experiments/_demo_control_autotune.yaml
```

Vast 跑完会把 `experiments/runs/` 和 `experiments/feedback/` 拉回本地。

然后本地生成 review：

```bash
auto-research review --cwd . -e experiments/_demo_control_autotune.yaml
```

## 3. 让 Claude Code 自动跑

在 Claude Code 里说：

```text
请按照 docs/RUN_CONTROL_AUTOTUNE_CN.md 执行。
我已经手动租好了 Vast，不要自动租服务器，不要用 GitHub。
SSH 是：ssh -p <PORT> root@<HOST>
请从本地上传代码到 Vast，运行 experiments/_demo_control_autotune.yaml，
然后生成 review brief，并告诉我 control_autotune_dashboard.html 在哪里。
```

## 4. 汇报展示顺序

1. `docs/AUTO_SYS_CONTROL_OPTIMIZATION_CN.md`
2. `experiments/_demo_control_autotune.yaml`
3. `experiments/feedback/demo_control_autotune_*_feedback.json`
4. `experiments/agent_output/review_demo_control_autotune_*.md`
5. `experiments/agent_output/control_autotune_dashboard.html`

## 5. 注意

- 这个 demo 主要是 CPU 仿真，不依赖 GPU；Vast 用来证明同一个 pipeline 可远程部署。
- 如果要让 GPU 更明显，可以后续把 plant simulation 扩展成 batch simulation 或 PyTorch 并行搜索。
- 跑完 Vast 记得 Stop 或 Destroy，避免持续计费。
