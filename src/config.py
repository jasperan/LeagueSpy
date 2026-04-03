from __future__ import annotations

import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.models import SummonerConfig

PLACEHOLDER_DISCORD_TOKENS = {
    "",
    "YOUR_DISCORD_BOT_TOKEN",
    "YOUR_TOKEN_HERE",
    "CHANGE_ME",
}
ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


class ConfigError(ValueError):
    """Raised when a config file is missing or invalid."""


@dataclass(slots=True)
class ValidationIssue:
    key: str
    message: str

    @property
    def path(self) -> str:
        return self.key


@dataclass(slots=True)
class ValidationReport:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def is_valid(self) -> bool:
        return self.ok

    def add_error(self, key: str, message: str) -> None:
        self.errors.append(ValidationIssue(key=key, message=message))

    def add_warning(self, key: str, message: str) -> None:
        self.warnings.append(ValidationIssue(key=key, message=message))

    def format_lines(self) -> list[str]:
        lines: list[str] = []
        lines.extend(f"ERROR {issue.key}: {issue.message}" for issue in self.errors)
        lines.extend(f"WARNING {issue.key}: {issue.message}" for issue in self.warnings)
        return lines

    def render(self, path: str | Path = "config.yaml") -> str:
        return format_config_report(self, path)


def read_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping in {config_path}")

    return _resolve_env_values(data)


def summarize_config(config: dict[str, Any]) -> dict[str, Any]:
    players = config.get("players") or []
    summoner_count = 0
    player_names: list[str] = []
    for player in players:
        if isinstance(player, dict):
            if isinstance(player.get("name"), str):
                player_names.append(player["name"])
            summoners = player.get("summoners") or []
            if isinstance(summoners, list):
                summoner_count += len(summoners)

    features = config.get("features") or {}
    enabled_features = sorted(
        key for key, value in features.items() if value is True
    ) if isinstance(features, dict) else []

    return {
        "player_count": len(players) if isinstance(players, list) else 0,
        "summoner_count": summoner_count,
        "players": player_names,
        "default_region": config.get("scraping", {}).get("region", "euw"),
        "enabled_features": enabled_features,
    }


def build_summoner_list(config: dict[str, Any]) -> list[SummonerConfig]:
    default_region = config.get("scraping", {}).get("region", "euw")
    summoners: list[SummonerConfig] = []
    for player in config.get("players", []):
        if not isinstance(player, dict):
            continue
        player_name = player.get("name", "unknown")
        for summoner in player.get("summoners", []):
            if not isinstance(summoner, dict) or "slug" not in summoner:
                continue
            summoners.append(
                SummonerConfig(
                    player_name=player_name,
                    slug=summoner["slug"],
                    region=summoner.get("region", default_region),
                )
            )
    return summoners


