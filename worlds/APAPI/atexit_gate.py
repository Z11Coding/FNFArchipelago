from __future__ import annotations

import atexit
import logging
import sys
import traceback
from typing import Any

logger = logging.getLogger("APAPI.AtexitGate")

_MAX_RETRIES: int = 1
_RETRY_COUNT: int = 0
_LAST_ERROR: BaseException | None = None
_LAST_TRACE: str | None = None
_LAST_ERARGS: Any | None = None
_LAST_SEED: Any | None = None
_LAST_BAKED: Any | None = None
_SUCCESS: bool = False
_IN_HANDLER: bool = False
_INSTALLED: bool = False
_ORIG_EXCEPTHOOK = None  # type: ignore
_PATCHED_ATEXIT = False
_ORIG_ATEXIT_REGISTER = None  # type: ignore


def _is_generate_context() -> bool:
    try:
        from .launch_context import is_generate_context
        return bool(is_generate_context())
    except Exception:
        return False


def _is_fill_error(exc: BaseException) -> bool:
    """True when exc is a Fill.FillError (checked lazily to avoid import cycles)."""
    try:
        if type(exc).__name__ == "FillError":
            return True
        from Fill import FillError as _FE
        return isinstance(exc, _FE)
    except Exception:
        return type(exc).__name__ == "FillError"


def _fill_replacement_text(exc: BaseException) -> str:
    """Enriched display text for a FillError. Never raises ('' on failure).

    Reuses the ``apapi_fill_diagnosis`` attached by the fill-analyzer hooks
    at raise time (the live MultiWorld may be gone by atexit), falling back
    to a fresh analysis against whatever the current multiworld still is.
    """
    try:
        pre = getattr(exc, "apapi_fill_diagnosis", None)
        if isinstance(pre, str) and pre.strip():
            return pre
    except Exception:
        pass
    try:
        from .fill_analyzer import diagnose_and_format, attach_diagnosis_to_exception, is_enabled
        if not is_enabled():
            return ""
        mw = None
        try:
            from .multiworld_api import get_current_multiworld
            mw = get_current_multiworld()
        except Exception:
            mw = None
        text = diagnose_and_format(mw, exc)
        try:
            attach_diagnosis_to_exception(exc, text)
        except Exception:
            pass
        return text
    except Exception:
        return ""


def _print_enriched_fill_error(exc: BaseException, text: str) -> None:
    """Print the enriched fill report *instead of* the raw FillError traceback."""
    try:
        import colorama
        try:
            colorama.just_fix_windows_console()
        except Exception:
            pass
        WHITE = getattr(colorama.Fore, "WHITE", "\033[97m")
        RED = getattr(colorama.Fore, "RED", "\033[91m")
        BRIGHT = getattr(colorama.Style, "BRIGHT", "\033[1m")
        RESET = getattr(colorama.Style, "RESET_ALL", "\033[0m")
    except Exception:
        WHITE = "\033[97m"
        RED = "\033[91m"
        BRIGHT = "\033[1m"
        RESET = "\033[0m"
    try:
        out: list[str] = []
        out.append(RED + BRIGHT + "=" * 78 + RESET + "\n")
        out.append(RED + BRIGHT + "[APAPI FILL ERROR] what was technically wrong" + RESET + "\n")
        out.append(RED + BRIGHT + "=" * 78 + RESET + "\n")
        for line in text.splitlines():
            out.append(WHITE + line + RESET + "\n")
        out.append(RED + BRIGHT + "=" * 78 + RESET + "\n")
        try:
            orig = f"{type(exc).__name__}: {exc}".strip()
            if orig:
                out.append(WHITE + f"(original: {orig[:300]})" + RESET + "\n")
        except Exception:
            pass
        sys.stderr.write("".join(out))
        sys.stderr.write(RESET)
        sys.stderr.flush()
    except Exception:
        try:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:
            pass


