from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import logging

import yaml

from Utils import user_path


logger = logging.getLogger("APAPI")


APAPI_DEFAULT_CONFIG = {
    "apapi": {
        "universal_tracker_snapshot": {
            "enabled": True,
            "verbose_location_log": True,
        }
    }
}


def _get_host_yaml_path() -> Path:
    return Path(user_path("host.yaml"))


def _safe_load_yaml(path: Path) -> Dict[str, Any]:
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
    merged = dict(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_apapi_config_exists() -> Dict[str, Any]:
    """Ensure host.yaml contains APAPI config defaults and return loaded config."""
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

    return merged


def get_universal_tracker_snapshot_config() -> Dict[str, Any]:
    config = ensure_apapi_config_exists()
    apapi_cfg = config.get("apapi", {}) if isinstance(config, dict) else {}
    ut_cfg = apapi_cfg.get("universal_tracker_snapshot", {}) if isinstance(apapi_cfg, dict) else {}

    defaults = APAPI_DEFAULT_CONFIG["apapi"]["universal_tracker_snapshot"]
    effective = dict(defaults)
    if isinstance(ut_cfg, dict):
        effective.update(ut_cfg)
    return effective


def is_universal_tracker_snapshot_enabled() -> bool:
    cfg = get_universal_tracker_snapshot_config()
    return bool(cfg.get("enabled", True))
