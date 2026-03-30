# Auto Research Pipeline (core)

本分支只保留 **核心 pipeline 代码**，不附带示例实验。教授/使用者可以自行在 `experiments/` 下添加 `*.yaml` 实验并运行。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 运行你自己的实验

在 `experiments/` 新增 YAML（模板见 `experiments/README.md`），然后：

```bash
auto-research run --cwd . -e experiments/your_experiment.yaml
```

可选 LLM 反馈：`pip install -e ".[anthropic]"`，并设置 `ANTHROPIC_API_KEY`。

## Vast.ai RTX 5080

1. `pip install vastai && vastai set api-key YOUR_KEY`
2. `export VAST_GPU_QUERY='gpu_name=RTX_5080 num_gpus=1'`（无货时可改为 `RTX_4090` 等）
3. `./one_click.sh vast`
4. SSH 进实例后执行 `bash scripts/setup_github_runner.sh YOUR_ORG/YOUR_REPO`，在仓库 Settings → Actions → Runners 取 registration token 作为 `GITHUB_TOKEN`。

## GitHub Actions

- **CI**：推送即跑 lint、pytest（核心代码质量保证）。
- **GPU Research**：`workflow_dispatch`，需带标签 `self-hosted` + `gpu` 的 runner；运行时请把输入 `experiment` 指向你自己添加的 YAML。

## Claude Code

仓库根目录 `CLAUDE.md` 供 Claude Code 阅读；本地开发路径与 `scripts/claude_code_bootstrap.sh` 一致即可。

## 发布到 GitHub（账号 [@1Muj](https://github.com/1Muj)）

1. 打开 [New repository](https://github.com/new)，Repository name 例如 **`auto-research-pipeline`**，选 **Public**，**不要**勾选 “Add a README”（本地已有）。
2. 在本机项目根目录执行（把 `YOUR_TOKEN` 换成你的 [Personal Access Token](https://github.com/settings/tokens) 若用 HTTPS，或改用 SSH 地址）：

```bash
git remote add origin https://github.com/1Muj/auto-research-pipeline.git
git branch -M main
git push -u origin main
```

若 GitHub 上用了别的仓库名，把上面 URL 里的 `auto-research-pipeline` 改成你的仓库名即可。