def _print_colored_exc(exc: BaseException | None) -> None:
    if exc is None:
        return
    # FillErrors get replaced by the enriched analyzer report instead of
    # the raw traceback (see _fill_replacement_text).
    try:
        if _is_fill_error(exc):
            assert exc is not None
            text = _fill_replacement_text(exc)
            if text:
                _print_enriched_fill_error(exc, text)
                return
    except Exception:
        pass
    try:
        import colorama
        try:
            colorama.just_fix_windows_console()
        except Exception:
            pass
        WHITE = getattr(colorama.Fore, "WHITE", "\033[97m")
        PURPLE = getattr(colorama.Fore, "MAGENTA", "\033[95m")
        RED = getattr(colorama.Fore, "RED", "\033[91m")
        YELLOW = getattr(colorama.Fore, "YELLOW", "\033[93m")
        BRIGHT = getattr(colorama.Style, "BRIGHT", "\033[1m")
        RESET = getattr(colorama.Style, "RESET_ALL", "\033[0m")
        DIM = getattr(colorama.Style, "DIM", "\033[2m")
    except Exception:
        WHITE = "\033[97m"
        PURPLE = "\033[95m"
        RED = "\033[91m"
        YELLOW = "\033[93m"
        BRIGHT = "\033[1m"
        RESET = "\033[0m"
        DIM = "\033[2m"
    try:
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    except Exception:
        tb_str = f"{exc}\n"
    try:
        exc_name = type(exc).__name__ if exc is not None else ""
        lines = tb_str.splitlines(keepends=True)
        out_parts: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            is_file_line = 'File "' in line or stripped.startswith('File "') or stripped.startswith("File")
            is_traceback_header = line.startswith("Traceback") or line.startswith("During handling") or line.startswith("The above") or line.startswith("Exception Group")
            is_indented_code = line.startswith(" ") or line.startswith("\t") or stripped.startswith("^")
            is_error_line = False
            if not is_traceback_header and not is_file_line and not is_indented_code:
                if line.strip():
                    if exc_name and exc_name in line:
                        is_error_line = True
                    elif ":" in line and not line.startswith(" "):
                        first_colon = line.find(":")
                        prefix = line[:first_colon].strip().split()[-1] if line[:first_colon].strip() else ""
                        if "Error" in prefix or "Exception" in prefix or "Failed" in prefix or prefix == exc_name:
                            is_error_line = True
                        elif line.strip().startswith("[") and "game=" in line:
                            is_error_line = False
                        elif stripped.startswith("APAPI assertions"):
                            is_error_line = False
            if is_traceback_header:
                out_parts.append(WHITE + line + RESET)
            elif is_file_line:
                out_parts.append(PURPLE + line + RESET)
            elif is_error_line:
                out_parts.append(RED + BRIGHT + line + RESET)
            elif is_indented_code:
                if stripped and all(c in " ~^*-_|" for c in stripped) and ("^" in stripped or "~" in stripped):
                    out_parts.append(YELLOW + BRIGHT + line + RESET)
                elif stripped.startswith("^") or "~" in stripped and stripped.strip().startswith("~"):
                    out_parts.append(YELLOW + BRIGHT + line + RESET)
                else:
                    out_parts.append(WHITE + line + RESET)
            else:
                if stripped.startswith("[") or stripped.startswith("Games errored") or stripped.startswith("APAPI"):
                    out_parts.append(WHITE + line + RESET)
                elif "traceback:" in line.lower():
                    out_parts.append(WHITE + line + RESET)
                elif not line.strip():
                    out_parts.append(line)
                else:
                    out_parts.append(WHITE + line + RESET)
        colored = "".join(out_parts)
        sys.stderr.write(colored)
        if not colored.endswith("\n"):
            sys.stderr.write("\n")
        sys.stderr.write(RESET)
        sys.stderr.flush()
    except Exception:
        try:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:
            pass


