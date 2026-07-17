# Paper / Project To Video MVP 运行说明

这版代码实现的是一个可以先演示、再逐步替换成真实模型的 AutoResearch-Video MVP。

它不是一上来直接生成最终 mp4，而是先生成一组可检查的中间结果：

- `slides.md`: slide builder 的输出
- `subtitles.srt`: subtitle builder 的输出
- `cursor_plan.json`: cursor builder 的输出
- `talker_plan.json`: talker builder 的 API 输入计划
- `judge_feedback.json`: judge agent 的评分和修改建议
- `revision_history.json`: judge → revise 的多轮历史
- `iterations/round_*`: 每一轮的 slides、subtitles、cursor、judge 快照
- `flowmesh_spec.json`: FlowMesh 风格的 DAG 草稿
- `preview.html`: 可视化预览页面
- `video.mp4`: 本地生成的静音讲解视频
- `metrics.json`: 接入 auto-research feedback 的指标

## 代码模块

正式入口现在按模块放在：

```text
src/auto_research/video/
  ingest.py       # 读取 paper / project
  builders.py     # slide / subtitle / cursor / talker builders
  judge.py        # module-level judge agent
  reviser.py      # module-level revise helpers
  renderer.py     # preview + mp4 renderer
  flowmesh.py     # FlowMesh DAG export
  pipeline.py     # 总编排入口
```

旧的 `src/auto_research/video_pipeline.py` 仍然保留，作为兼容实现层，避免之前的命令或脚本失效。

## 模块级 Judge / Revise

Judge 现在不是只给一个总分，而是输出模块分数：

```json
{
  "module_scores": {
    "slide_builder": 1.0,
    "subtitle_builder": 1.0,
    "cursor_builder": 1.0,
    "talker_builder": 1.0
  },
  "failed_modules": [],
  "rerun_modules_next": []
}
```

revision loop 会根据 `failed_modules` 只重跑对应模块和必要下游模块：

- `slide_builder` 失败：重跑 slide、subtitle、cursor、talker。
- `subtitle_builder` 失败：重跑 subtitle、cursor、talker。
- `cursor_builder` 失败：只重跑 cursor；如果 talker 也失败，再重跑 talker。
- `talker_builder` 失败：只刷新 talker plan。

每轮记录在：

```text
revision_history.json
iterations/round_*/rerun_modules.json
iterations/round_*/judge_feedback.json
```

## 从零开始跑 demo

在项目根目录执行：

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
pip install -e ".[dev]"
```

先跑不需要 API 的本地演示：

```bash
auto-research video demo
```

默认设置是：

```text
target_score = 0.9
min_revisions = 1
max_revisions = 3
```

也就是说，即使第一轮已经达到 judge 分数，也至少会 revise 一次，用来展示 auto-research 的反馈闭环。

生成结果在：

```text
experiments/video_output/paper_demo/video.mp4
experiments/video_output/project_demo/video.mp4
experiments/video_output/paper_demo/preview.html
experiments/video_output/project_demo/preview.html
```

如果想走原来的 auto-research experiment + feedback 流程：

```bash
auto-research run -e experiments/_demo_paper_to_video.yaml --brief
auto-research run -e experiments/_demo_project_to_video.yaml --brief
```

再生成总 dashboard：

```bash
auto-research visualize
```

## 用你自己的 paper

支持 `.md`、`.txt`。如果输入 PDF，需要额外装：

```bash
pip install pypdf
```

运行：

```bash
auto-research video build \
  --input /path/to/your_paper.pdf \
  --kind paper \
  --out-dir experiments/video_output/my_paper \
  --target-score 0.9 \
  --max-revisions 3 \
  --min-revisions 1 \
  --fps 12
```

打开：

```text
experiments/video_output/my_paper/video.mp4
experiments/video_output/my_paper/preview.html
```

## 用你自己的项目文件夹

```bash
auto-research video build \
  --input /path/to/your_project \
  --kind project \
  --out-dir experiments/video_output/my_project \
  --fps 12
```

它会优先读：

- `README.md`
- `pyproject.toml`
- `package.json`
- `requirements.txt`
- `docs/README.md`

## 视频流畅度

`--fps` 控制生成视频的帧率：

- `--fps 2`: 调试最快，但会比较卡。
- `--fps 12`: 当前默认值，适合演示，光标会平滑移动。
- `--fps 24`: 更像正式视频，但生成会慢很多。

当前 renderer 版本是 `smooth_cursor_v2`，会做三件事：

- 光标在关注点之间平滑插值移动，而不是跳点。
- 顶部增加视频进度条。
- slide 出场有轻微 fade-in。

## VLM Cursor Grounding

默认 cursor 是本地规则生成。如果想让模型看 slide 截图，判断每句字幕应该指向哪里，可以打开：

```bash
auto-research video build \
  --input examples/paper_to_video/sample_paper.md \
  --kind paper \
  --out-dir experiments/video_output/paper_vlm_demo \
  --use-vlm-cursor \
  --fps 12
