from __future__ import annotations

"""Host config helpers for universal tracker snapshot settings."""

from pathlib import Path
from typing import Any, Dict
import logging

import yaml

from Utils import user_path


logger = logging.getLogger("APAPI")

class YAMLComment(str):
    """Represents a YAML comment."""
    def __new__(cls, content: str) -> YAMLComment:
        return str.__new__(cls, content)
    def __repr__(self) -> str:
        return f"YAMLComment({super().__repr__()})"
    def __str__(self) -> str:
        return f"# {super().__str__()}"


APAPI_DEFAULT_CONFIG = {
    "apapi": {
        "debug": {
            "enabled": False,
        },
        "universal_tracker_snapshot": {
            "enabled": True,
            "verbose_location_log": False,
        },
        "fill_analyzer": {
            "enabled": True,
            "max_unplaced_items": 8,
            "max_unfilled_locations": 12,
            "max_examples_per_item": 5,
            "include_spheres": True,
            "inspect_rules": True,
            "max_rule_details": 6,
        },
        "apworld_updater": {
            "auto_update_enabled": False,
            "ask_in_terminal": True,
            "accept_mode": "each",
            "index_url": "https://github.com/dowlle/Archipelago-index",
            "index_version": "latest",
            "install_missing_from_index": False,
        },
        "generation_retry": {
            "enabled": False,
        }
    }
}

_extra_host_defaults: Dict[str, Any] = {}


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


def _collect_missing_paths(base: Dict[str, Any], existing: Dict[str, Any], prefix: str = "") -> list[str]:
    missing: list[str] = []
    for k, v in base.items():
        cur = f"{prefix}.{k}" if prefix else k
        if k not in existing:
            missing.append(cur)
        elif isinstance(v, dict) and isinstance(existing.get(k), dict):
            missing.extend(_collect_missing_paths(v, existing[k], cur))
    return missing


