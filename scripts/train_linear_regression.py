#!/usr/bin/env python3
"""
Tiny "real" experiment: fit y = a*x + b with gradient descent on synthetic data.

Writes metrics JSON for the auto-research pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def generate_data(n: int, seed: int) -> tuple[list[float], list[float]]:
    rng = random.Random(seed)
    xs: list[float] = []
    ys: list[float] = []
    for _ in range(n):
        x = rng.uniform(-2.0, 2.0)
        noise = rng.gauss(0.0, 0.2)
        y = 2.0 * x + 1.0 + noise
        xs.append(x)
        ys.append(y)
    return xs, ys


def mse(y_true: list[float], y_pred: list[float]) -> float:
    s = 0.0
    for yt, yp in zip(y_true, y_pred, strict=True):
        d = yt - yp
        s += d * d
    return s / max(1, len(y_true))


def r2_score(y_true: list[float], y_pred: list[float]) -> float:
    mean = sum(y_true) / max(1, len(y_true))
    ss_tot = sum((yt - mean) ** 2 for yt in y_true)
    ss_res = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred, strict=True))
    if ss_tot == 0:
        return 0.0
    return 1.0 - (ss_res / ss_tot)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=512, help="number of points")
    p.add_argument("--seed", type=int, default=0, help="random seed")
    p.add_argument("--epochs", type=int, default=400, help="gradient descent steps")
    p.add_argument("--lr", type=float, default=0.05, help="learning rate")
    p.add_argument("--metrics-path", type=str, default="metrics.json", help="output metrics json path")
    args = p.parse_args()

    xs, ys = generate_data(args.n, args.seed)

    a = 0.0
    b = 0.0
    n = float(len(xs))

    for _ in range(args.epochs):
        da = 0.0
        db = 0.0
        for x, y in zip(xs, ys, strict=True):
            pred = a * x + b
            err = pred - y
            da += (2.0 / n) * err * x
            db += (2.0 / n) * err
        if not (math.isfinite(da) and math.isfinite(db)):
            break
        a -= args.lr * da
        b -= args.lr * db

    preds = [a * x + b for x in xs]
    metrics = {
        "loss": mse(ys, preds),
        "r2": r2_score(ys, preds),
        "epochs": args.epochs,
        "lr": args.lr,
        "a": a,
        "b": b,
        "n": args.n,
        "seed": args.seed,
    }

    Path(args.metrics_path).write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