def _ensure_atexit_last() -> None:
    try:
        try:
            atexit.unregister(_atexit_handler)  # type: ignore[attr-defined]
        except Exception:
            pass
        atexit.register(_atexit_handler)
    except Exception:
        pass


def _wait_gate_sync(timeout: float = 8.0) -> bool:
    try:
        from .generation_gate import wait_for_all_patches
        return bool(wait_for_all_patches(timeout=timeout))
    except Exception:
        return False


def _all_patches_settled() -> bool:
    try:
        from .generation_gate import _snapshot_pending
        return not _snapshot_pending()
    except Exception:
        return False


def _reapply_global_injections() -> None:
    try:
        from worlds.AutoWorld import AutoWorldRegister
        from .injection import _apply_to_world
        for game, wt in list(AutoWorldRegister.world_types.items()):
            try:
                _apply_to_world(game, wt)
            except Exception:
                pass
    except Exception:
        pass
    try:
        from Options import PerGameCommonOptions
        from worlds.AutoWorld import AutoWorldRegister
        per_ann = getattr(PerGameCommonOptions, "__annotations__", {}) or {}
        if not per_ann:
            return
        import dataclasses
        for game, wt in list(AutoWorldRegister.world_types.items()):
            try:
                dc = wt.options_dataclass
                ann = getattr(dc, "__annotations__", None)
                if ann is None:
                    continue
                missing = {k: v for k, v in per_ann.items() if k not in ann}
                if not missing:
                    continue
                for k, v in missing.items():
                    ann[k] = v
                saved: dict[str, Any] = {}
                for attr in ("__init__", "__repr__", "__eq__"):
                    if attr in dc.__dict__:
                        saved[attr] = dc.__dict__[attr]
                        try:
                            delattr(dc, attr)
                        except Exception:
                            saved.pop(attr, None)
                try:
                    dataclasses.dataclass(dc)
                except Exception:
                    for a, orig in saved.items():
                        try:
                            setattr(dc, a, orig)
                        except Exception:
                            pass
                    continue
                try:
                    from .injection import _clear_type_hint_cache
                    _clear_type_hint_cache()
                except Exception:
                    pass
            except Exception:
                continue
    except Exception:
        pass


def _ensure_yaml_versions() -> None:
    try:
        from .yaml_tools import resolve_player_files_dir, iter_player_yaml_files, read_yaml_documents_file
        from worlds.AutoWorld import AutoWorldRegister
        from .updater import download_apworld_for_spec, get_temp_apworld_dir
        import pathlib, worlds, bisect
        pdir = resolve_player_files_dir()
        if not pdir or not pdir.is_dir():
            return
        for yf in iter_player_yaml_files(pdir):
            try:
                docs = read_yaml_documents_file(yf)
                for doc in docs:
                    if not isinstance(doc, dict):
                        continue
                    game = str(doc.get("game", "")).strip()
                    spec = None
                    if "apworld_version_wanted" in doc:
                        spec = str(doc["apworld_version_wanted"]).strip()
                    elif game and isinstance(doc.get(game), dict) and "apworld_version_wanted" in doc[game]:
                        spec = str(doc[game]["apworld_version_wanted"]).strip()
                    if not game or not spec:
                        continue
                    if game in AutoWorldRegister.world_types:
                        continue
                    dest = download_apworld_for_spec(game, spec, get_temp_apworld_dir() / f"retry_{game.replace(' ', '_')}")
                    if dest and dest.is_file() and not any(pathlib.Path(s.resolved_path) == dest for s in worlds.world_sources):
                        src = worlds.WorldSource(str(dest), is_zip=True, relative=False)
                        bisect.insort(worlds.world_sources, src)
                        src.load()
            except Exception:
                continue
    except Exception:
        pass


