# Paper2Video 长跑进度查看

这个版本会在 terminal/log 里打印阶段进度，适合本地或 Vast 上长时间运行。

## 一键完整运行

这个命令会自动完成：

1. 读取 `/tmp/lumid.env` 和 `deploy/video_api.env`
2. 生成 PPT 讲解视频
3. 生成 `directorbench_prompt_eval_report.json`
4. 如果评分低于阈值，自动按评估意见做 1 轮确定性修复并重新评分
5. 在 terminal 打印评分摘要

脚本默认使用 `/opt/anaconda3/bin/python`，避免当前 `.venv` 里的 Python 3.14 启动/读取
缓存过慢。如果缺 `pypdf`，脚本会自动安装。

脚本默认把输出写到 `/tmp/auto_video_runs`，避免 `Desktop` 被 macOS/iCloud 文件提供器
自动变成 `dataless` 占位文件，导致 ffmpeg 读帧卡住。

```bash
cd /Users/muj666/Desktop/auto
./scripts/run_video_with_eval.sh
```

这条命令现在默认启用完整的视频化流程：

- `AUTO_VIDEO_RENDER_STYLE=scene`：标题、论文图、流程、数字和字幕作为独立图层，不显示完整 PPT 边框。
- `qwen3.6-27b`：论文理解、脚本和 storyboard。
- `qwen-omni`：图像相关性检查与视觉定位；失败时自动重试 2 次。
- `qwen-image`：生成与当前论文内容相关的视觉素材。
- `qwen-tts`：合成旁白并自动 mux 到最终 `video.mp4`。
- 如果配置了 `DEEPSEEK_API_KEY`，Lumid 文本请求或 Omni 文字定位失败时可使用 DeepSeek 文字降级；DeepSeek 不会被描述成看过图片。

如需明确指定输入论文并把 Omni 重试次数提高到 3 次：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_VISION_ATTEMPTS=3 \
./scripts/run_video_with_eval.sh "inputs/papers/Automatic Video Generation.pdf"
```

如果已经配置了可用的 DeepSeek key，并希望整条脚本和评估器直接使用 DeepSeek 文字模型：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_TEXT_PROVIDER=deepseek \
./scripts/run_video_with_eval.sh "inputs/papers/Automatic Video Generation.pdf"
```

默认自动修复规则：

- `AUTO_VIDEO_EVAL_REPAIR_ROUNDS=1`：低分时自动修复 1 轮。
- `AUTO_VIDEO_EVAL_REPAIR_THRESHOLD=7.0`：总分低于 7 分，或分类是 `weak/poor`，触发修复。
- 修复会优先用文本模型按评分意见重写 storyboard；如果模型不可用或返回失败，则回退到清理内部评审词。
- 修复后会重建字幕/指针/说话人计划；如果开启 TTS，会重新合成音频、按音频时长缩放时间轴、重渲染视频并重新 mux 音频。

如果只想生成一次，不自动修复：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_EVAL_REPAIR_ROUNDS=0 ./scripts/run_video_with_eval.sh
```

如果想最多自动修两轮：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_EVAL_REPAIR_ROUNDS=2 AUTO_VIDEO_EVAL_REPAIR_THRESHOLD=7.5 ./scripts/run_video_with_eval.sh
```

默认 `AUTO_VIDEO_SLIDE_COUNT=auto`，也就是让模型根据论文内容决定页数。`MAX_SLIDES=10`
只是硬上限，不是固定页数；短论文可能少于 10 页，长论文最多到 10 页。

如果想把上限改成 12 页：

```bash
cd /Users/muj666/Desktop/auto
MAX_SLIDES=12 ./scripts/run_video_with_eval.sh
```

如果想强制固定 8 页：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_SLIDE_COUNT=8 ./scripts/run_video_with_eval.sh
```

默认 `AUTO_VIDEO_THEME=auto`，系统会根据论文标题和正文领域为整支视频选择一致的背景主题。
目前支持：`signal`（深蓝信号网格）、`bio`（研究绿边缘结构）、`field`（底部地形线）、
`orbit`（石墨边缘弧线）、`editorial`（黑色编辑排版）、`circuit`（技术灰角落线路）。

如果想手动指定主题：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_THEME=orbit ./scripts/run_video_with_eval.sh
```