def _get_nested(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _yaml_value_text(v: Any) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def _write_yaml_block(f: Any, d: Dict[str, Any], indent: str) -> None:
    for k, v in d.items():
        if isinstance(v, dict):
            f.write(f"{indent}{k}:\n")
            _write_yaml_block(f, v, indent + "  ")
        else:
            f.write(f"{indent}{k}: {_yaml_value_text(v)}\n")


def _yaml_block_lines(d: Dict[str, Any], indent: str) -> list[str]:
    lines: list[str] = []
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{indent}{k}:")
            lines.extend(_yaml_block_lines(v, indent + "    "))
        else:
            lines.append(f"{indent}{k}: {_yaml_value_text(v)}")
    return lines


def _indent_len(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _insert_leaf_into_section_block(lines: list[str], apapi_indent: str, section: str, leaf: str, value_text: str) -> bool:
    """Insert ``leaf: value`` into an existing ``section:`` mapping under ``apapi:``.

    Used for missing leaf paths like ``fill_analyzer.inspect_rules`` so they are
    nested properly instead of being written as flat ``fill_analyzer.inspect_rules:``
    keys (which YAML parses as a *different* key, causing duplicates on every run).
    Returns True when the key is present afterwards (inserted or already there).
    """
    section_indent = apapi_indent + "  "
    leaf_indent = section_indent + "  "
    # locate the apapi: block
    a_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == "apapi:" and _indent_len(line) == len(apapi_indent):
            a_idx = i
            break
    if a_idx is None:
        return False
    # locate the section header inside it
    s_idx: int | None = None
    j = a_idx + 1
    while j < len(lines):
        line = lines[j]
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _indent_len(line) <= len(apapi_indent):
            break  # left the apapi block
        if stripped == f"{section}:" and _indent_len(line) == len(section_indent):
            s_idx = j
            break
        j += 1
    if s_idx is None:
        # section itself is missing: append a new section block at the end of apapi
        end = a_idx + 1
        while end < len(lines):
            line = lines[end]
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and _indent_len(line) <= len(apapi_indent):
                break
            end += 1
        lines[end:end] = [f"{section_indent}{section}:", f"{leaf_indent}{leaf}: {value_text}"]
        return True
    # find end of the section block: first non-blank, non-comment line
    # dedented to section level or above
    end = s_idx + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _indent_len(line) <= len(section_indent):
            break
        end += 1
    # already present? (exact key match inside the block)
    for k in range(s_idx + 1, end):
        stripped = lines[k].strip()
        if stripped == f"{leaf}:" or stripped.startswith(f"{leaf}:"):
            return True
    lines[end:end] = [f"{leaf_indent}{leaf}: {value_text}"]
    return True


def _patch_yaml_dotted_path(file_path: Path, dotted_path: str, new_value: Any) -> bool:
    """Update dotted_path in file_path to new_value (dict or scalar), preserving surrounding comments."""
    try:
        text = file_path.read_text(encoding="utf-8")
        parts = dotted_path.split(".")
        top = parts[0]
        # scalar case: top-only or leaf scalar
        if len(parts) == 1:
            if isinstance(new_value, dict):
                block = [f"{top}:"] + _yaml_block_lines(new_value, "  ")
            else:
                block = [f"{top}: {_yaml_value_text(new_value)}"]
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.strip() == f"{top}:" or line.strip().startswith(f"{top}:"):
                    # find end of block (next top-level key or EOF)
                    j = i + 1
                    while j < len(lines) and (not lines[j].strip() or lines[j].startswith("  ") or lines[j].strip().startswith("#")):
                        # stop at next top-level non-indented non-empty non-comment
                        if lines[j] and not lines[j].startswith(" ") and not lines[j].startswith("\t") and lines[j].strip() and not lines[j].strip().startswith("#"):
                            break
                        j += 1
                    new_text = "\n".join(lines[:i] + block + lines[j:]) + ("\n" if text.endswith("\n") else "\n")
                    file_path.write_text(new_text, encoding="utf-8")
                    return True
            # not found -> append
            with file_path.open("a", encoding="utf-8") as f:
                if text and not text.endswith("\n"):
                    f.write("\n")
                for l in block:
                    f.write(l + "\n")
            return True
        # dotted nested e.g. my_world.enabled or apapi.debug.enabled
        # handle by loading dict, patching, then trying preserve; simplest: use text patch for first level
        # fallback to yaml safe dump merge if text patch fails
        loaded = _safe_load_yaml(file_path)
        cur: Dict[str, Any] = loaded
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = new_value if not isinstance(new_value, dict) else dict(new_value)
        # try text patch for leaf dict: rewrite the specific subsection if top-level dict
        # if leaf is under top-level dict, we can rebuild top block
        if len(parts) == 2 and isinstance(loaded.get(top), dict):
            top_dict = loaded[top]
            # rebuild top block text
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.strip() == f"{top}:":
                    top_indent = line[: len(line) - len(line.lstrip())]
                    j = i + 1
                    while j < len(lines):
                        if lines[j] and not lines[j].startswith(top_indent + " ") and lines[j].strip() and not lines[j].strip().startswith("#"):
                            break
                        j += 1
                    block = [f"{top_indent}{top}:"] + _yaml_block_lines(top_dict, top_indent + "  ")
                    new_text = "\n".join(lines[:i] + block + lines[j:]) + ("\n" if text.endswith("\n") else "\n")
                    file_path.write_text(new_text, encoding="utf-8")
                    return True
        # fallback: safe dump (loses comments but guarantees correctness)
        with file_path.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(loaded, stream, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        return False


def _try_preserve_merge(path: Path, existing: Dict[str, Any], merged: Dict[str, Any]) -> bool:
    try:
        full_base: Dict[str, Any] = _deep_merge(APAPI_DEFAULT_CONFIG, _extra_host_defaults)
        missing_paths = _collect_missing_paths(full_base, existing)
        if not missing_paths:
            return False
        text = path.read_text(encoding="utf-8")
        top_missing = [p for p in missing_paths if "." not in p]
        apapi_missing = [p.split(".", 1)[1] for p in missing_paths if p.startswith("apapi.")]
        if top_missing:
            with path.open("a", encoding="utf-8") as f:
                if text and not text.endswith("\n"):
                    f.write("\n")
                for key in top_missing:
                    val = _get_nested(full_base, key)
                    if isinstance(val, dict):
                        f.write(f"{key}:\n")
                        _write_yaml_block(f, val, "  ")
                    else:
                        f.write(f"{key}: {_yaml_value_text(val)}\n")
            text = path.read_text(encoding="utf-8")
        if apapi_missing:
            if "apapi:" not in text:
                with path.open("a", encoding="utf-8") as f:
                    if text and not text.endswith("\n"):
                        f.write("\n")
                    f.write("apapi:\n")
                    for key in apapi_missing:
                        val = _get_nested(full_base, f"apapi.{key}")
                        if isinstance(val, dict):
                            f.write(f"  {key}:\n")
                            _write_yaml_block(f, val, "    ")
                        else:
                            f.write(f"  {key}: {_yaml_value_text(val)}\n")
                return True
            lines = text.splitlines()
            # Deep leaf paths (e.g. fill_analyzer.inspect_rules) must be nested
            # inside their section block — never written as flat dotted keys.
            _apapi_indent = ""
            for _ln in lines:
                if _ln.strip() == "apapi:":
                    _apapi_indent = _ln[:len(_ln) - len(_ln.lstrip())]
                    break
            _remaining = list(apapi_missing)
            for key in list(apapi_missing):
                if key.count(".") != 1:
                    continue
                section, leaf = key.split(".", 1)
                val = _get_nested(full_base, f"apapi.{key}")
                if isinstance(val, dict):
                    continue
                if _insert_leaf_into_section_block(lines, _apapi_indent, section, leaf, _yaml_value_text(val)):
                    _remaining.remove(key)
            apapi_missing = _remaining
            if not apapi_missing:
                path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else "\n"), encoding="utf-8")
                return True
            out: list[str] = []
            inserted: set[str] = set()
            in_apapi = False
            apapi_indent = ""
            for line in lines:
                stripped = line.strip()
                if stripped == "apapi:":
                    in_apapi = True
                    apapi_indent = line[:len(line) - len(line.lstrip())]
                    out.append(line)
                    continue
                if in_apapi:
                    if line and not line.startswith(apapi_indent + "  ") and stripped and not stripped.startswith("#"):
                        for key in apapi_missing:
                            if key not in inserted:
                                val = _get_nested(full_base, f"apapi.{key}")
                                if isinstance(val, dict):
                                    out.append(f"{apapi_indent}  {key}:")
                                    out.extend(_yaml_block_lines(val, apapi_indent + "    "))
                                else:
                                    out.append(f"{apapi_indent}  {key}: {_yaml_value_text(val)}")
                                inserted.add(key)
                        in_apapi = False
                out.append(line)
            if in_apapi:
                for key in apapi_missing:
                    if key not in inserted:
                        val = _get_nested(full_base, f"apapi.{key}")
                        if isinstance(val, dict):
                            out.append(f"{apapi_indent}  {key}:")
                            out.extend(_yaml_block_lines(val, apapi_indent + "    "))
                        else:
                            out.append(f"{apapi_indent}  {key}: {_yaml_value_text(val)}")
                        inserted.add(key)
            if len(inserted) == len(apapi_missing):
                path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else "\n"), encoding="utf-8")
                return True
            return False
        return True
    except Exception:
        return False