def remove_atexit_gate() -> bool:
    global _INSTALLED
    try:
        try:
            atexit.unregister(_atexit_handler)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if _PATCHED_ATEXIT and _ORIG_ATEXIT_REGISTER is not None:
                atexit.register = _ORIG_ATEXIT_REGISTER  # type: ignore
        except Exception:
            pass
        if _INSTALLED:
            logger.info("[APAPI:atexit] gate removed — patches settled")
        _INSTALLED = False
        return True
    except Exception:
        return False


def _main_wrapper(next_callable, *args: Any, **kwargs: Any) -> Any:
    global _LAST_ERARGS, _LAST_SEED, _LAST_BAKED, _LAST_ERROR, _LAST_TRACE, _SUCCESS
    try:
        if args:
            if len(args) >= 1:
                _LAST_ERARGS = args[0]
            if len(args) >= 2:
                _LAST_SEED = args[1]
            if len(args) >= 3:
                _LAST_BAKED = args[2]
        else:
            if "args" in kwargs:
                _LAST_ERARGS = kwargs["args"]
            if "seed" in kwargs:
                _LAST_SEED = kwargs["seed"]
            if "baked_server_options" in kwargs:
                _LAST_BAKED = kwargs["baked_server_options"]
    except Exception:
        pass
    try:
        if _is_generate_context():
            _ensure_atexit_last()
    except Exception:
        pass
    try:
        result = next_callable(*args, **kwargs)
        _SUCCESS = True
        _LAST_ERROR = None
        _LAST_TRACE = None
        return result
    except BaseException as exc:  # noqa: BLE001
        _LAST_ERROR = exc
        _LAST_TRACE = traceback.format_exc()
        _SUCCESS = False
        logger.warning("[APAPI:atexit] Main.main failed: %s", exc, exc_info=True)
        raise


def _generate_wrapper(next_callable, *args: Any, **kwargs: Any) -> Any:
    global _LAST_ERARGS, _LAST_SEED, _LAST_ERROR, _LAST_TRACE, _SUCCESS
    try:
        if _is_generate_context():
            _ensure_atexit_last()
    except Exception:
        pass
    try:
        result = next_callable(*args, **kwargs)
        try:
            if isinstance(result, tuple) and len(result) == 2:
                _LAST_ERARGS, _LAST_SEED = result
        except Exception:
            pass
        if _LAST_ERROR is not None and "Generate" in str(type(_LAST_ERROR)):
            _LAST_ERROR = None
            _LAST_TRACE = None
        return result
    except BaseException as exc:  # noqa: BLE001
        _LAST_ERROR = exc
        _LAST_TRACE = traceback.format_exc()
        _SUCCESS = False
        logger.warning("[APAPI:atexit] Generate.main failed: %s", exc, exc_info=True)
        raise


def _roll_settings_wrapper(next_callable, yaml, *args, **kwargs):
    try:
        return next_callable(yaml, *args, **kwargs)
    except Exception as exc:
        msg = str(exc)
        if "No world found" not in msg and "No functional world" not in msg:
            raise
        game = yaml.get("game") if isinstance(yaml, dict) else None
        # The game may have failed its first import only because an apworld it
        # depends on (e.g. APAPI) had not loaded yet: apworlds load in world
        # version order, so dependents can come first. Reload failed worlds
        # synchronously and re-roll once, so the yaml does not fail for
        # load-order reasons alone. Worlds still fail fast on real errors
        # (no tolerant imports), and this never needs generation_retry.
        try:
            from .world_ready import _try_reload_failed_worlds
            _try_reload_failed_worlds()
        except Exception:
            pass
        try:
            if game:
                from worlds.AutoWorld import AutoWorldRegister
                if str(game) in AutoWorldRegister.world_types:
                    return next_callable(yaml, *args, **kwargs)
        except Exception:
            pass
        try:
            spec = None
            if isinstance(yaml, dict):
                if "apworld_version_wanted" in yaml:
                    spec = str(yaml["apworld_version_wanted"]).strip()
                elif isinstance(yaml.get(str(game), {}), dict) and "apworld_version_wanted" in yaml[str(game)]:
                    spec = str(yaml[str(game)]["apworld_version_wanted"]).strip()
            if game and spec:
                from worlds.AutoWorld import AutoWorldRegister
                if str(game) not in AutoWorldRegister.world_types:
                    from worlds.APAPI.updater import download_apworld_for_spec, get_temp_apworld_dir
                    import pathlib, worlds, bisect
                    dest = download_apworld_for_spec(str(game), spec, get_temp_apworld_dir() / f"roll_{str(game).replace(' ', '_')}")
                    if dest and dest.is_file() and not any(pathlib.Path(s.resolved_path) == dest for s in worlds.world_sources):
                        src = worlds.WorldSource(str(dest), is_zip=True, relative=False)
                        bisect.insort(worlds.world_sources, src)
                        if src.load():
                            return next_callable(yaml, *args, **kwargs)
        except Exception:
            pass
        raise


