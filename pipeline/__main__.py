"""Command line entry point for provider-rate pipeline stages."""

from __future__ import annotations

import argparse

from pipeline.config import load_config
from pipeline.stages.c1_index import run_c1


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("stage", choices=("c1", "c2", "all"))
    args = parser.parse_args()
    cfg = load_config()
    if args.stage in {"c1", "all"}:
        result = run_c1(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c2", "all"}:
        from pipeline.stages.c2_network import run_c2

        result = run_c2(cfg)
        print(f"{result.stage}: {result.counts}")


if __name__ == "__main__":
    main()
