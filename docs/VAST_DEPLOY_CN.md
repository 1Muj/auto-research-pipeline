# Vast.ai 部署交接说明

这套 `auto-research` 不是常驻 Web 服务，而是实验执行流水线：`experiments/*.yaml`
里写实验命令，程序负责运行命令、收集 `metrics.json`、生成 run manifest 和 feedback。
部署到 Vast.ai 的目标，是把一台 GPU 机器接成可重复触发的实验执行节点。

## 推荐方案：Vast + GitHub Actions self-hosted runner

适合和骏一学长整合，因为之后只需要在 GitHub 页面手动触发 workflow，不必每次 SSH
进 Vast 机器。

### 1. 本地准备

```bash
cd /path/to/auto
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install vastai
cp deploy/api.env.example deploy/api.env
```

在 `deploy/api.env` 里填写：

```bash
VAST_API_KEY=你的_vast_key
VAST_GPU_QUERY=gpu_name=RTX_5080 num_gpus=1
```

如果 5080 没库存，可以临时改成：

```bash
VAST_GPU_QUERY='gpu_name=RTX_4090 num_gpus=1 reliability>0.95'
```

### 2. 创建 Vast 实例

```bash
auto-research vast deploy --cwd .
```

等价命令：

```bash
bash scripts/deploy_vast_5080.sh
```

脚本会读取 `deploy/api.env`，搜索符合 `VAST_GPU_QUERY` 的 offer，并创建 SSH
可连接的实例。

### 3. SSH 到 Vast 机器后安装基础工具

如果镜像里缺基础工具，先跑：

```bash
apt-get update
apt-get install -y git curl tar python3 python3-pip python3-venv
```

检查 GPU：

```bash
nvidia-smi
```

### 4. 克隆仓库并注册 GitHub runner

```bash
git clone https://github.com/OWNER/REPO.git
cd REPO
```

到 GitHub 仓库页面生成 runner token：

`Settings -> Actions -> Runners -> New self-hosted runner`

然后在 Vast 机器上执行：

```bash
export GITHUB_TOKEN=刚生成的_runner_registration_token
bash scripts/setup_github_runner.sh OWNER/REPO
cd ~/actions-runner
./run.sh
```

保持 `./run.sh` 不退出。注册成功后，这台 Vast 机器会带有 `self-hosted,gpu`
标签。

### 5. 在 GitHub 触发 GPU 实验

进入 GitHub 仓库：

`Actions -> GPU Research -> Run workflow`

默认会跑：

```text
experiments/_demo_mnist_cnn.yaml
```

也可以把 input 改成自己的实验 YAML，例如：

```text
experiments/my_experiment.yaml
```

workflow 会上传：

```text
experiments/runs
experiments/feedback
```

## 直接 SSH 运行方案

如果暂时不接 GitHub runner，也可以从本地直接上传代码到已租好的 Vast 机器，不需要
把代码放到 GitHub。

从 Vast 页面复制 SSH 命令，格式一般类似：

```bash
ssh -p 12345 root@23.158.136.85
```

然后在本地仓库运行：

```bash
auto-research vast push --cwd . \
  --ssh "ssh -p 12345 root@23.158.136.85" \
  -e experiments/_demo_mnist_cnn.yaml
```

这条命令会做四件事：

1. 确认远端有 `rsync`、`python3`、`python3-venv` 等基础工具。
2. 把本地代码同步到 Vast 的 `/root/auto-research`。
3. 在远端创建 `.venv` 并安装 `.[dev,anthropic,demo]`。
4. 远端运行实验，并把 `experiments/runs/`、`experiments/feedback/` 拉回本地。

如果只想上传和安装，不想马上运行实验：

```bash
auto-research vast push --cwd . \
  --ssh "ssh -p 12345 root@23.158.136.85" \
  --no-run
```

上传时默认不会同步这些内容：`.venv/`、`.git/`、`.data/`、历史 run/feedback、
`deploy/api.env`、`deploy/vast.env`。这样可以避免把本地虚拟环境、缓存和密钥传上去。

如果想手动 SSH 到 Vast 后直接跑，也可以：

```bash
cd /root/auto-research
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,anthropic,demo]"
nvidia-smi
auto-research run --cwd . -e experiments/_demo_mnist_cnn.yaml
```

运行结果在：

```text
experiments/runs/
experiments/feedback/
```

## 需要和骏一学长确认的点

1. GitHub 仓库地址 `OWNER/REPO` 是哪个。
2. Vast API key 由谁提供、是否可以放在本地 `deploy/api.env`。
3. 使用 RTX 5080 还是先用 RTX 4090/A5000 做稳定验证。
4. 最终要跑哪个真实实验 YAML，而不是只跑 MNIST demo。
5. 结果是只上传 GitHub Actions artifacts，还是还要同步到网盘、S3、或实验记录系统。
