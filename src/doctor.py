from __future__ import annotations

import argparse
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import httpx

from src.config import ConfigError, format_config_report, read_config, summarize_config, validate_config
from src.database import Database


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass(slots=True)
class DoctorReport:
    checks: list[CheckResult]
    config: dict | None
    config_report: object | None

    @property
    def ok(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)


def check_python_runtime() -> CheckResult:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 12):
        return CheckResult("python", "ok", detail)
    return CheckResult("python", "warn", f"{detail} detected; README currently recommends Python 3.12+")


def check_python_modules() -> list[CheckResult]:
    modules = [
        ("discord", "discord.py"),
        ("playwright", "playwright"),
        ("oracledb", "oracledb"),
        ("yaml", "PyYAML"),
        ("PIL", "Pillow"),
        ("httpx", "httpx"),
    ]
    results: list[CheckResult] = []
    for module_name, display_name in modules:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            results.append(CheckResult(f"module:{display_name}", "fail", "not installed"))
        else:
            results.append(CheckResult(f"module:{display_name}", "ok", "installed"))
    return results


def check_playwright_ready() -> CheckResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return CheckResult("playwright", "fail", f"unable to import Playwright: {exc}")

    try:
        with sync_playwright() as playwright:
            executable_path = Path(playwright.chromium.executable_path)
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        return CheckResult("playwright", "fail", f"Chromium launch failed: {exc}")

    return CheckResult("playwright", "ok", f"Chromium launches successfully ({executable_path})")


check_playwright_browser = check_playwright_ready


def check_oracle_connection(config: dict) -> CheckResult:
    oracle_cfg = config["oracle"]
    try:
        db = Database(
            user=oracle_cfg["user"],
            password=oracle_cfg["password"],
            dsn=oracle_cfg["dsn"],
        )
    except Exception as exc:
        return CheckResult("oracle", "fail", str(exc))

    try:
        db.close()
    except Exception:
        pass
    return CheckResult("oracle", "ok", f"connected to {oracle_cfg['dsn']}")


def check_llm_endpoint(config: dict) -> CheckResult:
    llm_cfg = config.get("llm") or {}
    base_url = llm_cfg.get("base_url")
    if not base_url:
        return CheckResult("vllm", "skip", "no llm.base_url configured")

    models_url = base_url.rstrip("/") + "/models"
    try:
        response = httpx.get(models_url, timeout=4.0)
        response.raise_for_status()
    except Exception as exc:
        return CheckResult("vllm", "fail", f"{models_url} unreachable: {exc}")

    return CheckResult("vllm", "ok", f"{models_url} responded with {response.status_code}")


def run_doctor(config_path: str | Path, *, offline: bool = False) -> DoctorReport:
    checks: list[CheckResult] = [check_python_runtime()]

    try:
        config = read_config(config_path)
    except ConfigError as exc:
        checks.append(CheckResult("config", "fail", str(exc)))
        return DoctorReport(checks=checks, config=None, config_report=None)

    config_report = validate_config(config, mode="doctor")
    checks.append(
        CheckResult(
            "config",
            "ok" if config_report.ok else "fail",
            format_config_report(config_report, config_path),
        )
    )
    for issue in config_report.errors:
        checks.append(CheckResult(issue.key, "fail", issue.message))
    for issue in config_report.warnings:
        checks.append(CheckResult(issue.key, "warn", issue.message))
    checks.extend(check_python_modules())
    checks.append(check_playwright_ready())

    if offline:
        checks.append(CheckResult("oracle", "skip", "offline mode"))
        checks.append(CheckResult("vllm", "skip", "offline mode"))
    else:
        checks.append(check_oracle_connection(config))
        checks.append(check_llm_endpoint(config))

    config_report.summary = summarize_config(config)
    return DoctorReport(checks=checks, config=config, config_report=config_report)


def run_preflight(config_path: str | Path, *, offline: bool = False) -> tuple[list[CheckResult], dict | None]:
    report = run_doctor(config_path, offline=offline)
    return report.checks, report.config


def format_results(results: Iterable[CheckResult]) -> str:
    icon_map = {"ok": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    lines = []
    for result in results:
        icon = icon_map.get(result.status, result.status.upper())
        lines.append(f"[{icon}] {result.name}: {result.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LeagueSpy preflight and environment doctor.")
    parser.add_argument("--config", default="config.yaml", help="Path to the LeagueSpy YAML config file (default: config.yaml).")
    parser.add_argument("--offline", action="store_true", help="Skip live Oracle and vLLM connectivity checks.")
    args = parser.parse_args(argv)

    report = run_doctor(args.config, offline=args.offline)
    print(format_results(report.checks))

    if report.config is not None:
        summary = summarize_config(report.config)
        enabled = ", ".join(summary["enabled_features"]) or "none"
        print(
            f"\nSummary: {summary['player_count']} player(s), "
            f"{summary['summoner_count']} summoner(s), features={enabled}"
        )

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
