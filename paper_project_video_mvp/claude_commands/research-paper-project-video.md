# Paper / Project To Video Demo

你要在当前 auto-research 项目里跑 paper/project-to-video MVP。

## 目标

跑通两个 demo：

1. `experiments/_demo_paper_to_video.yaml`
2. `experiments/_demo_project_to_video.yaml`

并检查输出：

- `experiments/video_output/paper_demo/preview.html`
- `experiments/video_output/project_demo/preview.html`
- `experiments/video_output/*/judge_feedback.json`
- `experiments/video_output/*/revision_history.json`
- `experiments/video_output/*/iterations/round_*/judge_feedback.json`
- `experiments/video_output/*/flowmesh_spec.json`
- `experiments/video_output/*/metrics.json`

## 步骤

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
pip install -e ".[dev]"

auto-research run -e experiments/_demo_paper_to_video.yaml --brief
auto-research run -e experiments/_demo_project_to_video.yaml --brief
auto-research visualize
```

确认输出里有：

```text
revision_rounds >= 1
satisfied=True
video_rendered=True
```

## 如果用户提供 API

先加载：

```bash
set -a
source deploy/video_api.env
set +a
```

然后可以用：

```bash
auto-research video build \
  --input examples/paper_to_video/sample_paper.md \
  --kind paper \
  --out-dir experiments/video_output/paper_api_demo \
  --use-api
```

## 汇报重点

说明这不是一次性文生视频，而是 builder + judge-agent 的可检查 workflow：

- slide builder
- subtitle builder
- cursor builder
- talker builder
- judge agent
- revise builder / revision loop
- FlowMesh-style DAG

默认不调用 TTS/talking-head API，所以不会产生额外费用。