```

它会把每页 slide 渲成图片，放在：

```text
cursor_grounding/slide_*.png
```

然后把 slide 图片和当前字幕发给 VLM，要求返回：

```json
{
  "x_percent": 50,
  "y_percent": 40,
  "target_label": "second bullet",
  "reason": "The subtitle is explaining the slide builder."
}
```

如果没有配置 VLM API，或者 API 不支持图片输入，会自动回退到本地 heuristic cursor。

结果可以在 `metrics.json` 里看：

```text
vlm_cursor_requested
vlm_cursor_points
cursor_grounding_mode
```

## 需要填 API 的地方

模板文件：

```text
deploy/video_api.env.example
```

复制一份：

```bash
cp deploy/video_api.env.example deploy/video_api.env
```

### 必填：如果要用 LLM 改进 slide builder 和 judge agent

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

如果你用的是其他 OpenAI-compatible 服务，只要改 `OPENAI_BASE_URL` 和 `OPENAI_MODEL`。

### 可选：如果要用 VLM 改善 cursor grounding

```bash
OPENAI_VISION_API_KEY=
OPENAI_VISION_BASE_URL=
OPENAI_VISION_MODEL=
```

如果这三个为空，会回退使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。注意：普通文本模型通常不支持图片输入，所以这里最好填一个真正支持 vision 的模型。

加载 API 后运行：

```bash
set -a
source deploy/video_api.env
set +a

auto-research video build \
  --input examples/paper_to_video/sample_paper.md \
  --kind paper \
  --out-dir experiments/video_output/paper_api_demo \
  --use-api
```

### 可选：如果要真的接 TTS

```bash
AUTO_VIDEO_TTS_PROVIDER=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

当前代码会先把 TTS 需要的文本写到 `talker_plan.json`。真正调用 TTS 可以在下一版接入。

### 可选：如果要真的接 talking-head

```bash
AUTO_VIDEO_TALKING_HEAD_PROVIDER=
HEYGEN_API_KEY=
D_ID_API_KEY=
AUTO_VIDEO_VOICE_SAMPLE=
AUTO_VIDEO_PORTRAIT=
```

当前代码会先生成 talker builder 的输入计划，不会自动扣费调用视频生成 API。

### 可选：FlowMesh

```bash
FLOWMESH_API_URL=
FLOWMESH_API_TOKEN=
FLOWMESH_WORKSPACE=
```

当前输出的是：

```text
flowmesh_spec.json
```

这个文件把 ingest、slide builder、subtitle builder、cursor builder、talker builder、judge agent、revise builder、preview、renderer 这些节点和边写清楚。等俊一学长给具体 FlowMesh 工作流格式后，可以把这个 JSON 迁移成正式 FlowMesh pipeline。

## Vast 上怎么跑

你已经有本地上传 Vast 的脚本，所以流程是：

```bash
auto-research vast push \
  --ssh "ssh -p 你的端口 root@你的IP" \
  --experiment experiments/_demo_paper_to_video.yaml
```

然后跑 project demo：

```bash
auto-research vast push \
  --ssh "ssh -p 你的端口 root@你的IP" \
  --experiment experiments/_demo_project_to_video.yaml
```

如果需要在 Vast 上用 API，就先把 `deploy/video_api.env` 传上去并在远端 `source`，或者把 API 写进 Vast instance 的环境变量。

## 可以这样和教授汇报

我现在实现了一个 paper/project-to-video 的 MVP。它先不追求一次性生成最终视频，而是参考 PaperTalker / Paper2Video 的 builder 思路，把任务拆成 slide、subtitle、cursor、talker 和 judge agent。每一步都有可检查的中间结果，并且输出一个 FlowMesh 风格的 DAG 草稿，后面可以接俊一学长的 workflow 实例。当前版本本地无 API 也能跑通；填入 OpenAI-compatible API 后，slide builder 和 judge agent 可以切换到模型生成。TTS 和 talking-head API 的位置也预留好了，但默认不会自动调用，避免早期 demo 产生额外费用。
