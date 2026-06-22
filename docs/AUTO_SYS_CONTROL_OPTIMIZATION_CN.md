# AutoTune-Control：面向控制系统的自动优化 demo

## 背景

学长建议把方向从泛化的 `auto-research` 收窄到一个 specific system，例如 robotics、
communication 或 control system。本分支选择 **control system optimization**，因为它不依赖
真实机器人硬件，也不需要复杂通信仿真器，但仍能展示自动系统优化的完整闭环。

## 参考的 recent auto sys / agentic system 思路

| 工作 | 可借鉴点 | AutoTune-Control 中的对应 |
|---|---|---|
| ADAS / Meta Agent Search | meta-agent 迭代设计、评估并归档 agent/system design | `trial_archive` 保存每组 PID 参数和评价，后续 proposal 围绕 archive refine |
| LA-RCS robot control | plan / observe / execute / revise 的机器人控制闭环 | `propose -> simulate -> evaluate -> critique -> refine` |
| Agentic RAN / autonomous network optimization | 持续监控、诊断原因、自动优化性能 | `critique` 解释 tracking error、overshoot、energy cost 的失败原因 |
| RL / ML PID tuning | 用搜索或学习方法自动调控制器参数 | 在二阶系统上自动搜索 PID `Kp, Ki, Kd` |

参考链接：

- ADAS / Meta Agent Search: https://arxiv.org/abs/2408.08435
- LA-RCS: https://arxiv.org/html/2505.18214v1
- Ericsson agentic autonomous network optimization: https://www.ericsson.com/en/blog/2025/7/agentic-ai-pathway-to-autonomous-network-level-5
- RL PID tuning example: https://www.mathworks.com/help/reinforcement-learning/ug/tune-pi-controller-using-td3.html

## 具体任务

仿真一个二阶动态系统：

```text
x'' + damping * x' + stiffness * x = u
```

自动搜索 PID 控制器：

```text
u = Kp * error + Ki * integral(error) + Kd * derivative(error)
```

优化目标：

- 降低 tracking error
- 缩短 settling time
- 控制 overshoot
- 降低 energy cost
- 保持 stability

## 实现文件

| 文件 | 作用 |
|---|---|
| `scripts/demos/control_autotune_demo.py` | PID 搜索、仿真、评价、critique、dashboard 生成 |
| `experiments/_demo_control_autotune.yaml` | auto-research 实验入口 |
| `docs/RUN_CONTROL_AUTOTUNE_CN.md` | 从本地/Vast 跑 demo 的步骤 |
| `experiments/agent_output/control_autotune_dashboard.html` | 控制系统专属可视化 |

## 输出 metrics

运行后会写入 `metrics.json`，关键字段：

```json
{
  "best_tracking_error": 0.0,
  "settling_time": 0.0,
  "overshoot": 0.0,
  "energy_cost": 0.0,
  "stability_score": 1.0,
  "relative_improvement": 0.0,
  "iterations": 28,
  "best_gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0},
  "loop": "propose -> simulate -> evaluate -> critique -> refine"
}
```

## 为什么这是 specific auto system

它不是只做文本 agent，也不是泛泛的 AI Scientist demo。它有明确系统对象：

```text
plant dynamics + PID controller + closed-loop response + optimization objective
```

同时它仍然接入已有 `auto-research` 基础设施：

```text
YAML experiment -> run -> metrics.json -> feedback -> review -> dashboard -> Vast deployment
```

这正好可以向学长说明：我们把 automated research pipeline 具体落到了一个
control system optimization 场景里。
