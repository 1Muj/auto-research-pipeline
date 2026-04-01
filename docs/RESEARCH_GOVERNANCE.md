# Research governance（研究治理）— 与 gstack 思路的对照

本文说明：**如何把「虚拟工程团队 / 流程 / 角色」的思想落到本仓库**，而不是再造一个 gstack。灵感来自 Garry Tan 开源的 [gstack](https://github.com/garrytan/gstack)（YC 方法论：先想清楚再写代码、分阶段、分角色、可复盘）。

## 为什么教授会觉得「只有 pipeline」太简单

仅有 `auto-research run` 相当于只有一个「执行器」。工业界与研究组更在意：

- **治理（governance）**：谁在什么阶段做什么、输出是什么、如何验收。
- **可追溯**：假设、风险、前提条件是否写进产物（manifest / 反馈）。
- **门禁（gates）**：跑之前做 preflight，跑之后做 retro / 文档对齐。

本仓库用 **Markdown 命令 + 可选 YAML 字段 + CLI 子命令** 补齐这一层，仍保持 MIT 友好、无订阅、无后台服务。

## 阶段映射（Think → … → Reflect）

| 阶段 | 本仓库中的落点 |
|------|----------------|
| **Think** | `.claude/commands/research-office-hours.md`：在写 YAML 前挑战需求与假设。 |
| **Plan** | `.claude/commands/research-plan-eng.md`：锁定命令、`metrics` 契约、失败模式。 |
| **Build** | `experiments/*.yaml` + 训练脚本；`auto-research run`。 |
| **Review** | 阈值反馈 `experiments/feedback/`；可选 LLM 摘要。 |
| **Test** | CI（lint/pytest）；`auto-research preflight`（实验级门禁）。 |
| **Ship** | Git push、GPU workflow、artifact。 |
| **Reflect** | `auto-research retro`；`.claude/commands/research-retro.md`。 |

## 可选 YAML 治理字段

在实验 YAML 中可加入（均为可选，旧文件无需修改）：

- `hypothesis`：本实验要验证的陈述。
- `assumptions`：前提列表。
- `risks`：已知风险。
- `governance_phase`：标签，如 `plan` / `build`，写入 `manifest.json` 便于审计。

## CLI

```bash
auto-research preflight -e experiments/your_experiment.yaml
auto-research retro --last 10
```

## `.claude/commands/`

在 **Claude Code** 中，这些文件可作为项目级 slash 命令的说明体（具体启用方式随 Claude Code 版本以官方文档为准）。核心是：**给 AI 角色与输出结构**，而不是空白提示词。
