"""Command-line utilities for LeagueSpy."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

from src.config import summarize_config
from src.doctor import format_results, run_preflight
from src.showcase import format_showcase_report, generate_showcase


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeagueSpy utility commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Run environment and config preflight checks")
    doctor_parser.add_argument("--config", default="config.yaml", help="Path to the YAML config file")
    doctor_parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip network/service connectivity checks and focus on local readiness.",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Emit the report as JSON")

    showcase_parser = subparsers.add_parser(
        "showcase",
        help="Generate offline sample LeagueSpy artifacts (images + sample announcement JSON)",
    )
    showcase_parser.add_argument(
        "--output-dir",
        default="showcase-output",
        help="Directory where showcase artifacts should be written.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        checks, config = run_preflight(args.config, offline=args.offline)
        if args.json:
            payload = {
                "config": summarize_config(config) if config else None,
                "checks": [asdict(check) for check in checks],
                "ok": not any(check.status == "fail" for check in checks),
            }
            print(json.dumps(payload, indent=2))
        else:
            print("LeagueSpy doctor report")
            print(format_results(checks))
        return 1 if any(check.status == "fail" for check in checks) else 0

    if args.command == "showcase":
        artifacts = generate_showcase(Path(args.output_dir))
        print(format_showcase_report(artifacts))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
