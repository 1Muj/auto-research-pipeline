# Paper / Project To Video 方案

## 我对任务的理解

这次要做的不是普通的文生视频，而是把论文或项目仓库转成一个可展示的视频工作流。重点是沿用 auto-research 的思路：先生成结果，再由 judge agent 反馈，最后根据反馈迭代。部署上则预留 FlowMesh 节点，方便后面和俊一学长已有 workflow 实例对齐。

## 参考系统

- Paper2Video / PaperTalker: 把 paper 转成 presentation video，强调 slide、subtitle、cursor、talker 的分工。
- PaperTok: 把 paper 转成更短的视频，适合看怎么压缩信息。
- RepoClip: 把 GitHub repo 转成项目介绍视频，适合作为 project-to-video 参考。
- Arbor / FlowMesh 工作流: 参考它的多节点编排思路，把每个 builder 做成可替换节点。

## 第一版 MVP

第一版不直接追求高质量 mp4，而是先做可检查的中间产物：

1. Ingest builder: 读取 paper PDF/Markdown/Text，或者读取本地项目 README。
2. Slide builder: 生成 4-6 页讲解 slide。
3. Subtitle builder: 生成 narration 和 `.srt` 字幕。
4. Cursor builder: 生成每句讲解对应的屏幕关注点。
5. Talker builder: 生成 TTS / talking-head API 的输入计划。
6. Judge agent: 评分覆盖率、节奏、视觉同步和可汇报性。
7. Preview builder: 生成 HTML 可视化页面。

## 为什么这样做

这样做的好处是早期不用先花钱调用视频生成 API，也不用先把 FlowMesh 完全接好。我们可以先验证 workflow 是否合理，教授也能直接看到每一步产物。如果后面要接真实视频，只需要把 talker builder 和 renderer 替换成实际 API 或 GPU 模型。

## 两天内可以交付

- 一个可跑的 paper-to-video demo
- 一个可跑的 project-to-video demo
- 一个 judge feedback JSON
- 一个 HTML preview
- 一个 FlowMesh 风格 DAG 草稿
- 一份中文汇报说明

## 后续扩展

- 接入真实 LLM API 改善 slide builder 和 judge agent。
- 接入 TTS 生成音频。
- 接入 talking-head 或 Remotion/HyperFrames 生成最终视频。
- 把 `flowmesh_spec.json` 转成正式 FlowMesh workflow。
