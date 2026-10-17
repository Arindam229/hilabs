"""Command line entry point for provider-rate pipeline stages."""

from __future__ import annotations

import argparse

from pipeline.config import load_config
from pipeline.stages.c1_index import run_c1


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("stage", choices=("c1", "c2", "c4", "all"))
    parser.add_argument("--rate-file", dest="rate_file", default=None)
    parser.add_argument("--rate-member", dest="rate_member", default=None)
    parser.add_argument("--output-dir", dest="output_dir", default=None)
    args = parser.parse_args()
    cfg = load_config()
    if args.stage in {"c1", "c2", "all"}:
        result = run_c1(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c2", "all"}:
        from pipeline.stages.c2_network import run_c2

        result = run_c2(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c4", "all"}:
        from pipeline.stages.c4_rates import run_c4

        result = run_c4(cfg, rate_file=args.rate_file, output_dir=args.output_dir, rate_member=args.rate_member)
        print(f"{result.stage}: {result.counts}")


if __name__ == "__main__":
    main()