def _install_wrappers() -> None:
    try:
        from .hard_patch import hard_patches
    except Exception:
        return
    try:
        hard_patches.add_wrapper("Main.main", _main_wrapper, load_missing=True)
    except Exception:
        pass
    try:
        hard_patches.add_wrapper("Generate.main", _generate_wrapper, load_missing=True)
    except Exception:
        pass
    try:
        hard_patches.add_wrapper("Generate.roll_settings", _roll_settings_wrapper, load_missing=True)
    except Exception:
        pass


def _install_excepthook() -> None:
    global _ORIG_EXCEPTHOOK
    if _ORIG_EXCEPTHOOK is not None:
        return
    _ORIG_EXCEPTHOOK = sys.excepthook

    def _apapi_excepthook(exc_type, exc_value, exc_tb) -> None:  # type: ignore
        global _LAST_ERROR, _LAST_TRACE, _SUCCESS
        try:
            if _is_generate_context():
                _LAST_ERROR = exc_value
                _LAST_TRACE = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
                _SUCCESS = False
        except Exception:
            pass
        try:
            if _ORIG_EXCEPTHOOK is not None:
                return _ORIG_EXCEPTHOOK(exc_type, exc_value, exc_tb)
        except Exception:
            pass
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _apapi_excepthook  # type: ignore


