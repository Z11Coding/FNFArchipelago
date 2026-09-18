from __future__ import annotations

"""YAML import button for Options Creator — lives entirely inside game_addons.

Patching strategy (no core/APAPI edits):
1. Try APAPI hard_patch on ``OptionsCreator.OptionsCreator.build`` — this is
   the requested "through APAPI" path. Wrapper injects the button after the
   original build returns.
2. Fallback to direct monkey-patch of ``OptionsCreator.build`` if hard_patch
   is unavailable or the target isn't loaded yet.

Button behaviour:
* Opens a file dialog (``Utils.open_filename``) for ``.yaml``/``.yml``.
* Parses the file with ``Utils.parse_yaml`` (UniqueKeyLoader → duplicate-key
  check). Shows a snackbar and aborts on parse error.
* Expects the standard exported shape: ``{name, game, description, <game>: {options}}``.
  If ``game`` is missing but exactly one top-level key is a known game whose
  value is a dict, that key is treated as the game (tolerant fallback).
* Validates:
  - ``game`` exists in ``AutoWorldRegister.world_types``.
  - ``<game>`` section is a dict.
  - Every option key exists in ``world.options_dataclass.type_hints``.
  - Every value passes ``option_cls.from_any`` **and** ``option.verify`` (with
    a dummy player name). First failure aborts with a snackbar describing the
    problem — "if the yaml is valid" otherwise nothing changes.
* On success:
  - Switches the creator to the yaml's game (programmatically selects the
    matching ``WorldButton`` and calls ``create_options_panel``) if needed.
  - Writes ``name`` into the player-name field.
  - For each option, writes ``self.options[key] = <validated>`` and updates
    the on-screen widget so the change is visible without reopening the panel
    (Toggle icon, Range slider/tag, Choice button text, FreeText text, etc.).
  - Handles the ``random`` weighting toggle where possible.

All widget updates are best-effort and guarded — a widget sync failure never
prevents the underlying ``self.options`` from being set, so Export still
produces the imported values.
"""

import logging
import pathlib
from typing import Any

logger = logging.getLogger("APAPI.GameAddons.YAMLImport")

# ---------------------------------------------------------------------------
# YAML parsing / validation (no Kivy dependency)
# ---------------------------------------------------------------------------