def validate_config(config: dict[str, Any], *, mode: str = "runtime") -> ValidationReport:
    runtime = mode == "runtime"
    normalized = deepcopy(config)
    report = ValidationReport(normalized=normalized, summary=summarize_config(normalized))

    discord_cfg = _require_mapping(normalized, "discord", report)
    oracle_cfg = _require_mapping(normalized, "oracle", report)
    scraping_cfg = _require_mapping(normalized, "scraping", report)
    features_cfg = _optional_mapping(normalized, "features", report)
    llm_cfg = _optional_mapping(normalized, "llm", report)
    players = normalized.get("players")

    token = _require_string(discord_cfg, "token", "discord.token", report)
    _check_unresolved_env_ref(token, "discord.token", report, runtime=runtime)
    if token is not None and (
        token.strip() in PLACEHOLDER_DISCORD_TOKENS or token.strip().startswith("${")
    ):
        message = "still set to a placeholder token"
        if runtime:
            report.add_error("discord.token", message)
        else:
            report.add_warning("discord.token", message)

    channel_id = _require_int(discord_cfg, "channel_id", "discord.channel_id", report)
    if channel_id is not None and channel_id <= 0:
        message = "must be a real Discord channel ID (> 0) before runtime"
        if runtime:
            report.add_error("discord.channel_id", message)
        else:
            report.add_warning("discord.channel_id", message)

    oracle_user = _require_string(oracle_cfg, "user", "oracle.user", report)
    oracle_password = _require_string(oracle_cfg, "password", "oracle.password", report)
    oracle_dsn = _require_string(oracle_cfg, "dsn", "oracle.dsn", report)
    _check_unresolved_env_ref(oracle_user, "oracle.user", report, runtime=runtime)
    _check_unresolved_env_ref(oracle_password, "oracle.password", report, runtime=runtime)
    _check_unresolved_env_ref(oracle_dsn, "oracle.dsn", report, runtime=runtime)

    interval_minutes = _require_int(scraping_cfg, "interval_minutes", "scraping.interval_minutes", report)
    if interval_minutes is not None and interval_minutes <= 0:
        report.add_error("scraping.interval_minutes", "must be greater than 0")

    live_check_minutes = _optional_int(scraping_cfg, "live_check_minutes", "scraping.live_check_minutes", report)
    if live_check_minutes is not None and live_check_minutes <= 0:
        report.add_error("scraping.live_check_minutes", "must be greater than 0")

    region = _require_string(scraping_cfg, "region", "scraping.region", report)
    _check_unresolved_env_ref(region, "scraping.region", report, runtime=runtime)
    if region is not None and not region.strip():
        report.add_error("scraping.region", "cannot be empty")
    elif region is not None:
        scraping_cfg["region"] = region.lower()

    if not isinstance(players, list):
        report.add_error("players", "must be a list of players")
    else:
        if not players:
            report.add_warning(
                "players",
                "no players configured yet; the bot can start, but nothing will be tracked",
            )

        seen_slugs: set[tuple[str, str]] = set()
        default_region = region or "euw"
        for player_index, player in enumerate(players):
            player_key = f"players[{player_index}]"
            if not isinstance(player, dict):
                report.add_error(player_key, "must be a mapping")
                continue

            name = _require_string(player, "name", f"{player_key}.name", report)
            if name is not None and not name.strip():
                report.add_error(f"{player_key}.name", "cannot be empty")

            summoners = player.get("summoners")
            if not isinstance(summoners, list):
                report.add_error(f"{player_key}.summoners", "must be a list")
                continue

            if not summoners:
                report.add_warning(f"{player_key}.summoners", "has no summoner entries yet")

            for summoner_index, summoner in enumerate(summoners):
                summoner_key = f"{player_key}.summoners[{summoner_index}]"
                if not isinstance(summoner, dict):
                    report.add_error(summoner_key, "must be a mapping")
                    continue

                slug = _require_string(summoner, "slug", f"{summoner_key}.slug", report)
                _check_unresolved_env_ref(slug, f"{summoner_key}.slug", report, runtime=runtime)
                summoner_region = summoner.get("region", default_region)
                if not isinstance(summoner_region, str) or not summoner_region.strip():
                    report.add_error(f"{summoner_key}.region", "must be a non-empty string")
                    continue
                _check_unresolved_env_ref(summoner_region, f"{summoner_key}.region", report, runtime=runtime)
                summoner["region"] = summoner_region.lower()
                if slug is not None:
                    slug_key = (slug.lower(), summoner["region"])
                    if slug_key in seen_slugs:
                        report.add_error(
                            f"{summoner_key}.slug",
                            f"duplicate summoner slug '{slug}' for region '{summoner['region']}'",
                        )
                    else:
                        seen_slugs.add(slug_key)

    ask_enabled = _feature_enabled(features_cfg, "ask", default=True)
    llm_backed_features = [
        feature
        for feature in ("roast", "analyst")
        if _feature_enabled(features_cfg, feature, default=False)
    ]
    if ask_enabled:
        llm_backed_features.append("ask")

    if llm_backed_features and not llm_cfg:
        report.add_warning(
            "llm",
            "LLM-backed features are enabled but no llm config is present: "
            + ", ".join(sorted(set(llm_backed_features))),
        )

    if llm_cfg:
        llm_base_url = _require_string(llm_cfg, "base_url", "llm.base_url", report)
        llm_model = _require_string(llm_cfg, "model", "llm.model", report)
        _check_unresolved_env_ref(llm_base_url, "llm.base_url", report, runtime=runtime)
        _check_unresolved_env_ref(llm_model, "llm.model", report, runtime=runtime)
        max_tokens = _optional_int(llm_cfg, "max_tokens", "llm.max_tokens", report)
        if max_tokens is not None and max_tokens <= 0:
            report.add_error("llm.max_tokens", "must be greater than 0")

    report.summary = summarize_config(report.normalized)
    return report


