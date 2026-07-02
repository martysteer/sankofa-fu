from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import IndexConfig
from .index import build_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sankofa-fu")
    sub = parser.add_subparsers(dest="command", required=True)
    p_index = sub.add_parser("index", help="build authority index from CSV")
    p_index.add_argument("csv", type=Path)
    p_index.add_argument("--config", type=Path, required=True)
    p_index.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.config.exists():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 2
    cfg = IndexConfig.from_yaml(args.config)
    build_index(args.csv, cfg, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