def _dataclass_type_to_dict(cls: Any) -> Dict[str, Any]:
    import dataclasses
    out: Dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore
            try:
                out[f.name] = f.default_factory()  # type: ignore
            except Exception:
                out[f.name] = None
        else:
            out[f.name] = None
    return out


def _plain_class_to_dict(obj: Any, cls: Any | None = None) -> Dict[str, Any] | None:
    target = cls if cls is not None else obj
    cls_for_ann = target if isinstance(target, type) else type(target)
    ann = getattr(cls_for_ann, "__annotations__", None)
    if isinstance(ann, dict) and ann:
        out: Dict[str, Any] = {}
        has_any = False
        for k in ann:
            if k.startswith("_"):
                continue
            has_any = True
            if isinstance(target, type):
                out[k] = getattr(target, k, None)
            else:
                out[k] = getattr(target, k, getattr(cls_for_ann, k, None))
        if has_any:
            # merge instance overrides if type case missed instance values? keep as-is
            return out
    if not isinstance(target, type) and hasattr(obj, "__dict__"):
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict):
            filtered = {k: v for k, v in d.items() if not k.startswith("_")}
            if filtered:
                return filtered
    return None


def _coerce_default(v: Any) -> Any:
    if isinstance(v, dict):
        return v
    try:
        import dataclasses
        if isinstance(v, type) and dataclasses.is_dataclass(v):
            return _dataclass_type_to_dict(v)
        if dataclasses.is_dataclass(v):
            try:
                return dataclasses.asdict(v)
            except Exception:
                pass
    except Exception:
        pass
    # plain dataclass-like instance without decorator (has __dataclass_fields__)
    try:
        fields = getattr(v, "__dataclass_fields__", None)
        if isinstance(fields, dict) and fields:
            return {k: getattr(v, k, None) for k in fields}
    except Exception:
        pass
    # plain class type with annotations -> dict
    try:
        d = _plain_class_to_dict(v)
        if d is not None:
            return d
    except Exception:
        pass
    # Group compat (still supported but not required)
    try:
        from settings import Group
        if isinstance(v, type) and issubclass(v, Group):
            v = v()
        if isinstance(v, Group):
            return v.as_dict()
    except Exception:
        pass
    # plain object instance
    try:
        if not isinstance(v, dict) and hasattr(v, "__dict__"):
            d = getattr(v, "__dict__", None)
            if isinstance(d, dict):
                filtered = {k: vv for k, vv in d.items() if not k.startswith("_")}
                if filtered:
                    return filtered
    except Exception:
        pass
    return v


