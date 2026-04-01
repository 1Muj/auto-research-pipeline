from pathlib import Path

import yaml

from auto_research.preflight import preflight_experiment


def test_preflight_template_ok(tmp_path: Path) -> None:
    root = tmp_path
    exp = root / "ex.yaml"
    exp.write_text(
        yaml.safe_dump(
            {
                "name": "t",
                "command": ["python", "-c", "print(1)"],
                "metrics_path": "metrics.json",
                "success_threshold": {"loss": 0.1},
            }
        ),
        encoding="utf-8",
    )
    errs, _ = preflight_experiment(exp, root)
    assert errs == []


def test_preflight_absolute_metrics_rejected(tmp_path: Path) -> None:
    root = tmp_path
    exp = root / "bad.yaml"
    exp.write_text(
        yaml.safe_dump(
            {
                "name": "t",
                "command": ["true"],
                "metrics_path": "/tmp/x.json",
            }
        ),
        encoding="utf-8",
    )
    errs, _ = preflight_experiment(exp, root)
    assert any("relative" in e.lower() for e in errs)


def test_preflight_missing_file(tmp_path: Path) -> None:
    errs, _ = preflight_experiment(tmp_path / "nope.yaml", tmp_path)
    assert errs
