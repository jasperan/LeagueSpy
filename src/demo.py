"""Backward-compatible wrapper around the canonical LeagueSpy showcase generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.showcase import format_showcase_report, generate_showcase


def generate_demo(output_dir: str | Path) -> list[Path]:
    artifacts = generate_showcase(output_dir)
    return [Path(path) for path in artifacts.values()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.demo",
        description="Generate an offline LeagueSpy demo without Discord, Oracle, or a live LLM.",
    )
    parser.add_argument(
        "--output-dir",
        default="demo-output",
        help="Directory where generated artifacts should be written.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    artifacts = generate_showcase(args.output_dir)
    print(format_showcase_report(artifacts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
