# Paper / Project To Video MVP 交付包

这个文件夹把本次 paper/project-to-video 任务相关文件集中放在一起，方便汇报、交接和部署。

原项目里仍然保留了正式接入位置：

- `/Users/muj666/Desktop/auto/src/auto_research/video_pipeline.py`
- `/Users/muj666/Desktop/auto/src/auto_research/cli.py`
- `/Users/muj666/Desktop/auto/src/auto_research/video/`

这些文件不要移动，否则 `auto-research video ...` 命令会失效。

## 文件结构

```text
paper_project_video_mvp/
  README.md
  src/video_pipeline.py
  src/video/
    ingest.py
    builders.py
    judge.py
    reviser.py
    renderer.py
    flowmesh.py
    pipeline.py
  scripts/paper_project_video_demo.py
  examples/
    paper_to_video/sample_paper.md
    project_to_video/README.md
  experiments/
    _demo_paper_to_video.yaml
    _demo_project_to_video.yaml
  deploy/video_api.env.example
  docs/
    PAPER_PROJECT_TO_VIDEO_IMPLEMENTATION_CN.md
    PAPER_PROJECT_TO_VIDEO_PROPOSAL_CN.md
  claude_commands/research-paper-project-video.md
  outputs/
    paper_demo/
    project_demo/
  feedback/
    demo_paper_to_video_feedback.json
    demo_project_to_video_feedback.json
```

## 已经跑出的视频结果

直接打开：

```text
outputs/paper_demo/video.mp4
outputs/project_demo/video.mp4
```

也可以打开调试预览页：

```text
outputs/paper_demo/preview.html
outputs/project_demo/preview.html
```

每个 demo 里都有：

- `slides.md`
- `subtitles.srt`
- `cursor_plan.json`
- `talker_plan.json`
- `judge_feedback.json`
- `revision_history.json`
- `iterations/round_*`
- `flowmesh_spec.json`
- `metrics.json`
- `preview.html`
- `video.mp4`

## 在原项目里重新运行

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate

auto-research video demo
```

默认会跑一个 judge-driven revise loop：

```text
target_score = 0.9
min_revisions = 1
max_revisions = 3
```

所以不是只生成一次，而是至少经过一轮 judge feedback → revise；如果分数不到 `target_score`，会继续 revise，直到满意或达到最大轮数。

Judge 现在是 module-level，不是只给一个总分。它会输出：

```text
module_scores
failed_modules
rerun_modules_next
```

revision loop 会只重跑失败模块和必要下游模块。例如：

- `slide_builder` 失败，会重跑 slide → subtitle → cursor → talker。
- `subtitle_builder` 失败，会重跑 subtitle → cursor → talker。
- `cursor_builder` 失败，只重跑 cursor。
- `talker_builder` 失败，只刷新 talker plan。

每轮具体重跑了什么，可以看：

```text
outputs/*/revision_history.json
outputs/*/iterations/round_*/rerun_modules.json
```

视频默认用 `--fps 12` 生成，比之前的低帧率版本更顺。当前 renderer 是 `smooth_cursor_v2`：

- 光标会在关注点之间平滑移动，不再是跳点。
- 顶部有视频进度条。
- slide 出场有轻微 fade-in。

调试时可以用 `--fps 2` 加快速度；正式演示可以用 `--fps 12` 或 `--fps 24`。

如果要让光标由 VLM 看图定位，可以加：

```bash
auto-research video build \
  --input examples/paper_to_video/sample_paper.md \
  --kind paper \
  --out-dir experiments/video_output/paper_vlm_demo \
  --use-vlm-cursor \
  --fps 12
```

需要配置：

```text
OPENAI_VISION_API_KEY
OPENAI_VISION_BASE_URL
OPENAI_VISION_MODEL
```

如果没有 vision API，会自动回退到本地 heuristic cursor。

或者走 auto-research experiment + feedback：

```bash
auto-research run -e experiments/_demo_paper_to_video.yaml --brief
auto-research run -e experiments/_demo_project_to_video.yaml --brief
auto-research visualize
```

## API 留空位置

模板在：

```text
deploy/video_api.env.example
```

当前 MVP 不填 API 也能跑。

如果要让 slide builder 和 judge agent 调用模型，需要填：

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
```

如果后续要接真实 TTS，再填：

```bash
AUTO_VIDEO_TTS_PROVIDER=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
```

如果后续要接 talking-head，再填：

```bash
AUTO_VIDEO_TALKING_HEAD_PROVIDER=
HEYGEN_API_KEY=
D_ID_API_KEY=
AUTO_VIDEO_VOICE_SAMPLE=
AUTO_VIDEO_PORTRAIT=
```

如果后续要正式接 FlowMesh，再填：

```bash
FLOWMESH_API_URL=
FLOWMESH_API_TOKEN=
FLOWMESH_WORKSPACE=
```

## 汇报一句话

这个 MVP 已经把 paper/project-to-video 拆成 ingest、slide builder、subtitle builder、cursor builder、talker builder、judge agent、revise builder、preview 和 renderer 几个可检查节点，并生成 FlowMesh 风格 DAG。当前版本可以无 API 跑通，且已经支持 judge feedback 触发多轮 revise；后续只需要替换 LLM/TTS/talking-head/FlowMesh 节点即可升级成真实视频生成系统。
