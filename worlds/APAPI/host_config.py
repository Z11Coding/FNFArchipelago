from __future__ import annotations

"""Host config helpers for universal tracker snapshot settings."""

from pathlib import Path
from typing import Any, Dict
import logging

import yaml

from Utils import user_path


logger = logging.getLogger("APAPI")


APAPI_DEFAULT_CONFIG = {
    "apapi": {
        "debug": {
            "enabled": False,
        },
        "universal_tracker_snapshot": {
            "enabled": True,
            "verbose_location_log": True,
        },
        "verbose_collection_state": {
            "enabled": False,
            "log_has": True,
            "log_has_all": True,
            "log_count": True,
            "log_can_reach": True,
            "log_can_reach_location": True,
            "log_can_reach_region": True,
            "log_locations_checked": True,
            "max_log_entries": 200000,
            "log_stack_depth": 6,
            "report_on_fill_error": True,
            "ask_force_continue": True,
        }
    }
}


def _get_host_yaml_path() -> Path:
    """Returns: host.yaml path."""
    return Path(user_path("host.yaml"))


def _safe_load_yaml(path: Path) -> Dict[str, Any]:
    """Input: path. Returns: loaded dict or {}."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)
        return loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        logger.warning("APAPI could not load host.yaml (%s): %s", path, exc)
        return {}


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Input: base, incoming. Returns: merged dict."""
    merged = dict(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_apapi_config_exists() -> Dict[str, Any]:
    """Returns: merged host.yaml config (ensures defaults exist)."""
    config_path = _get_host_yaml_path()
    existing = _safe_load_yaml(config_path)
    merged = _deep_merge(APAPI_DEFAULT_CONFIG, existing)

    if merged != existing:
        try:
            with config_path.open("w", encoding="utf-8") as stream:
                yaml.safe_dump(merged, stream, default_flow_style=False, sort_keys=False)
            logger.info("APAPI wrote default config section to %s", config_path)
        except Exception as exc:
            logger.warning("APAPI could not write host.yaml (%s): %s", config_path, exc)

    # Sync debug flag to debug module (host.yaml is source of truth, defaults to True).
    try:
        from .debug import set_debug_enabled as _set_debug

        debug_cfg: Any = merged.get("apapi", {}).get("debug", {}) if isinstance(merged.get("apapi"), dict) else {}
        enabled: Any = True
        if isinstance(debug_cfg, dict):
            enabled = debug_cfg.get("enabled", True)
        elif isinstance(debug_cfg, bool):
            enabled = debug_cfg
        else:
            # legacy flat keys: apapi.debug_messages / apapi.enable_debug
            apapi_cfg = merged.get("apapi", {})
            if isinstance(apapi_cfg, dict):
                for _k in ("debug_messages", "enable_debug", "debug_enabled"):
                    if _k in apapi_cfg:
                        enabled = apapi_cfg[_k]
                        break
        _set_debug(bool(enabled))
    except Exception:
        pass

    return merged


def get_universal_tracker_snapshot_config() -> Dict[str, Any]:
    """Returns: universal tracker snapshot config dict."""
    config = ensure_apapi_config_exists()
    apapi_cfg = config.get("apapi", {}) if isinstance(config, dict) else {}
    ut_cfg = apapi_cfg.get("universal_tracker_snapshot", {}) if isinstance(apapi_cfg, dict) else {}

    defaults = APAPI_DEFAULT_CONFIG["apapi"]["universal_tracker_snapshot"]
    effective = dict(defaults)
    if isinstance(ut_cfg, dict):
        effective.update(ut_cfg)
    return effective


def is_universal_tracker_snapshot_enabled() -> bool:
    """Returns: True if snapshot is enabled."""
    cfg = get_universal_tracker_snapshot_config()
    return bool(cfg.get("enabled", True))


def get_debug_config() -> Dict[str, Any]:
    """Returns: APAPI debug config dict."""
    config = ensure_apapi_config_exists()
    apapi_cfg = config.get("apapi", {}) if isinstance(config, dict) else {}
    dbg_cfg = apapi_cfg.get("debug", {}) if isinstance(apapi_cfg, dict) else {}

    defaults = APAPI_DEFAULT_CONFIG["apapi"]["debug"]
    if isinstance(dbg_cfg, dict):
        effective = dict(defaults)
        effective.update(dbg_cfg)
        return effective
    if isinstance(dbg_cfg, bool):
        return {"enabled": bool(dbg_cfg)}
    # legacy flat keys
    if isinstance(apapi_cfg, dict):
        for _k in ("debug_messages", "enable_debug", "debug_enabled"):
            if _k in apapi_cfg:
                return {"enabled": bool(apapi_cfg[_k])}
    return dict(defaults)


def is_debug_enabled() -> bool:
    """Returns: True if APAPI debug messages are enabled (default True)."""
    cfg = get_debug_config()
    return bool(cfg.get("enabled", True))