def _atexit_handler() -> None:
    global _RETRY_COUNT, _IN_HANDLER, _SUCCESS, _LAST_ERROR, _LAST_TRACE, _LAST_ERARGS, _LAST_SEED, _LAST_BAKED
    if _IN_HANDLER:
        return
    if not _is_generate_context():
        return
    try:
        from .generation_gate import wait_for_all_patches, _snapshot_pending
        try:
            pending = _snapshot_pending()
        except Exception:
            pending = []
        if pending:
            logger.info("[APAPI:atexit] waiting for patches: %s", "; ".join(pending))
        settled = wait_for_all_patches(timeout=12.0)
        if not settled:
            logger.warning("[APAPI:atexit] patch gate timed out")
    except Exception:
        pass
    # If failure is an APAPI assertion aggregate, don't retry — it's a deferred logical error, not transient
    try:
        from .assertions import APAPIAssertionAggregateError, get_failure_count, format_report  # type: ignore

        if isinstance(_LAST_ERROR, APAPIAssertionAggregateError):
            logger.error("[APAPI:atexit] APAPI assertion failures detected — not retrying")
            _print_colored_exc(_LAST_ERROR)
            return
        # also check if there are pending assertion failures even if last error was generic
        if get_failure_count() > 0:
            try:
                from .assertions import check_and_raise

                check_and_raise(stage="atexit_gate")
            except APAPIAssertionAggregateError as agg:
                _LAST_ERROR = agg
                _LAST_TRACE = traceback.format_exc()
                _print_colored_exc(agg)
                return
            except Exception:
                pass
    except Exception:
        pass
    if _SUCCESS or _LAST_ERROR is None:
        try:
            if _all_patches_settled():
                remove_atexit_gate()
        except Exception:
            pass
        return
    if _RETRY_COUNT >= _MAX_RETRIES:
        logger.warning("[APAPI:atexit] max retries (%d) reached", _MAX_RETRIES)
        _print_colored_exc(_LAST_ERROR)
        return
    try:
        from .host_config import is_generation_retry_enabled
        if not is_generation_retry_enabled():
            logger.info("[APAPI:atexit] generation_retry disabled in host.yaml — not retrying")
            _print_colored_exc(_LAST_ERROR)
            return
    except Exception:
        pass
    _IN_HANDLER = True
    try:
        while not _SUCCESS and _LAST_ERROR is not None and _RETRY_COUNT < _MAX_RETRIES:
            _RETRY_COUNT += 1
            logger.info("[APAPI:atexit] generation failed (%s), retrying (%d/%d)", _LAST_ERROR, _RETRY_COUNT, _MAX_RETRIES)
            try:
                from .generation_gate import wait_for_all_patches
                wait_for_all_patches(timeout=10.0)
            except Exception:
                pass
            try:
                from .world_ready import _try_reload_failed_worlds
                _try_reload_failed_worlds()
            except Exception:
                pass
            _ensure_yaml_versions()
            _reapply_global_injections()
            # Before retry, check if assertions would still fail — if so, don't retry generic logic, surface assertions
            try:
                from .assertions import APAPIAssertionAggregateError, check_and_raise, get_failure_count

                if get_failure_count() > 0:
                    try:
                        check_and_raise(stage=f"atexit_retry_{_RETRY_COUNT}")
                    except APAPIAssertionAggregateError as agg:
                        _LAST_ERROR = agg
                        _LAST_TRACE = traceback.format_exc()
                        _SUCCESS = False
                        logger.error("[APAPI:atexit] retry %d blocked by assertions: %s", _RETRY_COUNT, agg, exc_info=True)
                        _print_colored_exc(agg)
                        # break retry loop — assertions are not transient
                        break
            except Exception:
                pass
            retry_success = False
            if _LAST_ERARGS is not None and _LAST_SEED is not None:
                try:
                    from Main import main as ERmain
                    logger.info("[APAPI:atexit] retrying Main.main (seed=%s) %d/%d", _LAST_SEED, _RETRY_COUNT, _MAX_RETRIES)
                    ERmain(_LAST_ERARGS, _LAST_SEED, _LAST_BAKED)
                    retry_success = True
                    logger.info("[APAPI:atexit] retry succeeded")
                except BaseException as exc2:  # noqa: BLE001
                    # If it's an assertion aggregate, don't count as retryable
                    try:
                        from .assertions import APAPIAssertionAggregateError as _AAE

                        if isinstance(exc2, _AAE):
                            _LAST_ERROR = exc2
                            _LAST_TRACE = traceback.format_exc()
                            _SUCCESS = False
                            logger.error("[APAPI:atexit] retry %d assertions still failed: %s", _RETRY_COUNT, exc2, exc_info=True)
                            _print_colored_exc(exc2)
                            break
                    except Exception:
                        pass
                    _LAST_ERROR = exc2
                    _LAST_TRACE = traceback.format_exc()
                    _SUCCESS = False
                    logger.error("[APAPI:atexit] retry %d failed: %s", _RETRY_COUNT, exc2, exc_info=True)
                    _print_colored_exc(exc2)
                else:
                    _SUCCESS = True
                    _LAST_ERROR = None
                    _LAST_TRACE = None
            else:
                try:
                    from Generate import main as GenMain
                    from Main import main as ERmain
                    logger.info("[APAPI:atexit] retrying Generate.main %d/%d", _RETRY_COUNT, _MAX_RETRIES)
                    gen_result = GenMain()
                    if isinstance(gen_result, tuple) and len(gen_result) == 2:
                        _LAST_ERARGS, _LAST_SEED = gen_result
                        erargs, seed = gen_result
                    else:
                        erargs, seed = _LAST_ERARGS, _LAST_SEED  # type: ignore
                    logger.info("[APAPI:atexit] retrying Main.main (seed=%s)", seed)
                    ERmain(erargs, seed, _LAST_BAKED)
                    retry_success = True
                    logger.info("[APAPI:atexit] full retry succeeded")
                except BaseException as exc2:  # noqa: BLE001
                    try:
                        from .assertions import APAPIAssertionAggregateError as _AAE2

                        if isinstance(exc2, _AAE2):
                            _LAST_ERROR = exc2
                            _LAST_TRACE = traceback.format_exc()
                            _SUCCESS = False
                            logger.error("[APAPI:atexit] retry %d assertions still failed: %s", _RETRY_COUNT, exc2, exc_info=True)
                            _print_colored_exc(exc2)
                            break
                    except Exception:
                        pass
                    _LAST_ERROR = exc2
                    _LAST_TRACE = traceback.format_exc()
                    _SUCCESS = False
                    logger.error("[APAPI:atexit] retry %d failed: %s", _RETRY_COUNT, exc2, exc_info=True)
                    _print_colored_exc(exc2)
                else:
                    _SUCCESS = True
                    _LAST_ERROR = None
                    _LAST_TRACE = None
            if retry_success:
                break
        if _SUCCESS:
            logger.info("[APAPI:atexit] generation recovered (%d attempt(s))", _RETRY_COUNT)
            try:
                if _all_patches_settled():
                    remove_atexit_gate()
            except Exception:
                pass
            try:
                try:
                    atexit.unregister(input)  # type: ignore[arg-type]
                except Exception:
                    pass
                import builtins
                try:
                    builtins.input = lambda *a, **kw: ""  # type: ignore
                except Exception:
                    pass
            except Exception:
                pass
            try:
                sys.exit(0)
            except SystemExit:
                raise SystemExit(0) from None
        else:
            logger.warning("[APAPI:atexit] all %d retries failed", _RETRY_COUNT)
            _print_colored_exc(_LAST_ERROR)
    finally:
        _IN_HANDLER = False