def _load_yaml_data(path: pathlib.Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse a YAML file. Returns (data, error)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return None, f"Could not read file: {exc}"
    # Try single-doc parse first; fall back to multi-doc if needed
    try:
        import Utils
        data = Utils.parse_yaml(text)
    except Exception as exc:
        return None, f"YAML parse error: {exc}"
    # Utils.parse_yaml returns None for empty file
    if data is None:
        return None, "YAML is empty or could not be parsed."
    if not isinstance(data, dict):
        # Could be a list of docs? Try load_all
        try:
            import Utils as _U
            docs = list(_U.parse_yamls(text))  # type: ignore[attr-defined]
            # parse_yamls is not exported; use yaml directly
        except Exception:
            pass
        return None, "Top-level YAML must be a mapping (dict)."
    return data, None


def _infer_game(data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (game, error). Tries tolerant inference if 'game' missing."""
    game = data.get("game")
    if isinstance(game, str) and game.strip():
        return game.strip(), None
    # Fallback: exactly one top-level key is a known game with dict value
    try:
        from worlds.AutoWorld import AutoWorldRegister
        candidates = [
            k for k, v in data.items()
            if isinstance(k, str) and k in AutoWorldRegister.world_types and isinstance(v, dict)
        ]
        if len(candidates) == 1:
            inferred = candidates[0]
            logger.info("[GameAddons] Inferred game '%s' from top-level key (no 'game' field).", inferred)
            return inferred, None
    except Exception:
        pass
    return None, "Missing or invalid 'game' field in YAML."


def _validate_yaml(
    data: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None, str | None, str | None]:
    """Validate structure and option values.

    Returns (game, options_dict, player_name, error_text). On error, first
    three are None and error_text describes the problem. Does NOT mutate.
    """
    game, err = _infer_game(data)
    if err:
        return None, None, None, err
    assert game is not None
    try:
        from worlds.AutoWorld import AutoWorldRegister
    except Exception as exc:
        return None, None, None, f"Could not access world registry: {exc}"
    if game not in AutoWorldRegister.world_types:
        return None, None, None, f"Unknown game '{game}'. Is its apworld installed?"
    world_type = AutoWorldRegister.world_types[game]
    raw_opts = data.get(game)
    if not isinstance(raw_opts, dict):
        return None, None, None, f"Missing '{game}' options section (expected mapping under key '{game}')."
    # player name
    name_raw = data.get("name")
    player_name: str | None = None
    if isinstance(name_raw, str) and name_raw.strip():
        player_name = name_raw.strip()

    # per-option validation
    try:
        type_hints: dict[str, Any] = world_type.options_dataclass.type_hints  # type: ignore[attr-defined]
    except Exception as exc:
        return None, None, None, f"Could not read options for '{game}': {exc}"

    errors: list[str] = []
    validated: dict[str, Any] = {}
    # For verify we need a PlandoOptions value; 0 = no plando
    try:
        from BaseClasses import PlandoOptions
        plando_zero = PlandoOptions(0)
    except Exception:
        plando_zero = 0  # type: ignore

    for key, raw_val in raw_opts.items():
        if key not in type_hints:
            errors.append(f"Unknown option '{key}' for '{game}'")
            continue
        option_cls = type_hints[key]
        try:
            inst = option_cls.from_any(raw_val)
        except Exception as exc:
            errors.append(f"Option '{key}' value {raw_val!r}: {exc}")
            continue
        # Run verify (item/location name checks etc.) — best effort
        try:
            # inst.verify expects (world_type, player_name, plando_options)
            inst.verify(world_type, player_name or "Player", plando_zero)  # type: ignore[arg-type]
        except Exception as exc:
            errors.append(f"Option '{key}' verification failed: {exc}")
            continue
        validated[key] = raw_val

    if errors:
        # Show first few errors, cap length
        head = "; ".join(errors[:5])
        if len(errors) > 5:
            head += f" (+{len(errors)-5} more)"
        return None, None, None, head

    return game, validated, player_name, None


# ---------------------------------------------------------------------------
# Widget sync helpers (Kivy/KivyMD — imported lazily)
# ---------------------------------------------------------------------------

def _find_widgets_by_name(root: Any) -> dict[str, Any]:
    """Recursively collect every widget that has .name and .option."""
    found: dict[str, Any] = {}
    stack: list[Any] = [root]
    seen: set[int] = set()
    while stack:
        w = stack.pop()
        if w is None or id(w) in seen:
            continue
        seen.add(id(w))
        try:
            if hasattr(w, "name") and hasattr(w, "option"):
                n = getattr(w, "name", None)
                if isinstance(n, str) and n:
                    found[n] = w
        except Exception:
            pass
        # Traverse all plausible containers — Kivy widgets store children in
        # .children, but ScrollBox uses .layout, MDExpansionPanel uses
        # .content/.header, and Kivy Builder uses .ids dict.
        containers: list[Any] = []
        try:
            children = getattr(w, "children", None)
            if children:
                containers.extend(list(children))
        except Exception:
            pass
        for attr in ("layout", "content", "header", "container"):
            try:
                val = getattr(w, attr, None)
                if val is not None and id(val) not in seen:
                    containers.append(val)
                    # If layout is a layout widget, also add its children
                    try:
                        inner = getattr(val, "children", None)
                        if inner:
                            containers.extend(list(inner))
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            ids = getattr(w, "ids", None)
            if isinstance(ids, dict):
                for v in ids.values():
                    if v is not None and id(v) not in seen:
                        containers.append(v)
            elif ids is not None:
                # ids can be an ObservableDict-like
                try:
                    for v in list(ids.values()):
                        if v is not None and id(v) not in seen:
                            containers.append(v)
                except Exception:
                    pass
        except Exception:
            pass
        for ch in containers:
            if ch is not None and id(ch) not in seen:
                stack.append(ch)
    return found


def _set_toggle_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    try:
        inst = option_cls.from_any(raw)
        bool_val = bool(inst.value)
    except Exception:
        bool_val = bool(raw)
    try:
        # VisualToggle has .button (MDIconButton)
        btn = getattr(widget, "button", None)
        if btn is not None:
            btn.icon = "checkbox-outline" if bool_val else "checkbox-blank-outline"
    except Exception:
        pass
    app_options[key] = bool_val


def _set_range_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    # VisualRange
    try:
        # Handle random strings: store as-is, do not touch slider
        if isinstance(raw, str) and raw.startswith("random"):
            app_options[key] = raw
            # Try to mark random toggle, leave slider alone
            return
        inst = option_cls.from_any(raw)
        int_val = int(inst.value)
        # Clamp
        try:
            lo = int(getattr(option_cls, "range_start", 0))
            hi = int(getattr(option_cls, "range_end", int_val))
            int_val = max(lo, min(int_val, hi))
        except Exception:
            pass
        try:
            widget.slider.value = int_val
        except Exception:
            pass
        try:
            widget.tag.text = str(int_val)
        except Exception:
            pass
        app_options[key] = int_val
    except Exception as exc:
        logger.debug("range sync failed for %s: %s", key, exc)


def _set_named_range_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    # VisualNamedRange contains .range (VisualRange) and .choice (MDButton)
    if isinstance(raw, str) and raw.startswith("random"):
        app_options[key] = raw
        return
    try:
        # raw could be string special name or int
        lower = str(raw).lower() if isinstance(raw, str) else None
        special = getattr(option_cls, "special_range_names", {}) or {}
        # Case 1: string special name
        if lower is not None and lower in special:
            val = int(special[lower])
            try:
                widget.range.slider.value = val
            except Exception:
                pass
            try:
                widget.range.tag.text = str(val)
            except Exception:
                pass
            # choice button text
            try:
                # MDButton -> MDButtonText is .text
                btn = getattr(widget, "choice", None)
                if btn is not None:
                    # btn.text is MDButtonText
                    inner = getattr(btn, "text", None)
                    if inner is not None and hasattr(inner, "text"):
                        inner.text = lower.title()
                    else:
                        # fallback: try children
                        for ch in getattr(btn, "children", []):
                            if hasattr(ch, "text"):
                                ch.text = lower.title()
                                break
            except Exception:
                pass
            app_options[key] = lower
            return
        # Case 2: int or numeric string
        try:
            inst = option_cls.from_any(raw)
            int_val = int(inst.value)
        except Exception:
            int_val = int(raw)  # type: ignore
        try:
            lo = int(getattr(option_cls, "range_start", 0))
            hi = int(getattr(option_cls, "range_end", int_val))
            int_val = max(lo, min(int_val, hi))
        except Exception:
            pass
        try:
            widget.range.slider.value = int_val
        except Exception:
            pass
        try:
            widget.range.tag.text = str(int_val)
        except Exception:
            pass
        # If int matches a special value, display that name, else Custom
        try:
            inv = {v: k for k, v in special.items()}
            if int_val in inv:
                name = inv[int_val]
                display = name.title()
                app_options[key] = name
            else:
                display = "Custom"
                app_options[key] = int_val
            btn = getattr(widget, "choice", None)
            if btn is not None:
                inner = getattr(btn, "text", None)
                if inner is not None and hasattr(inner, "text"):
                    inner.text = display
        except Exception:
            app_options[key] = int_val
    except Exception as exc:
        logger.debug("named_range sync failed for %s: %s", key, exc)


def _set_choice_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    if isinstance(raw, str) and raw.startswith("random"):
        app_options[key] = raw
        # still set display to random? Leave as is
        return
    try:
        inst = option_cls.from_any(raw)
        display = option_cls.get_option_name(inst.value)
        # VisualChoice: .text is MDButtonText
        try:
            inner = getattr(widget, "text", None)
            if inner is not None and hasattr(inner, "text"):
                inner.text = display
            else:
                for ch in getattr(widget, "children", []):
                    if hasattr(ch, "text"):
                        ch.text = display
                        break
        except Exception:
            pass
        # Stored value in OptionsCreator is name_lookup[value] (string key)
        try:
            stored = option_cls.name_lookup[inst.value]  # type: ignore
        except Exception:
            try:
                stored = inst.current_key  # type: ignore
            except Exception:
                stored = raw
        app_options[key] = stored
    except Exception as exc:
        logger.debug("choice sync failed for %s: %s", key, exc)


def _set_text_choice_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    if isinstance(raw, str) and raw.startswith("random"):
        app_options[key] = raw
        return
    try:
        inst = option_cls.from_any(raw)
        if isinstance(inst.value, int):
            # It's a named choice
            display = option_cls.get_option_name(inst.value)
            try:
                choice_w = getattr(widget, "choice", None)
                if choice_w is not None:
                    inner = getattr(choice_w, "text", None)
                    if inner is not None and hasattr(inner, "text"):
                        inner.text = display
            except Exception:
                pass
            try:
                free = getattr(widget, "text", None)
                if free is not None and hasattr(free, "text"):
                    free.text = ""
            except Exception:
                pass
            try:
                stored = option_cls.name_lookup[inst.value]  # type: ignore
            except Exception:
                stored = raw
            app_options[key] = stored
        else:
            # Custom free text
            try:
                choice_w = getattr(widget, "choice", None)
                if choice_w is not None:
                    inner = getattr(choice_w, "text", None)
                    if inner is not None and hasattr(inner, "text"):
                        inner.text = "Custom"
            except Exception:
                pass
            try:
                free = getattr(widget, "text", None)
                if free is not None and hasattr(free, "text"):
                    # VisualFreeText is a ResizableTextField; setting .text triggers bind
                    free.text = str(inst.value)
            except Exception:
                pass
            app_options[key] = str(inst.value)
    except Exception as exc:
        logger.debug("text_choice sync failed for %s: %s", key, exc)


def _set_free_text_widget(widget: Any, option_cls: Any, raw: Any, app_options: dict[str, Any], key: str) -> None:
    try:
        s = str(raw)
        # VisualFreeText is itself a text field
        if hasattr(widget, "text"):
            widget.text = s
        app_options[key] = s
    except Exception as exc:
        logger.debug("free_text sync failed for %s: %s", key, exc)


def _set_set_list_counter(
    option_cls: Any, raw: Any, app_options: dict[str, Any], key: str
) -> None:
    # No widget to update beyond app_options; "Edit" button stays.
    try:
        from Options import OptionCounter, OptionSet, OptionList
    except Exception:
        app_options[key] = raw
        return
    try:
        inst = option_cls.from_any(raw)
        if issubclass(option_cls, OptionCounter):
            # inst.value is Counter/dict
            try:
                app_options[key] = dict(inst.value)
            except Exception:
                app_options[key] = dict(raw) if isinstance(raw, dict) else {}
        elif issubclass(option_cls, OptionSet):
            try:
                app_options[key] = sorted(inst.value)  # type: ignore
            except Exception:
                app_options[key] = sorted(list(raw)) if isinstance(raw, (list, set, tuple)) else []
        elif issubclass(option_cls, OptionList):
            try:
                app_options[key] = list(inst.value)  # type: ignore
            except Exception:
                app_options[key] = list(raw) if isinstance(raw, (list, tuple)) else []
        else:
            app_options[key] = raw
    except Exception as exc:
        logger.debug("set/list/counter sync failed for %s: %s", key, exc)
        # Keep raw as fallback
        app_options[key] = raw


def _sync_single_option(
    app: Any, key: str, option_cls: Any, raw: Any, widget_map: dict[str, Any]
) -> None:
    """Sync one option's widget (if any) and app.options entry."""
    from Options import (
        Choice,
        FreeText,
        NamedRange,
        Range,
        TextChoice,
        Toggle,
        OptionSet,
        OptionList,
        OptionCounter,
    )

    # Random handling: if raw is random string and option supports weighting, store as-is and try to toggle
    is_random_str = isinstance(raw, str) and raw.startswith("random")
    # Even for random, we still need to update widget disabled state if possible
    # For now, handle normal path then random toggle attempt after

    widget = widget_map.get(key)

    try:
        if issubclass(option_cls, Toggle):
            if widget is not None:
                _set_toggle_widget(widget, option_cls, raw, app.options, key)
            else:
                # no widget found, just store
                try:
                    inst = option_cls.from_any(raw)
                    app.options[key] = bool(inst.value)
                except Exception:
                    app.options[key] = bool(raw)
            return

        if issubclass(option_cls, NamedRange):
            if widget is not None:
                _set_named_range_widget(widget, option_cls, raw, app.options, key)
            else:
                # fallback preserve raw if valid else int
                try:
                    inst = option_cls.from_any(raw)
                    # For NamedRange, from_any returns int; but raw may be string name
                    if isinstance(raw, str) and raw.lower() in getattr(option_cls, "special_range_names", {}):
                        app.options[key] = raw.lower()
                    else:
                        app.options[key] = int(inst.value)
                except Exception:
                    app.options[key] = raw
            return

        if issubclass(option_cls, Range):
            if widget is not None:
                _set_range_widget(widget, option_cls, raw, app.options, key)
            else:
                try:
                    app.options[key] = int(option_cls.from_any(raw).value)
                except Exception:
                    app.options[key] = raw
            return

        if issubclass(option_cls, TextChoice):
            if widget is not None:
                _set_text_choice_widget(widget, option_cls, raw, app.options, key)
            else:
                app.options[key] = raw
            return

        if issubclass(option_cls, Choice):
            if widget is not None:
                _set_choice_widget(widget, option_cls, raw, app.options, key)
            else:
                try:
                    inst = option_cls.from_any(raw)
                    app.options[key] = option_cls.name_lookup[inst.value]  # type: ignore
                except Exception:
                    app.options[key] = raw
            return

        if issubclass(option_cls, FreeText) and not issubclass(option_cls, TextChoice):
            if widget is not None:
                _set_free_text_widget(widget, option_cls, raw, app.options, key)
            else:
                app.options[key] = str(raw)
            return

        if issubclass(option_cls, (OptionSet, OptionList, OptionCounter)):
            _set_set_list_counter(option_cls, raw, app.options, key)
            return

        # Fallback
        app.options[key] = raw
    except Exception as exc:
        logger.debug("sync for %s failed: %s", key, exc)
        app.options[key] = raw

    # Attempt random toggle disabling if needed (best-effort)
    if is_random_str:
        _try_set_random_toggle(app, key, raw, widget)


def _try_set_random_toggle(app: Any, key: str, raw: Any, widget: Any | None) -> None:
    """If option supports weighting and raw is random, set toggle down + disable widget."""
    try:
        from OptionsCreator import option_can_be_randomized
        from worlds.AutoWorld import AutoWorldRegister
        world_type = AutoWorldRegister.world_types.get(getattr(app, "current_game", ""), None)
        if world_type is None:
            return
        type_hints = getattr(world_type.options_dataclass, "type_hints", {})  # type: ignore
        option_cls = type_hints.get(key)
        if option_cls is None or not option_can_be_randomized(option_cls):
            return
        # Find option_base for this key by walking option_layout
        # option_base is MDBoxLayout with children: label_box + widget
        # We can search for ToggleButton with text "Random?" inside label_box
        # Instead of precise search, look for any ToggleButton whose parent chain contains label
        is_random = isinstance(raw, str) and raw.startswith("random")
        target_state = "down" if is_random else "normal"
        # Search in option_layout subtree
        root = getattr(app, "option_layout", None)
        if root is None:
            return
        # BFS to find option_base widgets that contain a child with .name == key
        # Use _find_widgets_by_name to get widget, then find its parent option_base
        # Simpler: traverse expansion panels
        _set_random_state_for_key(root, key, target_state, widget)
    except Exception:
        pass


def _set_random_state_for_key(root: Any, key: str, state: str, widget: Any | None) -> None:
    """Locate the option_base for key and set its random ToggleButton state."""
    try:
        # Walk all widgets, find MDBoxLayout that has a child with attribute name == key? Not.
        # Alternative: find all ToggleButtons inside root and check if their parent's sibling contains widget
        # Simpler: brute force search for option_base candidates
        # An option_base is the MDBoxLayout created in create_option — it has two children:
        # label_box (contains label + random toggle) and the visual widget
        # So we can find widget's parent
        if widget is not None:
            # widget.parent should be option_base
            parent = getattr(widget, "parent", None)
            if parent is not None:
                # parent.children contains widget and label_box
                for child in list(getattr(parent, "children", [])):
                    # look for ToggleButton inside child
                    stack = [child]
                    seen = set()
                    while stack:
                        w = stack.pop()
                        if id(w) in seen:
                            continue
                        seen.add(id(w))
                        if w.__class__.__name__ == "ToggleButton" or "ToggleButton" in str(type(w)):
                            # Heuristic: check text contains Random?
                            txt = getattr(w, "text", "")
                            # ToggleButton may have MDButtonText child
                            if isinstance(txt, str) and "Random" in txt:
                                w.state = state
                            else:
                                # Check children for MDButtonText with Random
                                for ch in getattr(w, "children", []):
                                    t = getattr(ch, "text", "")
                                    if isinstance(t, str) and "Random" in t:
                                        w.state = state
                                        break
                                # Also check widget.disabled
                            # Disable main widget per random spec
                            if widget is not None:
                                try:
                                    widget.disabled = (state == "down")
                                except Exception:
                                    pass
                            return
                        for ch in getattr(w, "children", []):
                            stack.append(ch)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Import flow — called from the patched OptionsCreator
# ---------------------------------------------------------------------------

def _switch_to_game(app: Any, target_game: str) -> bool:
    """Switch creator to target_game. Returns True if switched or already there."""
    if getattr(app, "current_game", "") == target_game:
        return True
    try:
        scrollbox = getattr(app, "scrollbox", None)
        if scrollbox is None or not hasattr(scrollbox, "layout"):
            return False
        buttons = list(getattr(scrollbox.layout, "children", []))
        target_btn = None
        for btn in buttons:
            wc = getattr(btn, "world_cls", None)
            if wc is not None and getattr(wc, "game", None) == target_game:
                target_btn = btn
                break
        if target_btn is None:
            return False
        # Mimic world_button_action logic
        old_game = getattr(app, "current_game", "")
        old_btn = None
        for b in buttons:
            wc2 = getattr(b, "world_cls", None)
            if wc2 is not None and getattr(wc2, "game", None) == old_game:
                old_btn = b
                break
        if old_btn is not None and old_btn is not target_btn:
            try:
                old_btn.state = "normal"
            except Exception:
                pass
        try:
            target_btn.state = "down"
        except Exception:
            pass
        # This is the choke point — rebuilds option_layout and self.options
        app.create_options_panel(target_btn)
        return True
    except Exception as exc:
        logger.warning("Game switch to '%s' failed: %s", target_game, exc, exc_info=True)
        return False


def _apply_imported_data(app: Any, game: str, validated: dict[str, Any], player_name: str | None) -> None:
    """Apply validated options + name to the live OptionsCreator instance."""
    # Switch game first (recreates panel & clears app.options)
    if not _switch_to_game(app, game):
        _show_snack(app, f"Could not switch to game '{game}'.")
        return

    # Update player name field
    if player_name:
        try:
            name_input = getattr(app, "name_input", None)
            if name_input is not None:
                # ResizableTextField's text property
                name_input.text = player_name[:16]
        except Exception as exc:
            logger.debug("Failed to set player name: %s", exc)

    # Build widget map once after switch
    try:
        root = getattr(app, "option_layout", None)
        widget_map = _find_widgets_by_name(root) if root is not None else {}
    except Exception:
        widget_map = {}

    # Need world type hints to know option classes
    try:
        from worlds.AutoWorld import AutoWorldRegister
        world_type = AutoWorldRegister.world_types[game]
        type_hints = world_type.options_dataclass.type_hints  # type: ignore
    except Exception as exc:
        logger.warning("Could not get type_hints for %s: %s", game, exc)
        type_hints = {}

    # Apply each option
    applied = 0
    for key, raw in validated.items():
        option_cls = type_hints.get(key)
        if option_cls is None:
            # Should not happen after validation, but keep
            app.options[key] = raw
            applied += 1
            continue
        _sync_single_option(app, key, option_cls, raw, widget_map)
        applied += 1

    # Some options (e.g. OptionSet) may be missing from widget_map; ensure they're still in app.options
    # (handled inside _sync_single_option fallback)

    _show_snack(app, f"Imported {applied} option(s) for '{game}'.")


def _show_snack(app: Any, text: str) -> None:
    try:
        from kvui import dp
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.5,
        ).open()
    except Exception:
        try:
            # Fallback to app helper if present
            if hasattr(app, "show_result_snack"):
                app.show_result_snack(text)
            else:
                logger.info(text)
        except Exception:
            logger.info(text)


def _on_import_yaml_clicked(self: Any) -> None:  # type: ignore
    """Handler for the Import YAML button (installed as a method)."""
    try:
        import Utils
    except Exception as exc:
        _show_snack(self, f"Cannot open dialog: {exc}")
        return

    try:
        file_name = Utils.open_filename(  # type: ignore[attr-defined]
            "Import YAML...",
            [("YAML", [".yaml", ".yml"])],
            "",
        )
    except Exception as exc:
        _show_snack(self, f"Could not open dialog: {exc}")
        return

    if not file_name:
        return  # cancelled

    path = pathlib.Path(file_name)
    data, err = _load_yaml_data(path)
    if err:
        _show_snack(self, err)
        return
    assert data is not None
    game, validated, player_name, v_err = _validate_yaml(data)
    if v_err:
        _show_snack(self, f"Invalid YAML: {v_err}")
        return
    assert game is not None and validated is not None
    try:
        _apply_imported_data(self, game, validated, player_name)
    except Exception as exc:
        logger.warning("Import apply failed: %s", exc, exc_info=True)
        _show_snack(self, f"Import failed: {exc}")


def _inject_import_button(app: Any) -> None:
    """Add Import YAML button next to Export after build. Idempotent."""
    # Guard against double-injection
    if getattr(app, "_gameaddons_import_injected", False):
        return
    try:
        from kvui import dp
        from kivymd.uix.button import MDButton, MDButtonText
        from kivymd.uix.boxlayout import MDBoxLayout as KMDBoxLayout
        from kivy.uix.boxlayout import BoxLayout as KBoxLayout
    except Exception as exc:
        logger.warning("KivyMD not available for button injection: %s", exc)
        return

    try:
        # Prefer the high-level ids set in build()
        player_options = getattr(app, "player_options", None)
        # The vertical box that holds game label + Export is inside player_options
        # Find its parent and the Export button
        export_parent = None
        export_btn = None

        # Strategy: search for any widget with text "Export Options" (could be MDButtonText itself)
        def _find_export(root: Any) -> tuple[Any | None, Any | None]:
            if root is None:
                return None, None
            stack: list[Any] = [root]
            seen: set[int] = set()
            while stack:
                w = stack.pop()
                if w is None or id(w) in seen:
                    continue
                seen.add(id(w))
                try:
                    if getattr(w, "text", None) == "Export Options":
                        # w is likely MDButtonText; parent is MDButton
                        parent = getattr(w, "parent", None)
                        if parent is not None and "Button" in type(parent).__name__:
                            return parent, getattr(parent, "parent", None)
                        return w, getattr(w, "parent", None)
                except Exception:
                    pass
                # Also check if w itself is a button whose text child matches (fallback for older KivyMD)
                try:
                    for ch in list(getattr(w, "children", []) or []):
                        if getattr(ch, "text", None) == "Export Options":
                            return w, getattr(w, "parent", None)
                        # one more level: MDButton -> MDButtonText
                        for sub in list(getattr(ch, "children", []) or []):
                            if getattr(sub, "text", None) == "Export Options":
                                return ch, getattr(ch, "parent", None)
                except Exception:
                    pass
                try:
                    for ch in list(getattr(w, "children", []) or []):
                        stack.append(ch)
                    for attr in ("layout", "content", "header", "container"):
                        val = getattr(w, attr, None)
                        if val is not None and id(val) not in seen:
                            stack.append(val)
                    ids = getattr(w, "ids", None)
                    if isinstance(ids, dict):
                        for v in ids.values():
                            if v is not None:
                                stack.append(v)
                except Exception:
                    pass
            return None, None

        if player_options is not None:
            export_btn, export_parent = _find_export(player_options)
        else:
            export_btn, export_parent = None, None

        # Fallback: search in container
        if export_btn is None or export_parent is None:
            container = getattr(app, "container", None)
            export_btn, export_parent = _find_export(container)

        if export_btn is None or export_parent is None:
            logger.warning("[GameAddons] Could not locate Export button; adding Import to player_options fallback.")
            # Fallback: add to player_options directly
            try:
                import_btn = MDButton(
                    MDButtonText(text="Import YAML", pos_hint={"center_x": 0.5, "center_y": 0.5}),
                    on_release=lambda *_: app._gameaddons_import_yaml(),  # type: ignore
                    theme_width="Custom",
                    size_hint_x=None,
                    width=dp(130),
                    pos_hint={"center_x": 0.5, "center_y": 0.5},
                )
                if player_options is not None:
                    player_options.add_widget(import_btn)
                    app._gameaddons_import_injected = True  # type: ignore
                    logger.info("[GameAddons] Import YAML button injected (fallback to player_options).")
                    return
            except Exception as exc2:
                logger.warning("Fallback injection failed: %s", exc2)
                return
            return

        # We have export_parent (usually the vertical MDBoxLayout with orientation vertical)
        # To place Import beside Export nicely, wrap them in a horizontal box if parent is vertical,
        # otherwise just add beside.
        try:
            orientation = getattr(export_parent, "orientation", None)
        except Exception:
            orientation = None

        import_btn = MDButton(
            MDButtonText(text="Import YAML", pos_hint={"center_x": 0.5, "center_y": 0.5}),
            on_release=lambda *_: app._gameaddons_import_yaml(),  # type: ignore
            theme_width="Custom",
            size_hint_y=1,
            size_hint_x=1,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )

        try:
            if orientation == "vertical":
                # export_parent currently stacks label + Export vertically.
                # Keep label at top, then put a horizontal box with Export + Import below.
                # Remove export from parent, add horizontal container, then re-add export into it plus import.
                try:
                    export_parent.remove_widget(export_btn)
                except Exception:
                    pass
                # Build horizontal container
                try:
                    hbox = KMDBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
                except Exception:
                    hbox = KBoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
                # Ensure buttons fill horizontally
                for b in (export_btn, import_btn):
                    try:
                        b.size_hint_x = 1
                        b.size_hint_y = 1
                    except Exception:
                        pass
                hbox.add_widget(export_btn)
                hbox.add_widget(import_btn)
                export_parent.add_widget(hbox)
            else:
                # Parent is already horizontal or unknown — just add import beside export
                export_parent.add_widget(import_btn)
            app._gameaddons_import_injected = True  # type: ignore
            logger.info("[GameAddons] Import YAML button injected next to Export.")
        except Exception as exc:
            logger.warning("[GameAddons] Injection layout failed, trying simple add: %s", exc)
            try:
                export_parent.add_widget(import_btn)
                app._gameaddons_import_injected = True  # type: ignore
            except Exception as exc2:
                logger.warning("Simple add also failed: %s", exc2)
    except Exception as exc:
        logger.warning("[GameAddons] Button injection failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Public entry point — called from worlds.game_addons.__init__
# ---------------------------------------------------------------------------

def _ensure_module_update() -> None:
    """Neutralize ModuleUpdate version gate that blocks OptionsCreator on Py 3.14."""
    try:
        import ModuleUpdate  # type: ignore
    except RuntimeError:
        import sys, types
        fake = types.ModuleType("ModuleUpdate")
        fake.update = lambda *a, **k: None  # type: ignore[attr-defined]
        sys.modules["ModuleUpdate"] = fake
    except Exception:
        pass


def _do_install_patch() -> None:
    """Inner installer — expects OptionsCreator importable. Raises on failure."""
    try:
        from worlds.APAPI.launch_context import should_skip_gui_patch
        if should_skip_gui_patch():
            logger.info("[GameAddons] Skipping YAML import patch — generation context (no GUI).")
            return
    except Exception:
        pass
    _ensure_module_update()
    from OptionsCreator import OptionsCreator  # type: ignore

    # Attach handler method (idempotent)
    if not hasattr(OptionsCreator, "_gameaddons_import_yaml"):
        OptionsCreator._gameaddons_import_yaml = _on_import_yaml_clicked  # type: ignore[attr-defined]

    if getattr(OptionsCreator, "_gameaddons_yaml_patch_done", False):
        return

    # Use APAPI hard_patch — wrapper must forward *args/**kwargs correctly
    # This is the APAPI-native way; hard_patches.add_wrapper builds a chain
    # that calls wrapper(next_callable, *args, **kwargs).
    def _hard_wrapper(next_callable, *args, **kwargs):  # type: ignore
        container = next_callable(*args, **kwargs)
        try:
            # args[0] is the OptionsCreator instance (self)
            app = args[0] if args else None
            if app is not None:
                _inject_import_button(app)
        except Exception as exc:
            logger.warning("[GameAddons] APAPI wrapper injection failed: %s", exc, exc_info=True)
        return container

    # Prefer APAPI public API register_hard_wrapper; fall back to hard_patches directly
    try:
        from worlds.APAPI import register_hard_wrapper  # type: ignore
        register_hard_wrapper("OptionsCreator.OptionsCreator.build", _hard_wrapper)
    except Exception:
        from worlds.APAPI.hard_patch import hard_patches  # type: ignore
        hard_patches.add_wrapper("OptionsCreator.OptionsCreator.build", _hard_wrapper)

    OptionsCreator._gameaddons_yaml_patch_done = True  # type: ignore
    logger.info("[GameAddons] YAML Import button patch installed via APAPI hard_patch.")


def init_yaml_import_patch() -> None:
    """Install the Import YAML button — defers via APAPI if needed."""
    try:
        from worlds.APAPI.launch_context import should_skip_gui_patch
        if should_skip_gui_patch():
            logger.info("[GameAddons] init deferred — generation context, will not patch GUI.")
            return
    except Exception:
        pass
    try:
        _do_install_patch()
        return
    except Exception as exc:
        logger.debug("[GameAddons] Patch not ready (%s); deferring via APAPI.", exc)
        # Rely on APAPI's own deferral (world_ready poll worker) — no custom retry thread
        try:
            from worlds.APAPI import on_worlds_loaded  # type: ignore
            # on_worlds_loaded queues the callback and retries via APAPI's poll worker
            # (0.25s interval, 120s timeout) — this is APAPI-native retry logic.
            on_worlds_loaded(_do_install_patch)
            logger.info("[GameAddons] YAML import patch deferred via APAPI on_worlds_loaded.")
        except Exception as defer_exc:
            logger.warning("[GameAddons] Failed to defer YAML import patch: %s", defer_exc, exc_info=True)


__all__ = ["init_yaml_import_patch"]
