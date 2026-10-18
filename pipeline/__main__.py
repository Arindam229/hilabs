"""Command line entry point for provider-rate pipeline stages."""

from __future__ import annotations

import argparse

from pipeline.config import load_config
from pipeline.stages.c1_index import run_c1


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("stage", choices=("c1", "c2", "c3", "c4", "c5", "c6", "all"))
    parser.add_argument("--rate-file", dest="rate_file", default=None)
    parser.add_argument("--rate-member", dest="rate_member", default=None)
    parser.add_argument("--output-dir", dest="output_dir", default=None)
    parser.add_argument("--c4-path", dest="c4_path", default=None)
    parser.add_argument("--c5-path", dest="c5_path", default=None)
    args = parser.parse_args()
    cfg = load_config()
    c4_uses_c2_queue = args.stage == "c4" and not (args.rate_file or cfg.rate_file)
    if args.stage in {"c1", "c2", "c3", "all"} or c4_uses_c2_queue:
        result = run_c1(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c2", "c3", "all"} or c4_uses_c2_queue:
        from pipeline.stages.c2_network import run_c2

        result = run_c2(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c3", "all"} or c4_uses_c2_queue:
        from pipeline.stages.c3_quality import run_c3

        result = run_c3(cfg)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c4", "all"}:
        from pipeline.stages.c4_rates import run_c4

        result = run_c4(cfg, rate_file=args.rate_file, output_dir=args.output_dir, rate_member=args.rate_member)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c5"}:
        from pathlib import Path

        from pipeline.stages.c5_address import run_c5

        c4p = Path(args.c4_path) if args.c4_path else None
        out = Path(args.output_dir) if args.output_dir else None
        result = run_c5(cfg, c4_path=c4p, output_dir=out)
        print(f"{result.stage}: {result.counts}")
    if args.stage in {"c6"}:
        from pathlib import Path

        from pipeline.stages.c6_final import run_c6

        c5p = Path(args.c5_path) if args.c5_path else None
        result = run_c6(cfg, c5_path=c5p)
        print(f"{result.stage}: {result.counts}")


if __name__ == "__main__":
    main()
