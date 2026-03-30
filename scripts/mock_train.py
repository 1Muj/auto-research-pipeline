#!/usr/bin/env python3
"""Writes metrics.json for CI and local dry runs."""
import json
from pathlib import Path

Path("metrics.json").write_text(
    json.dumps({"loss": 0.42, "accuracy": 0.91, "epoch": 1}, indent=2),
    encoding="utf-8",
)
