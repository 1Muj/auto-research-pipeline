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

默认 `AUTO_VIDEO_IMAGE_MODE=image_only`：只有 `visual_kind=image` 的页会调用图像模型，
流程图、表格、指标页优先用本地 renderer 画，避免 AI 图像生成出残缺截图或假 UI。

如果想完全不用图像模型、全部用本地图表渲染：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_IMAGE_MODE=none ./scripts/run_video_with_eval.sh
```

如果想所有页都调用图像模型：

```bash
cd /Users/muj666/Desktop/auto
AUTO_VIDEO_IMAGE_MODE=all ./scripts/run_video_with_eval.sh
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

## 查看是否还在跑

```bash
ps -p <PID> -o pid,etime,command
tail -f "$LOG"
```

## 关闭进度输出

```bash
AUTO_VIDEO_PROGRESS=0 auto-research video build ...
```