默认 `AUTO_VIDEO_RENDER_STYLE=scene`，会把每页内容拆成 2–4 个由旁白驱动的镜头，
以标题、论点、论文图、流程节点、证据行、指标和字幕等独立图层构成视频，不再显示完整 PPT 边框。
镜头规划保存在输出目录的 `scene_timeline.json`。

默认节奏针对论文讲解而不是宣传短片：

- 中文旁白按约 240 字/分钟估时，英文按约 140 词/分钟估时。
- 普通镜头至少 5 秒；开场 6–8 秒；流程和证据镜头至少 8 秒；指标镜头 6–8 秒。
- 少于 12 秒的一段旁白不会为了增加镜头数而强拆。
- 主动画通常在前 1–3.2 秒完成，之后至少保留 1.5 秒稳定阅读时间。
- 开启 TTS 后，每条字幕会独立合成并测量真实音频时长，镜头不会在本句读完前切换。
- 默认语音按 `0.90x` 放慢，每句开始前留 `0.35` 秒入场，读完后再保持 `1.20` 秒供观众阅读。
- 最终旁白由这些定时片段拼接，字幕、镜头和音频共用同一组起止时间，不再按整段总时长等比猜测。

可以用环境变量调整整体速度：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_SPEECH_WPM=130 \
AUTO_VIDEO_CJK_CHARS_PER_SEC=3.6 \
AUTO_VIDEO_MIN_BEAT_SEC=6 \
AUTO_VIDEO_MIN_SHOT_SEC=6 \
AUTO_VIDEO_SPLIT_BEAT_SEC=14 \
AUTO_VIDEO_TTS_TEMPO=0.88 \
AUTO_VIDEO_POST_SPEECH_HOLD_SEC=1.5 \
./scripts/run_video_with_eval.sh
```

如需回看旧版 PPT 式 renderer：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_RENDER_STYLE=arbor ./scripts/run_video_with_eval.sh
```

默认 `AUTO_VIDEO_IMAGE_MODE=all` 且 `AUTO_VIDEO_IMAGES_PER_SLIDE=2`：每一页都会调用图像模型生成两个不同构图，镜头会轮换使用；PDF 中尺寸合适且与章节文本相关的原始图像也会提取到 `paper_figures/` 并穿插使用。流程图、表格和指标页仍保留本地可控动画，生成图主要用于机制特写与视觉转场。

PDF 原图还会经过 Omni 相关性验证；其他论文封面、无关演示截图、装饰图标和不支持当前章节的图片会被拒绝。检查记录位于 `paper_figure_index.json` 与 `paper_figure_assignments.json`。

这个默认设置会显著增加图像生成和验证调用次数，因此完整运行时间会比旧版更长；这是为了换取镜头级视觉差异，不再让多个镜头反复使用同一张图。

如果想完全不用图像模型、全部用本地图表渲染：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_IMAGE_MODE=none ./scripts/run_video_with_eval.sh
```

如果想所有页都调用图像模型：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_IMAGE_MODE=all AUTO_VIDEO_IMAGES_PER_SLIDE=3 ./scripts/run_video_with_eval.sh
```

如果是修复已有输出目录，默认 `TARGET_SLIDES=0` 表示自动决定；可以用正数强制页数：

```bash
cd /Users/muj666/Desktop/auto
TARGET_SLIDES=10 ./scripts/repair_existing_video_with_eval.sh /tmp/auto_video_runs/paper2video_full_你的RUN_ID
```

如果要换输入论文：

```bash
cd /Users/muj666/Desktop/auto
./scripts/run_video_with_eval.sh "inputs/papers/你的论文.pdf"
```

输出目录和日志会在开头打印：

```text
OUT=/tmp/auto_video_runs/paper2video_full_...
LOG=/tmp/auto_video_runs/logs/paper2video_full_....log
EVAL_REPORT=/tmp/auto_video_runs/paper2video_full_.../directorbench_prompt_eval_report.json
```