def host_config(path: str):
    """Annotation/decorator for plain objects.

    Usage (no Group needed):
        import dataclasses
        from worlds.APAPI.host_config import host_config

        @host_config("my_world")
        @dataclasses.dataclass
        class MyHostConfig:
            enabled: bool = False
            count: int = 10

        # or plain class:
        @host_config("my_world")
        class MyHostConfig:
            enabled: bool = False

        # or dict/object directly:
        # register_host_config("my_world", {"enabled": False})

    The decorator just calls register_host_config(path, cls) and keeps Group optional.
    """
    def decorator(cls: Any) -> Any:
        # allow annotation to also work via class attribute __host_config_path__
        try:
            setattr(cls, "__apapi_host_config_path__", path)
        except Exception:
            pass
        register_host_config(path, cls)
        return cls
    return decorator


def register_host_config(path: str, default: Any) -> None:
    default = _coerce_default(default)
    parts = path.split(".")
    cur: Dict[str, Any] = _extra_host_defaults
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = default


def get_host_config(path: str, default: Any = None) -> Any:
    cfg = ensure_apapi_config_exists()
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def get_host_config_object(path: str, cls: Any, default: Any | None = None) -> Any:
    """Typed getter: hydrates a dataclass/plain class from host.yaml.

    Returns: instance of cls if path exists, else default (or fresh cls()).
    Works with dict-hosted data: merges stored dict over dataclass/plain defaults.
    """
    data = get_host_config(path, None)
    if data is None:
        return default if default is not None else None
    if not isinstance(data, dict):
        return data
    try:
        import dataclasses
        if dataclasses.is_dataclass(cls):
            base: Dict[str, Any] = {}
            try:
                base = _dataclass_type_to_dict(cls)
            except Exception:
                pass
            merged = dict(base)
            merged.update(data)
            try:
                return cls(**{k: v for k, v in merged.items() if k in {f.name for f in dataclasses.fields(cls)}})
            except Exception:
                return merged
    except Exception:
        pass
    try:
        if isinstance(cls, type):
            out = cls()
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                try:
                    setattr(out, k, v)
                except Exception:
                    pass
            return out
    except Exception:
        pass
    return data


def ensure_host_config(path: str, default: Any) -> Any:
    """One-call: load if exists else create with defaults (and persist).

    Registers default (dataclass/dict/plain object/Group), ensures host.yaml
    contains it (creates missing keys, preserves comments), returns current
    merged value. Use for worlds that just want a dict/object without boilerplate.

    Examples:
        cfg = ensure_host_config("my_world", {"enabled": False, "count": 10})
        cfg = ensure_host_config("my_world", MyDataclass)
        cfg = ensure_host_config("my_world", MyDataclass(enabled=True))
    """
    register_host_config(path, default)
    # ensure file now contains defaults if missing
    ensure_apapi_config_exists()
    return get_host_config(path)


def ensure_host_config_object(path: str, cls: Any) -> Any:
    """One-call typed: load if exists else create, return hydrated object.

    Shorthand for register + hydrate. `cls` may be dataclass type, plain class
    with annotations, or dict-like. Persists defaults if path missing.
    """
    register_host_config(path, cls)
    ensure_apapi_config_exists()
    return get_host_config_object(path, cls)


