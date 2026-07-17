# Paper / Project To Video 当前进展与不足总结

## 目前完成的内容

目前已经完成了一个 **paper/project-to-video 的可运行 MVP**。这个版本不是只生成一个视频文件，而是把整个任务拆成了可检查、可迭代的 workflow。

整体流程如下：

```text
paper / project 输入
→ ingest
→ slide builder
→ subtitle builder
→ cursor builder
→ talker plan
→ judge agent
→ revise loop
→ renderer
→ video.mp4
```

目前系统支持两类输入：

- paper：支持 `.md`、`.txt`、`.pdf`
- project：支持本地项目文件夹，优先读取 `README.md`、`pyproject.toml`、`package.json` 等文件

## 已经可以生成的结果

每次运行后，系统会生成以下文件：

```text
video.mp4              最终视频
preview.html           HTML 预览页
slides.md              生成的 slides 内容
subtitles.srt          字幕文件
cursor_plan.json       光标移动计划
talker_plan.json       后续 TTS / talking-head 的输入计划
judge_feedback.json    judge agent 评分和反馈
revision_history.json  多轮 judge → revise 记录
flowmesh_spec.json     FlowMesh-style DAG 草稿
metrics.json           运行指标
```

其中 `video.mp4` 已经是真实视频文件，不是单纯的网页预览。视频中包含 slides、字幕、光标移动和顶部进度条。

## AutoResearch 相关能力



### 1. Judge-driven revise loop

系统不是一次性生成后结束，而是会经过：

```text
生成初稿 → judge agent 评分 → revise → 再次 judge
```

可以通过参数控制：

```text
target_score
min_revisions
max_revisions
```

这样可以体现 auto-research 中“反馈—修改—再运行”的闭环。

### 2. Module-level judge / rerun

Judge 不是只给一个总分，而是会分别评估不同模块：

```text
slide_builder
subtitle_builder
cursor_builder
talker_builder
```

输出内容包括：

```text
module_scores
failed_modules
rerun_modules_next
```

如果某个模块失败，系统会只重跑对应模块和必要的下游模块，而不是每次全部重跑。

例如：

- `slide_builder` 失败：重跑 slide、subtitle、cursor、talker
- `subtitle_builder` 失败：重跑 subtitle、cursor、talker
- `cursor_builder` 失败：只重跑 cursor
- `talker_builder` 失败：只刷新 talker plan



## API 接入情况

目前已经接入了 OpenAI-compatible 的 LLM API。

实际测试中，DeepSeek-compatible 配置可以跑通：