自动修复会额外保留：

```text
directorbench_prompt_eval_report_round_0.json   # 初始评分
directorbench_prompt_eval_report_round_1.json   # 第 1 轮修复后的评分
eval_repair_report.json                         # 修复动作摘要
```

## 直接后台运行

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
set -a; source /tmp/lumid.env; source deploy/video_api.env; set +a

RUN_ID=$(date +%Y%m%d_%H%M%S)
OUT="experiments/video_output/paper2video_full_$RUN_ID"
LOG="logs/paper2video_full_$RUN_ID.log"
mkdir -p logs

nohup auto-research video build \
  --cwd . \
  --input "inputs/papers/Automatic Video Generation.pdf" \
  --kind paper \
  --out-dir "$OUT" \
  --max-slides 10 \
  --seconds-per-slide 22 \
  --fps 24 \
  --use-api \
  --use-image-api \
  --use-tts \
  --use-omni-cursor \
  --target-score 0.88 \
  --min-revisions 1 \
  --max-revisions 3 \
  > "$LOG" 2>&1 &

echo "PID=$!"
echo "OUT=$OUT"
echo "LOG=$LOG"
tail -f "$LOG"
```

## 生成完成后跑评估器

上面的 `tail -f "$LOG"` 看到 `MP4 video:`、`Metrics:` 后，说明视频生成完成。  
如果还在同一个 terminal 里，`OUT` 变量还在，可以直接继续跑：

```bash
PYTHONPATH=src .venv/bin/python -m auto_research.cli video prompt-eval \
  --cwd . \
  --artifact-dir "$OUT" \
  --out "$OUT/directorbench_prompt_eval_report.json" \
  --use-api
```

如果已经换了一个 terminal，把 `OUT` 手动设回刚才输出的目录：

```bash
cd /Users/muj666/Desktop/auto
source .venv/bin/activate
set -a; source /tmp/lumid.env; source deploy/video_api.env; set +a

OUT="experiments/video_output/paper2video_full_你的RUN_ID"

PYTHONPATH=src .venv/bin/python -m auto_research.cli video prompt-eval \
  --cwd . \
  --artifact-dir "$OUT" \
  --out "$OUT/directorbench_prompt_eval_report.json" \
  --use-api
```

快速查看评分摘要：

```bash
jq '.evaluation | {
  overall_score,
  confidence,
  classification,
  major_bottlenecks,
  highest_priority_fixes
}' "$OUT/directorbench_prompt_eval_report.json"
```

如果只想生成 evaluator prompt，不调用大模型评分，就去掉 `--use-api`。

## 日志里会看到什么

```text
[video 0000s] pipeline           [--------------------] 0/12 start paper/project-to-video build
[video 0012s] text_model         request chat/completions | provider=lumid model=qwen3.6-27b
[video 0048s] image_builder      [####----------------] 2/10 calling image model | slide=2
[video 0120s] tts_builder        request speech synthesis | model=qwen-tts
[video 0180s] renderer           [##############------] 7/10 draw slide frames | slide=7 frames=528
[video 0240s] renderer           start ffmpeg encoding | frames=5256 fps=24
```

## 大模型场景导演与多动画

完整流程默认会额外调用一次文本模型，为每个章节选择受控的场景方向。可用版式包括 `editorial`、`comparison`、`data_wall`、`timeline`、`evidence_grid`、`diagram_focus`；可用入场动画包括 `fade_up`、`slide_left`、`slide_right`、`scale_in`、`wipe`。模型只负责提出内容重点和方向，最终坐标、边界与可读性仍由本地渲染器控制。

生成结果保存在：

```text
$OUT/scene_direction.json
$OUT/scene_timeline.json
```

如需关闭额外的场景导演模型调用：

```bash
AUTO_VIDEO_USE_SCENE_DIRECTOR=0 ./scripts/run_video_with_eval.sh
```

## 查看是否还在跑

```bash
ps -p <PID> -o pid,etime,command
tail -f "$LOG"
```

## 关闭进度输出

```bash
AUTO_VIDEO_PROGRESS=0 auto-research video build ...
```
