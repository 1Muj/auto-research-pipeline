# Blender 操作员分段渲染流程

当前系统仍由模型负责论文解析、章节、讲稿、视觉资产、字幕、TTS 和评估；Blender 负责空间场景、摄像机、物体动画和分段渲染。两条渲染路径并存，默认路径不变。

## 导出一个分段任务

```bash
cd /Users/muj666/Desktop/auto
./.venv/bin/python scripts/export_blender_operator_job.py \
  /tmp/auto_video_runs/paper2video_fullqa_v5_20260813 \
  --start 0 --duration 60 --max-shots 2 \
  --fps 15 --width 640 --height 360
```

命令只读取 checkpoint，不调用文本、视觉、图片或 TTS 模型。它会生成 `blender_operator_manifest.json`，把镜头按语义边界拆成小任务，并为每个镜头写入 `operator_action`、空间层次和 HUD 约束。

## Blender MCP 操作约束

- 论文图/生成图是空间平面或舞台对象；标题、关键数字和字幕保持为面向摄像机的平面 HUD。
- 所有外显文字来自 `source.json`、`storyboard.json` 或 `scene_timeline.json`，不添加默认占位标签。
- 每个分段先低分辨率预览，再检查切换帧、末帧、安全边距和文字可读性。
- 只有通过画面检查后，才渲染下一段；最终再按原字幕/TTS 时间线合成音频并运行 evaluator。

## 保留旧渲染器并导出 Blender 旁路

完整 pipeline 可以在保持原 MP4 的同时导出 Blender manifest：

```bash
AUTO_VIDEO_EXPORT_BLENDER_OPERATOR=1 \
AUTO_VIDEO_OPERATOR_MAX_SHOTS=3 \
./scripts/run_video_with_eval.sh
```

这一步只增加 `OUT/blender_operator/blender_operator_manifest.json`，不会替换现有 Pillow/FFmpeg 输出。确认各分段稳定后，再把 Blender 分段视频接入音频 mux 和 DirectorBench 评分。

## 当前交付策略

当前主视频默认使用清晰的 2D scene renderer。原因是实验中的空间卡片在小预览或远景构图下会缩小正文、遮挡论文图，并降低文字和图片的可读性。主流程会要求同时设置以下两个变量才启用 3D：

```bash
AUTO_VIDEO_HYBRID_3D=1 AUTO_VIDEO_EXPERIMENTAL_3D=1
```

只设置 `AUTO_VIDEO_HYBRID_3D=1` 不会改变交付视频。需要预览时可运行：

```bash
./.venv/bin/python scripts/render_hybrid_3d_preview.py \
  /tmp/auto_video_runs/paper2video_fullqa_v5_20260813 \
  --mode clear_2d --start 0 --duration 18 --fps 15 --width 1280 --height 720
```