```bash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

API 主要提升的是文本生成部分，包括：

- slide 标题
- bullet 内容
- speaker note
- judge feedback
- revise 建议

相比本地 heuristic 版本，API 版生成的 slide 结构和讲稿更自然。

## VLM Cursor Grounding

目前已经预留并实现了 VLM cursor grounding 的代码入口：

```bash
--use-vlm-cursor
```

设计逻辑是：

```text
slide 截图 + 当前字幕
→ VLM 判断应该指向哪里
→ 返回 x_percent / y_percent
→ renderer 根据坐标移动光标
```

相关环境变量：

```text
OPENAI_VISION_API_KEY
OPENAI_VISION_BASE_URL
OPENAI_VISION_MODEL
```

如果没有配置 vision-capable 模型，系统会自动 fallback 到本地 heuristic cursor。

目前 DeepSeek `deepseek-chat` 是文本模型，不能真正看图，所以不能用于 VLM cursor grounding。后续需要换成支持图片输入的模型，例如 Qwen-VL、GPT-4.1 / GPT-4o vision 等。

## 视频渲染情况

目前 renderer 使用本地 PIL + ffmpeg 实现。

已经完成的视觉优化：

- 可以输出真实 `video.mp4`
- 支持 `--fps` 控制帧率
- 默认使用 12fps，比早期低帧率版本更顺滑
- 字幕放在 lower-third 安全区，避免被播放器控制条挡住
- 光标已改成普通箭头，不再使用十字或靶心样式
- 光标移动方式改为快速移动到目标位置后停留，更接近真人演示
- 顶部增加视频进度条
- slide 出场有轻微 fade-in



## FlowMesh-style DAG

目前系统会生成：

```text
flowmesh_spec.json
```

这个文件把整个任务拆成类似 FlowMesh workflow 的节点：

```text
ingest
slide_builder
subtitle_builder
cursor_builder
talker_builder
judge_agent
revise_builder
preview
renderer
```

目前它还不是正式 FlowMesh 部署文件，而是一个 workflow blueprint。后续可以根据俊一学长的 FlowMesh 示例，把它迁移成正式 FlowMesh workflow。

## 当前不足



### 1. PDF 解析还比较基础

目前 PDF 输入主要是抽取前 30 页文本。对于真实论文中的双栏排版、公式、图表、表格和 caption，解析还不够精细。

当前还没有完成：

- figure extraction
- table extraction
- section detection
- figure-caption matching
- 论文图表自动放入视频

这会导致生成的视频目前更偏文字 slides，而不是充分利用 paper 中的图表。

### 2. 视频没有真实配音

目前视频还是静音版。

虽然已经生成了：

```text
subtitles.srt
talker_plan.json
```

但还没有真正接入 TTS。

后续可以接：

- OpenAI TTS：自然度较好
- ElevenLabs：声音更自然，适合正式展示



### 3. 没有 talking-head

目前 `talker_plan.json` 只是预留 talking-head 输入计划，还没有真正接入 HeyGen、D-ID、SadTalker 等 talking-head 方案。

这个功能展示效果强，但不是当前研究核心，而且成本和调试复杂度更高，建议放在后续阶段。



4. Cursor grounding 还没有真正接入 VLM

代码层面已经支持 `--use-vlm-cursor`，但目前还没有配置真实 vision model。

如果使用 DeepSeek `deepseek-chat`，会 fallback 到 heuristic cursor，因为它不能看 slide 图片。

后续需要接入支持图片输入的模型，例如：

- Qwen-VL / Qwen2.5-VL / Qwen3-VL
- GPT-4.1 / GPT-4o vision
- Claude vision
- Gemini vision



### 5. Renderer 还比较朴素

目前 renderer 是本地 PIL + ffmpeg，适合快速验证 workflow，但视觉效果还不是正式产品级。

后续可以考虑：

- HyperFrames
- Remotion
- 更正式的 slide template
- 更自然的转场动画
- 图文混排
- 自动布局优化



### 6. Judge rubric 还比较简单

目前 judge 已经支持 module-level score，但评价标准还比较轻量。

后续可以参考 Paper2Video / PaperBench，把评价拆成更细的维度：

- 内容覆盖度
- 结构清晰度
- 讲稿自然度
- 字幕可读性
- 光标/画面对齐
- 视频节奏
- 图表使用情况
- 最终可观看性



### 7. FlowMesh 还没有正式部署

目前只生成了 FlowMesh-style DAG 草稿，还没有接入真实 FlowMesh runtime。

后续需要和骏一学长已有 workflow 示例对齐，确认：

- 节点格式
- 输入输出 artifact 规范
- 失败重试机制
- 缓存机制
- 多轮 revise 如何表达
- 每个 builder 如何单独部署



## 下一步建议

我认为下一步可以按以下顺序完善：

1. **先接 TTS**
  让视频从静音版变成有 narration 的 presentation video。这个改动最能提升 demo 观感。
2. **接 VLM cursor grounding**
  让光标不再依赖固定坐标，而是根据 slide 截图和当前字幕自动选择指向位置。
3. **增强 PDF parsing**
  加入 figure/table/caption extraction，让视频能展示论文中的真实图表。
4. **升级 renderer**
  用 HyperFrames 或 Remotion 替代当前 PIL renderer，让视频更像正式 presentation。
5. **正式对接 FlowMesh**
  把当前 `flowmesh_spec.json` 迁移成可运行的 FlowMesh workflow。
6. **完善 evaluation rubric**
  把 judge 从简单评分升级成更系统的 benchmark-style rubric。

~~目前~~我已经完成了一个 paper/project-to-video 的 runnable MVP。系统可以从真实 PDF 或项目文件夹输入，自动生成 slides、字幕、cursor plan、judge feedback、revision history、FlowMesh-style DAG，并最终渲染成 `video.mp4`。现在已经支持 LLM API 来优化内容生成，也实现了 judge-driven revise loop 和 module-level rerun。后续主要需要完善 TTS 配音、VLM cursor grounding、PDF 图表解析、renderer 视觉效果，以及正式 FlowMesh 部署。