"""Thin reusable wrapper around the existing Python pipeline CLI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run(args: list[str], env: dict[str, str] | None = None) -> int:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    print("Running:", " ".join(args))
    result = subprocess.run(args, cwd=ROOT, env=full_env, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python scripts/pipeline_commands.py <c1|c2|c4|test|current> [args...]")
        return 2

    command = argv[0]
    rest = argv[1:]

    if command == "c1":
        return _run([PYTHON, "-m", "pipeline", "c1", *rest])
    if command == "c2":
        return _run([PYTHON, "-m", "pipeline", "c2", *rest])
    if command == "c4":
        return _run([PYTHON, "-m", "pipeline", "c4", *rest])
    if command == "test":
        return _run([PYTHON, "-m", "ruff", "check", ".", *rest]) or _run(
            [PYTHON, "-m", "pytest", "-q", *rest]
        )
    if command == "current":
        rc = _run([PYTHON, "-m", "pipeline", "c1", *rest])
        if rc != 0:
            return rc
        rc = _run([PYTHON, "-m", "pipeline", "c2", *rest])
        if rc != 0:
            return rc
        return _run([PYTHON, "-m", "pipeline", "c4", *rest])

    # Pass through unknown commands to the CLI.
    return _run([PYTHON, "-m", "pipeline", command, *rest])


if __name__ == "__main__":
    raise SystemExit(main())
