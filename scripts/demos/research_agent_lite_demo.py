#!/usr/bin/env python3
"""Small deterministic demos for reviewer/visualization/Vast workflows."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path


def _detect_device() -> tuple[str, bool]:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0), True
        return "cpu", False
    except Exception:
        return "python-only", False


def _gpu_probe() -> float:
    try:
        import torch

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        a = torch.randn((512, 512), device=device)
        b = torch.randn((512, 512), device=device)
        start = time.perf_counter()
        for _ in range(8):
            c = a @ b
            if device.type == "cuda":
                torch.cuda.synchronize()
        _ = float(c[0, 0].detach().cpu())
        return round(time.perf_counter() - start, 4)
    except Exception:
        start = time.perf_counter()
        total = 0.0
        for i in range(20000):
            total += math.sin(i) * math.cos(i / 3)
        return round(time.perf_counter() - start + abs(total) * 0.0, 4)


def _metrics(mode: str, max_seconds: float) -> dict[str, object]:
    started = time.perf_counter()
    device, cuda_available = _detect_device()
    probe_sec = _gpu_probe()
    time.sleep(min(max_seconds, 0.2))
    elapsed = time.perf_counter() - started

    if mode == "ml-intern-lite":
        return {
            "task_plan_score": 0.91,
            "tool_trace_events": 7,
            "artifact_score": 0.88,
            "shipping_readiness": 0.86,
            "sandbox_or_remote_runtime": True,
            "device": device,
            "cuda_available": cuda_available,
            "gpu_probe_sec": probe_sec,
            "duration_sec": round(elapsed, 4),
            "exit_code": 0,
        }

    if mode == "co-scientist-lite":
        return {
            "hypothesis_generation_score": 0.88,
            "multi_agent_critique_score": 0.85,
            "ranking_confidence": 0.83,
            "human_in_loop_ready": 1.0,
            "candidate_hypotheses": 4,
            "device": device,
            "cuda_available": cuda_available,
            "gpu_probe_sec": probe_sec,
            "duration_sec": round(elapsed, 4),
            "exit_code": 0,
        }

    if mode == "paperbench-lite":
        return {
            "paper_understanding": 0.86,
            "code_reproduction": 0.81,
            "rubric_score": 0.84,
            "artifact_completeness": 0.90,
            "replication_subtasks": 6,
            "device": device,
            "cuda_available": cuda_available,
            "gpu_probe_sec": probe_sec,
            "duration_sec": round(elapsed, 4),
            "exit_code": 0,
        }

    return {
        "hypothesis_quality": 0.84,
        "experiment_success": 1.0,
        "reviewer_score": 0.82,
        "visualization_ready": 1.0,
        "device": device,
        "cuda_available": cuda_available,
        "gpu_probe_sec": probe_sec,
        "duration_sec": round(elapsed, 4),
        "exit_code": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=[
            "ai-scientist-lite",
            "co-scientist-lite",
            "paperbench-lite",
            "ml-intern-lite",
        ],
        required=True,
    )
    parser.add_argument("--metrics-path", type=Path, default=Path("metrics.json"))
    parser.add_argument("--max-seconds", type=float, default=1.0)
    args = parser.parse_args()

    body = _metrics(args.mode, args.max_seconds)
    args.metrics_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    print(json.dumps(body, ensure_ascii=False))


if __name__ == "__main__":
    main()