def load_config(path: str | Path = "config.yaml", *, mode: str = "runtime") -> dict[str, Any]:
    config = read_config(path)
    report = validate_config(config, mode=mode)
    if report.errors:
        raise ConfigError("\n".join(report.format_lines()))
    return report.normalized


def load_and_validate_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    return load_config(path, mode="runtime")


def build_config_report(path: str | Path = "config.yaml", *, mode: str = "doctor") -> ValidationReport:
    try:
        config = read_config(path)
    except ConfigError as exc:
        report = ValidationReport()
        report.add_error("config", str(exc))
        return report

    report = validate_config(config, mode=mode)
    report.summary = summarize_config(config)
    return report


def count_summoners(config: dict[str, Any]) -> int:
    return summarize_config(config)["summoner_count"]


def enabled_features(config: dict[str, Any]) -> str:
    features = summarize_config(config)["enabled_features"]
    return ", ".join(features) if features else "none"


def format_config_report(report: ValidationReport, path: str | Path = "config.yaml") -> str:
    location = Path(path)
    lines = [f"Config report for {location}:"]
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"  - {issue.key}: {issue.message}" for issue in report.errors)
    else:
        lines.append("Errors: none")
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {issue.key}: {issue.message}" for issue in report.warnings)
    else:
        lines.append("Warnings: none")
    if report.summary:
        enabled = ", ".join(report.summary["enabled_features"]) if report.summary["enabled_features"] else "none"
        lines.append(
            "Summary: "
            f"players={report.summary['player_count']}, "
            f"summoners={report.summary['summoner_count']}, "
            f"features={enabled}"
        )
    return "\n".join(lines)


def _require_mapping(config: dict[str, Any], key: str, report: ValidationReport) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        report.add_error(key, "must be a mapping")
        return {}
    return value


def _optional_mapping(config: dict[str, Any], key: str, report: ValidationReport) -> dict[str, Any]:
    value = config.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        report.add_error(key, "must be a mapping")
        return {}
    return value


def _require_string(config: dict[str, Any], key: str, full_key: str, report: ValidationReport) -> str | None:
    value = config.get(key)
    if not isinstance(value, str):
        report.add_error(full_key, "must be a string")
        return None
    return value


def _require_int(config: dict[str, Any], key: str, full_key: str, report: ValidationReport) -> int | None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        report.add_error(full_key, "must be an integer")
        return None
    return value


def _optional_int(config: dict[str, Any], key: str, full_key: str, report: ValidationReport) -> int | None:
    if key not in config:
        return None
    return _require_int(config, key, full_key, report)


def _feature_enabled(features_cfg: dict[str, Any], key: str, *, default: bool) -> bool:
    value = features_cfg.get(key, default)
    return bool(value)


def _check_unresolved_env_ref(value: str | None, key: str, report: ValidationReport, *, runtime: bool) -> None:
    if not isinstance(value, str) or not value.strip().startswith("${"):
        return
    message = "references an unset environment variable"
    if runtime:
        report.add_error(key, message)
    else:
        report.add_warning(key, message)


def _resolve_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_values(item) for item in value]
    if isinstance(value, str):
        return ENV_REF_RE.sub(
            lambda match: os.getenv(
                match.group(1),
                match.group(2) if match.group(2) is not None else match.group(0),
            ),
            value,
        )
    return value
