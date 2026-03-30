from auto_research.feedback import evaluate_thresholds


def test_thresholds_min_max():
    ok, d = evaluate_thresholds(
        {"loss": 0.4, "accuracy": 0.85},
        {"loss": 0.5, "accuracy": 0.8},
    )
    assert ok
    assert d["loss"]["direction"] == "minimize"
    assert d["accuracy"]["direction"] == "maximize"


def test_thresholds_fail():
    ok, _ = evaluate_thresholds({"loss": 0.9}, {"loss": 0.5})
    assert not ok
