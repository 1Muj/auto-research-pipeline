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
- Claude Code 命令说明：`.claude/commands/research-*.md`（office-hours、plan、review、retro）；**全程由 Claude Code 跑终端并改 YAML/脚本**：**research-agent-claude-code**；**对比演示**（先故意错误 YAML，再 MNIST+CNN，固定步骤）：**research-demo-mnist-agent**；**已租 Vast，本地直传代码运行**：**research-vast-push-local**
- CLI：`auto-research cycle --cwd .`（全部 `experiments/*.yaml` 顺序跑 + 末尾 retro）、或 `cycle -e experiments/<file>.yaml` 只跑一个；也可分步 `preflight` / `run` / `retro`
- **Agent 一轮**：`auto-research agent --cwd . -e experiments/<file>.yaml` → 预检 + 跑一次 + 读 `experiments/feedback/*.json`，在 `experiments/agent_output/` 写 Markdown 简报；每次成功开始跑之前会把当前实验 YAML 复制到 `agent_output/yaml_backups/<name>_before_agent_run_<时间戳>.yaml`，便于恢复跑前版本；`--llm` 需 `pip install -e ".[anthropic]"` 与 `ANTHROPIC_API_KEY`；`--llm --apply-suggested-yaml` 在覆盖写回前另有 `*_pre_patch_*` 备份（未应用则退出码 3）
- 可选 YAML 字段：`hypothesis`、`assumptions`、`risks`、`governance_phase`（写入 run 的 `manifest.json`）

## CI / GPU

- Push 触发 `.github/workflows/ci.yml`（lint + 测试）。
- 在 Vast GPU 机器上注册 self-hosted runner（标签 `self-hosted`, `gpu`）后，可手动触发 `GPU Research` workflow。
- **Claude Code 部署 Vast**：使用命令 `research-deploy-vast`（说明见 `.claude/commands/research-deploy-vast.md`）；等价终端：`auto-research vast deploy --cwd .` 或 `bash scripts/deploy_vast_5080.sh`（会读 `deploy/api.env` 里的 `VAST_API_KEY` 等）。
- **已租 Vast，本地代码直传**：使用命令 `research-vast-push-local`（说明见 `.claude/commands/research-vast-push-local.md`）；等价终端：`auto-research vast push --cwd . --ssh "ssh -p PORT root@HOST" -e experiments/_demo_mnist_cnn.yaml`。

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
