# Auto Research — Claude Code 说明

本仓库是自动化研究流水线：用 YAML 定义实验、`auto-research` 执行命令、写入 `experiments/runs/`，阈值反馈写入 `experiments/feedback/`；可选 `ANTHROPIC_API_KEY` 生成文字总结。

## 常用命令

- 本地一键环境（无内置实验）：`bash scripts/claude_code_bootstrap.sh`，再自行添加 YAML 后 `auto-research run ...`
- 跑单个实验：`auto-research run --cwd . -e experiments/your_experiment.yaml`
- 跑 `experiments/` 下全部 YAML：`auto-research run --cwd .`

## 写新实验

在 `experiments/` 新增 `*.yaml`：`name`、`command`、可选 `success_threshold`（指标名含 `loss`/`error` 视为越小越好，否则越大越好）。训练脚本需在仓库根目录写出 `metrics.json`（或通过 `metrics_path` 指定路径）。

## 治理 / 虚拟「角色」流程（对标 gstack 思路）

- 文档：`docs/RESEARCH_GOVERNANCE.md`
- Claude Code 命令说明：`.claude/commands/research-*.md`（office-hours、plan、review、retro）
- CLI：`auto-research cycle --cwd .`（全部 `experiments/*.yaml` 顺序跑 + 末尾 retro）、或 `cycle -e experiments/<file>.yaml` 只跑一个；也可分步 `preflight` / `run` / `retro`
- 可选 YAML 字段：`hypothesis`、`assumptions`、`risks`、`governance_phase`（写入 run 的 `manifest.json`）

## CI / GPU

- Push 触发 `.github/workflows/ci.yml`（lint + 测试）。
- 在 Vast GPU 机器上注册 self-hosted runner（标签 `self-hosted`, `gpu`）后，可手动触发 `GPU Research` workflow。

## API 与密钥（预留位）

以后有接口时**只填环境变量即可**，不必改代码结构：

| 用途 | 模板文件 | 说明 |
|------|----------|------|
| Claude / Anthropic、OpenAI 兼容、Vast、GitHub token | `deploy/api.env.example` | 复制为 `deploy/api.env`（已在 `.gitignore`） |
| 仅 Vast 旧习惯 | `deploy/vast.env.example` | 可复制为 `deploy/vast.env`，或与上表合并到 `api.env` |

加载到当前 shell：

```bash
source scripts/load_api_env.sh
```

- **Anthropic**：`ANTHROPIC_API_KEY` — 与 `pip install -e ".[anthropic]"` + `auto-research run` 里可选 LLM 反馈一致；可选 `ANTHROPIC_BASE_URL`。
- **Vast**：`VAST_API_KEY`、`VAST_GPU_QUERY` 等 — `scripts/deploy_vast_5080.sh` 若发现 `deploy/api.env` 会自动 `source`；有 `VAST_API_KEY` 时会尝试 `vastai set api-key`。
- **预留**：`OPENAI_*`、`CUSTOM_INFERENCE_*` — 供后续你自己的调用脚本读取。

修改流水线行为时优先改 `src/auto_research/`，并保持 `tests/` 可通过 CI。
