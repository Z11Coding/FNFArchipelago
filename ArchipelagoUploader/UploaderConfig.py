import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

def _get_host_yaml_path() -> Path:
    try:
        from Utils import user_path
        return Path(user_path("host.yaml"))
    except Exception:
        return Path("host.yaml")

def _load_host_yaml() -> Dict[str, Any]:
    config_path = _get_host_yaml_path()
    if not config_path.exists():
        return {}
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Failed to load host.yaml: {e}")
        return {}

def _ensure_uploader_config_exists() -> bool:
    config_path = _get_host_yaml_path()
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        if 'archipelago_uploader:' in content:
            return True
        uploader_section = """archipelago_uploader:
  enabled: true
  upload_mode: prompt
  upload_session_key: ""
  upload_domain: https://archipelago.gg
"""
        with open(config_path, 'a') as f:
            if not content.endswith('\n'):
                f.write('\n')
            f.write(uploader_section)
        return True
    except Exception as e:
        logger.error(f"[ArchipelagoUploader] Failed to ensure uploader config: {e}")
        return False

def load_uploader_config() -> Dict[str, Any]:
    defaults = {
        "enabled": True,
        "upload_domain": "https://archipelago.gg",
        "upload_session_key": "",
        "upload_mode": "prompt",
    }
    try:
        _ensure_uploader_config_exists()
        host_config = _load_host_yaml()
        uploader_config = host_config.get("archipelago_uploader", {})
        result = defaults.copy()
        if uploader_config:
            result.update(uploader_config)
        return result
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Failed to load uploader config: {e}")
        return defaults

def get_session_key() -> Optional[str]:
    config = load_uploader_config()
    key = config.get("upload_session_key", "").strip()
    return key if key else None

def get_upload_domain() -> str:
    config = load_uploader_config()
    return config.get("upload_domain", "https://archipelago.gg")

def is_enabled() -> bool:
    config = load_uploader_config()
    return config.get("enabled", True)

def get_upload_mode() -> str:
    config = load_uploader_config()
    mode = config.get("upload_mode", "prompt")
    valid_modes = ["prompt", "online", "online-room", "local", "none"]
    if mode not in valid_modes:
        logger.warning(f"[ArchipelagoUploader] Invalid upload_mode: {mode}, defaulting to prompt")
        return "prompt"
    return mode
