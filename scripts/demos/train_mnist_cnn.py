#!/usr/bin/env python3
"""MNIST + small CNN on CPU/CUDA; runs until --max-seconds wall time, then writes metrics.json."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torchvision import datasets, transforms


class SmallCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(x))
        x = F.max_pool2d(x, 2)
        x = F.relu(self.conv2(x))
        x = F.max_pool2d(x, 2)
        x = torch.flatten(x, 1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


def train_epoch(
    model: nn.Module,
    device: torch.device,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0
    for data, target in loader:
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


@torch.no_grad()
def evaluate(model: nn.Module, device: torch.device, loader: DataLoader) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    n = 0
    for data, target in loader:
        data, target = data.to(device), target.to(device)
        output = model(data)
        total_loss += F.nll_loss(output, target, reduction="sum").item()
        pred = output.argmax(dim=1)
        correct += int(pred.eq(target).sum().item())
        n += len(target)
    return total_loss / max(n, 1), correct / max(n, 1)


def main() -> None:
    p = argparse.ArgumentParser(description="MNIST CNN demo for auto-research (~10 min CPU).")
    p.add_argument("--max-seconds", type=float, default=600.0, help="Wall-time training budget.")
    p.add_argument("--data-dir", type=Path, default=Path(".data/mnist"))
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--metrics-path", type=Path, default=Path("metrics.json"))
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(42)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(42)

    tfm = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
    )
    train_ds = datasets.MNIST(
        str(args.data_dir), train=True, download=True, transform=tfm
    )
    test_ds = datasets.MNIST(
        str(args.data_dir), train=False, download=True, transform=tfm
    )
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0, pin_memory=False
    )
    test_loader = DataLoader(
        test_ds, batch_size=args.batch_size, shuffle=False, num_workers=0, pin_memory=False
    )

    model = SmallCNN().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    t0 = time.monotonic()
    deadline = t0 + args.max_seconds
    epoch = 0
    last_train_loss = 0.0
    val_loss, val_acc = float("inf"), 0.0

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining < 5:
            break
        last_train_loss = train_epoch(model, device, train_loader, opt)
        val_loss, val_acc = evaluate(model, device, test_loader)
        epoch += 1

    duration = time.monotonic() - t0
    body = {
        "val_loss": round(val_loss, 6),
        "val_accuracy": round(val_acc, 6),
        "train_loss": round(last_train_loss, 6),
        "epochs": epoch,
        "duration_sec": round(duration, 2),
        "device": str(device),
        "exit_code": 0,
    }
    args.metrics_path.write_text(json.dumps(body, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
