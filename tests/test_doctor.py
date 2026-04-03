from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from src.doctor import CheckResult, check_playwright_ready, run_doctor


def _write_config(path: Path) -> Path:
    config = {
        "discord": {"token": "token", "channel_id": 123},
        "oracle": {"user": "user", "password": "pw", "dsn": "dsn"},
        "scraping": {"interval_minutes": 5, "live_check_minutes": 2, "region": "euw"},
        "llm": {"base_url": "http://localhost:8000/v1", "model": "qwen3.5:9b"},
        "features": {"roast": True, "analytics": True, "ask": True},
        "players": [{"name": "jasper", "summoners": [{"slug": "jasper-1971", "region": "euw"}]}],
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@patch("playwright.sync_api.sync_playwright")
def test_check_playwright_ready_reports_success(mock_sync_playwright):
    browser = MagicMock()
    chromium = SimpleNamespace(launch=MagicMock(return_value=browser), executable_path="/tmp/chromium")
    mock_sync_playwright.return_value.__enter__.return_value = SimpleNamespace(chromium=chromium)

    result = check_playwright_ready()

    assert result.status == "ok"
    assert "Chromium launches successfully" in result.detail
    browser.close.assert_called_once()


@patch("src.doctor.check_playwright_ready")
def test_run_doctor_offline_skips_network_checks(mock_playwright, tmp_path):
    mock_playwright.return_value = CheckResult("playwright", "ok", "ready")
    config_path = _write_config(tmp_path / "config.yaml")

    report = run_doctor(config_path, offline=True)
    checks = {check.name: check.status for check in report.checks}

    assert report.config_report is not None
    assert report.config_report.ok is True
    assert checks["playwright"] == "ok"
    assert checks["oracle"] == "skip"
    assert checks["vllm"] == "skip"


@patch("src.doctor.httpx.get")
@patch("src.doctor.Database")
@patch("src.doctor.check_playwright_ready")
def test_run_doctor_online_runs_all_checks(mock_playwright, mock_database, mock_get, tmp_path):
    mock_playwright.return_value = CheckResult("playwright", "ok", "ready")
    mock_database.return_value = MagicMock()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    config_path = _write_config(tmp_path / "config.yaml")
    report = run_doctor(config_path, offline=False)
    checks = {check.name: check.status for check in report.checks}

    assert report.ok is True
    assert checks["oracle"] == "ok"
    assert checks["vllm"] == "ok"
