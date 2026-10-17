import sys
from types import SimpleNamespace

import pipeline.__main__ as cli
from pipeline.stages import c2_network


def test_c2_command_generates_c1_before_running_c2(monkeypatch):
    calls = []
    cfg = object()

    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli,
        "run_c1",
        lambda value: calls.append(("c1", value)) or SimpleNamespace(stage="c1", counts={}),
    )
    monkeypatch.setattr(
        c2_network,
        "run_c2",
        lambda value: calls.append(("c2", value)) or SimpleNamespace(stage="c2", counts={}),
    )
    monkeypatch.setattr(sys, "argv", ["python -m pipeline", "c2"])

    cli.main()

    assert calls == [("c1", cfg), ("c2", cfg)]