def _patch_atexit_register() -> None:
    global _PATCHED_ATEXIT, _ORIG_ATEXIT_REGISTER
    if _PATCHED_ATEXIT:
        return
    try:
        _ORIG_ATEXIT_REGISTER = atexit.register
        orig = atexit.register

        def _wrapped_register(func, *args, **kwargs):  # type: ignore
            result = orig(func, *args, **kwargs)
            try:
                is_input_prompt = func is input or getattr(func, "__name__", "") == "input"
                if is_input_prompt:
                    try:
                        atexit.unregister(_atexit_handler)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        orig(_atexit_handler)
                    except Exception:
                        pass
            except Exception:
                pass
            return result

        atexit.register = _wrapped_register  # type: ignore
        _PATCHED_ATEXIT = True
    except Exception:
        pass


def initialize_atexit_gate() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        _install_wrappers()
        _install_excepthook()
        _patch_atexit_register()
        atexit.register(_atexit_handler)
    except Exception:
        return
    _INSTALLED = True


def get_atexit_state() -> dict[str, Any]:
    return {
        "installed": _INSTALLED,
        "retry_count": _RETRY_COUNT,
        "max_retries": _MAX_RETRIES,
        "last_error": _LAST_ERROR,
        "last_trace": _LAST_TRACE,
        "last_erargs": _LAST_ERARGS,
        "last_seed": _LAST_SEED,
        "success": _SUCCESS,
        "in_handler": _IN_HANDLER,
        "is_generate": _is_generate_context(),
    }


__all__ = ["initialize_atexit_gate", "get_atexit_state", "remove_atexit_gate"]