class HostConfig:
    """Base for custom host.yaml sections — no Group/dataclass required.

    One-all class: subclass + call .load() to register defaults, create the
    section if missing, and get a hydrated object back.

    Examples:
        import dataclasses
        from worlds.APAPI.host_config import HostConfig

        @dataclasses.dataclass
        class MyWorldConfig(HostConfig):
            path = "my_world"   # required; also accepts __host_config_path__
            enabled: bool = False
            count: int = 10

        cfg = MyWorldConfig.load()  # -> MyWorldConfig(enabled=False, count=10)
        # plain class (no dataclass) also works:
        class MyOther(HostConfig):
            path = "my_other"
            enabled: bool = True

        # dict-style:
        class MyDict(HostConfig):
            path = "my_dict"
            defaults = {"enabled": False}
    """

    path: str = ""
    __host_config_path__: str = ""
    defaults: Dict[str, Any] | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # no auto-register; .load() does it explicitly so import has no side-effects

    @classmethod
    def _resolve_path(cls) -> str:
        for attr in ("path", "__host_config_path__", "_path", "host_path"):
            v = getattr(cls, attr, "")
            if isinstance(v, str) and v:
                return v
        raise ValueError(f"{cls.__name__}.path not set (e.g. path = 'my_world')")

    @classmethod
    def _default_payload(cls) -> Any:
        if getattr(cls, "defaults", None) is not None:
            return getattr(cls, "defaults")
        # dataclass subclass -> use its own type as default source
        try:
            import dataclasses
            if dataclasses.is_dataclass(cls):
                return cls
        except Exception:
            pass
        # plain annotated class -> use class itself (coerced via _plain_class_to_dict)
        return cls

    @classmethod
    def load(cls) -> Any:
        """Load if exists else create with defaults. Returns hydrated instance."""
        path = cls._resolve_path()
        payload = cls._default_payload()
        register_host_config(path, payload)
        ensure_apapi_config_exists()
        return get_host_config_object(path, cls)

    @classmethod
    def get(cls) -> Any:
        """Alias for load()."""
        return cls.load()

    def save(self) -> None:
        """Persist current instance fields back to host.yaml (preserves comments where possible)."""
        cls = type(self)
        dotted = cls._resolve_path()
        payload = _coerce_default(self)
        # keep in-memory defaults in sync
        try:
            register_host_config(dotted, payload)
        except Exception:
            pass
        file_path = _get_host_yaml_path()
        # ensure file exists first
        ensure_apapi_config_exists()
        # try to patch file directly so existing values are overwritten
        if isinstance(payload, dict):
            _patch_yaml_dotted_path(file_path, dotted, payload)
        else:
            _patch_yaml_dotted_path(file_path, dotted, payload)


def ensure_apapi_config_exists() -> Dict[str, Any]:
    """Returns: merged host.yaml config (ensures defaults exist)."""
    config_path = _get_host_yaml_path()
    existing = _safe_load_yaml(config_path)
    base = _deep_merge(APAPI_DEFAULT_CONFIG, _extra_host_defaults)
    merged = _deep_merge(base, existing)

    if merged != existing:
        try:
            if config_path.exists():
                if _try_preserve_merge(config_path, existing, merged):
                    logger.info("APAPI added missing keys to %s (preserved comments)", config_path)
                else:
                    logger.info("APAPI keeping %s unchanged to preserve comments (missing keys available in memory)", config_path)
            else:
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


def get_apworld_updater_config() -> Dict[str, Any]:
    config = ensure_apapi_config_exists()
    apapi_cfg = config.get("apapi", {}) if isinstance(config, dict) else {}
    upd_cfg = apapi_cfg.get("apworld_updater", {}) if isinstance(apapi_cfg, dict) else {}
    defaults = APAPI_DEFAULT_CONFIG["apapi"]["apworld_updater"]
    effective = dict(defaults)
    if isinstance(upd_cfg, dict):
        effective.update(upd_cfg)
    return effective


def is_apworld_auto_update_enabled() -> bool:
    cfg = get_apworld_updater_config()
    return bool(cfg.get("auto_update_enabled", False))


def get_generation_retry_config() -> Dict[str, Any]:
    config = ensure_apapi_config_exists()
    apapi_cfg = config.get("apapi", {}) if isinstance(config, dict) else {}
    retry_cfg = apapi_cfg.get("generation_retry", {}) if isinstance(apapi_cfg, dict) else {}
    defaults = APAPI_DEFAULT_CONFIG["apapi"]["generation_retry"]
    effective = dict(defaults)
    if isinstance(retry_cfg, dict):
        effective.update(retry_cfg)
    elif isinstance(retry_cfg, bool):
        effective["enabled"] = bool(retry_cfg)
    return effective


def is_generation_retry_enabled() -> bool:
    cfg = get_generation_retry_config()
    return bool(cfg.get("enabled", False))
