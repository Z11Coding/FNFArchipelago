"""Bridge for Mystery Game and Universal Tracker. Exposes real game for hashed slots and adds relay tracker tab."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("APAPI.MysteryTrackerBridge")

try:
    from worlds.APAPI.world_ready import when_game_available, on_worlds_loaded
    from worlds.APAPI import inject_world_behavior
    HAS_APAPI = True
except Exception:
    HAS_APAPI = False
    when_game_available = lambda *a, **k: None  # type: ignore
    on_worlds_loaded = lambda *a, **k: None  # type: ignore
    inject_world_behavior = lambda *a, **k: None  # type: ignore

# ---------------------------------------------------------------------------
# 1) Inject mystery_real_game into hashed slots' slot_data (for UT direct connect)
# ---------------------------------------------------------------------------

def _mystery_identity_after_fill(result: Any, world_self: Any, *args: Any, **kwargs: Any) -> Any:
    """Inject real game and slot into slot_data for Mystery-hashed players so UT can find the correct world."""
    if not isinstance(result, dict):
        result = {}
    try:
        player = getattr(world_self, "player", None)
        mw = getattr(world_self, "multiworld", None)
        if mw is not None and player is not None:
            # Try shared dict first (available after pre_output), then fallback to mystery world's identity_map
            identities = getattr(mw, "_mystery_identities", None)
            if not isinstance(identities, dict) or player not in identities:
                # Fallback: search for MysteryGameWorld instance and its identity_map (available already in generate_early)
                for w in getattr(mw, "worlds", {}).values():
                    try:
                        if getattr(w, "game", None) == "Mystery Game" and hasattr(w, "identity_map"):
                            im = getattr(w, "identity_map", None)
                            if isinstance(im, dict) and player in im:
                                identities = im
                                break
                    except Exception:
                        continue
            if isinstance(identities, dict) and player in identities:
                info = identities[player]
                # Provide real game/slot so UT can generate correctly even though server reports hashed name
                result.setdefault("mystery_real_game", info.get("game"))
                result.setdefault("mystery_real_slot", info.get("slot"))
                result.setdefault("mystery_server_game", info.get("server_game"))
                result.setdefault("mystery_server_slot", info.get("server_slot"))
                # Also expose for debugging
                try:
                    logger.info("[MysteryTrackerBridge] injected mystery_real_game=%r for player %s (hashed %r)", info.get("game"), player, info.get("server_game"))
                except Exception:
                    pass
    except Exception:
        pass
    return result


def _install_mystery_identity_hook() -> None:
    """Install the fill_slot_data hook for all games to expose mystery_real_game."""
    try:
        from worlds.AutoWorld import AutoWorldRegister

        # Inject for all currently loaded worlds
        for g in list(AutoWorldRegister.world_types.keys()):
            try:
                inject_world_behavior(g, "fill_slot_data", after=_mystery_identity_after_fill)
            except Exception:
                pass

        # Also hook future worlds via world_ready
        def _late_install() -> None:
            try:
                from worlds.AutoWorld import AutoWorldRegister as _Reg

                for gg in list(_Reg.world_types.keys()):
                    try:
                        inject_world_behavior(gg, "fill_slot_data", after=_mystery_identity_after_fill)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            on_worlds_loaded(_late_install)
        except Exception:
            pass
        logger.info("[MysteryTrackerBridge] installed mystery_real_game hook for all worlds")
    except Exception as exc:
        logger.warning("[MysteryTrackerBridge] failed to install identity hook: %s", exc)


def _make_mystery_ut_friendly(mystery_cls: Any) -> None:
    """Ensure Mystery Game itself is not tracked by UT. UT should track underlying real games instead."""
    try:
        # Explicitly disable UT for Mystery Game itself – UT should track the underlying real games, not the Mystery wrapper
        # We set a flag so if UT ever tries to connect to Mystery Game, it will show disabled message rather than attempt generation
        # Leave ut_can_gen_without_yaml as is (default False) – don't enable
        # If the world had it enabled, we leave it; but we ensure disable_ut is set if not already
        # Actually we want to prevent UT tracking Mystery Game itself, so we can set disable_ut = True
        # However to avoid breaking existing behavior for users who might want it, we just ensure there's no forced enable
        if getattr(mystery_cls, "ut_can_gen_without_yaml", False):
            # User clarified they don't want Mystery Game itself tracked – log but don't force off if author enabled
            logger.info("[MysteryTrackerBridge] Mystery Game ut_can_gen_without_yaml left as %s (UT will not track Mystery itself per user request)", getattr(mystery_cls, "ut_can_gen_without_yaml"))
        # We do NOT inject interpret_slot_data for Mystery Game
        logger.info("[MysteryTrackerBridge] Mystery Game left not UT-friendly (as requested)")
    except Exception as exc:
        logger.warning("[MysteryTrackerBridge] _make_mystery_ut_friendly failed: %s", exc)


def _patch_ut_for_mystery_relay(tracker_cls: Any = None) -> None:
    """Patch UT to use mystery_real_game from slot_data when connecting to hashed Mystery slots."""
    try:
        from worlds.tracker.TrackerClient import TrackerGameContext  # type: ignore

        _orig_on_pkg = TrackerGameContext.on_package

        def _patched_on_pkg(self: Any, cmd: str, args: dict) -> None:  # type: ignore
            if cmd == "Connected":
                try:
                    slot = args.get("slot")
                    slot_info = args.get("slot_info", {})
                    slot_data = args.get("slot_data", {})
                    # slot_data may contain mystery_real_game for hashed slots
                    real_game = None
                    real_slot = None
                    if isinstance(slot_data, dict):
                        real_game = slot_data.get("mystery_real_game")
                        real_slot = slot_data.get("mystery_real_slot")
                    # Also handle case where UT connected to a hashed slot but slot_data still has hashed game;
                    # we want to override the game that UT will use for generation.
                    # We do this by patching the args dict in-place before calling original.
                    if isinstance(real_game, str) and real_game:
                        # Override slot_info entry for this slot to use real game/slot
                        # slot_info keys may be int or str
                        for key in (slot, str(slot)):
                            if key in slot_info:
                                entry = slot_info[key]
                                # entry is usually tuple (name, game) or object with .name/.game
                                try:
                                    if hasattr(entry, "_replace"):
                                        # Named tuple from NetUtils
                                        new_name = real_slot if isinstance(real_slot, str) else getattr(entry, "name", None)
                                        slot_info[key] = entry._replace(game=real_game, name=new_name if new_name else entry.name)  # type: ignore[attr-defined]
                                    elif isinstance(entry, dict):
                                        entry = dict(entry)
                                        entry["game"] = real_game
                                        if isinstance(real_slot, str):
                                            entry["name"] = real_slot
                                        slot_info[key] = entry
                                    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                                        lst = list(entry)
                                        if isinstance(real_slot, str):
                                            lst[0] = real_slot
                                        lst[1] = real_game
                                        slot_info[key] = tuple(lst) if isinstance(entry, tuple) else lst
                                except Exception:
                                    pass
                                break
                        logger.info("[MysteryTrackerBridge] UT direct connect: hashed -> real game %r (slot %r) for slot %s", real_game, real_slot, slot)
                    else:
                        # No mystery_real_game – log details to help debug
                        try:
                            # Find the hashed entry for this slot
                            hashed_game = None
                            hashed_name = None
                            for key in (slot, str(slot)):
                                if key in slot_info:
                                    e = slot_info[key]
                                    if hasattr(e, "game"):
                                        hashed_game = e.game
                                        hashed_name = getattr(e, "name", None)
                                    elif isinstance(e, dict):
                                        hashed_game = e.get("game")
                                        hashed_name = e.get("name")
                                    elif isinstance(e, (list, tuple)) and len(e) >= 2:
                                        hashed_name, hashed_game = e[0], e[1]
                                    break
                            keys = list(slot_data.keys()) if isinstance(slot_data, dict) else []
                            logger.warning("[MysteryTrackerBridge] UT direct connect: NO mystery_real_game for slot %s (hashed game %r name %r) slot_data keys=%s", slot, hashed_game, hashed_name, keys[:10])
                        except Exception:
                            pass
                        if isinstance(slot_info, dict):
                            for pid, entry in slot_info.items():
                                g = None
                                if hasattr(entry, "game"):
                                    g = entry.game
                                elif isinstance(entry, dict):
                                    g = entry.get("game")
                                elif isinstance(entry, (list, tuple)) and len(entry) > 1:
                                    g = entry[1]
                                if g == "Mystery Game" or g == "Mystery Cheese":
                                    logger.info("[MysteryTrackerBridge] UT connected to Mystery Game slot (not tracking Mystery itself) pid %s", pid)
                                    break
                except Exception as exc:
                    logger.debug("[MysteryTrackerBridge] UT mystery_real_game override failed: %s", exc)
            return _orig_on_pkg(self, cmd, args)

        if getattr(TrackerGameContext.on_package, "_mystery_patched", False) is not True:
            _patched_on_pkg._mystery_patched = True  # type: ignore[attr-defined]
            TrackerGameContext.on_package = _patched_on_pkg  # type: ignore[method-assign]
            logger.info("[MysteryTrackerBridge] patched TrackerGameContext.on_package for mystery_real_game")

        # Also patch TrackerCore to handle case where connected_cls is None due to hashed game but slot_data has real
        try:
            from worlds.tracker.TrackerCore import TrackerCore  # type: ignore

            _orig_init = TrackerCore.initalize_tracker_core

            def _patched_init(self: Any, connected_cls: Any, raw_slot_data: Any) -> None:  # type: ignore
                # If connected_cls is None (hashed game not found) but raw_slot_data has mystery_real_game, try real
                if connected_cls is None and isinstance(raw_slot_data, dict):
                    rg = raw_slot_data.get("mystery_real_game")
                    if isinstance(rg, str) and rg:
                        try:
                            from worlds.AutoWorld import AutoWorldRegister
                            real_cls = AutoWorldRegister.world_types.get(rg)
                            if real_cls is not None:
                                logger.info("[MysteryTrackerBridge] TrackerCore fallback to real game %r", rg)
                                return _orig_init(self, real_cls, raw_slot_data)
                        except Exception:
                            pass
                return _orig_init(self, connected_cls, raw_slot_data)

            if getattr(TrackerCore.initalize_tracker_core, "_mystery_patched", False) is not True:
                _patched_init._mystery_patched = True  # type: ignore[attr-defined]
                TrackerCore.initalize_tracker_core = _patched_init  # type: ignore[method-assign]
                logger.info("[MysteryTrackerBridge] patched TrackerCore.initalize_tracker_core for mystery_real_game fallback")
        except Exception as exc:
            logger.debug("[MysteryTrackerBridge] TrackerCore patch skipped: %s", exc)

    except Exception as exc:
        logger.debug("[MysteryTrackerBridge] UT patch skipped (tracker not installed or load order): %s", exc)


def install() -> None:
    """Register APAPI hooks for Mystery to UT bridging."""
    if not HAS_APAPI:
        logger.debug("[MysteryTrackerBridge] APAPI not available, skipping")
        return

    # Identity hook for hashed slots (so UT can read mystery_real_game)
    try:
        _install_mystery_identity_hook()
    except Exception:
        pass

    # Patch Mystery Game when it becomes available (it is already loaded now, but use hook for safety)
    def _on_mystery(cls: Any) -> None:
        if cls is not None:
            _make_mystery_ut_friendly(cls)

    def _on_ut(cls: Any) -> None:
        if cls is not None:
            _patch_ut_for_mystery_relay(cls)

    try:
        when_game_available("Mystery Game", _on_mystery)
    except Exception:
        pass
    try:
        when_game_available("Universal Tracker", _on_ut)
    except Exception:
        pass

    # Also run immediately if worlds already loaded (on_worlds_loaded will fire soon, but do eager too)
    try:
        from worlds.AutoWorld import AutoWorldRegister
        m_cls = AutoWorldRegister.world_types.get("Mystery Game")
        if m_cls is not None:
            _make_mystery_ut_friendly(m_cls)
        # UT may not be registered yet; will be handled by when_game_available
        t_cls = AutoWorldRegister.world_types.get("Universal Tracker")
        if t_cls is not None:
            _patch_ut_for_mystery_relay(t_cls)
    except Exception:
        pass

    # Fallback: ensure patches run after all worlds loaded
    try:
        on_worlds_loaded(lambda: _patch_ut_for_mystery_relay())
    except Exception:
        pass


# Auto-install on import
try:
    install()
except Exception as exc:
    logger.warning("[MysteryTrackerBridge] auto-install failed: %s", exc)


# ---------------------------------------------------------------------------
# Helpers for MysteryClient's optional Relay Tracker tab
# ---------------------------------------------------------------------------

def is_tracker_available() -> bool:
    """Return True if Universal Tracker is installed."""
    try:
        import worlds.tracker  # noqa: F401
        from worlds.tracker.TrackerCore import TrackerCore  # noqa: F401
        from worlds.tracker.TrackerClient import TrackerGameContext  # noqa: F401

        return True
    except Exception:
        return False


def create_relay_tracker_tab(ctx: Any, gui_module: Any = None) -> Any | None:
    """Create the optional Relay Tracker tab for the Mystery Client if UT is available."""
    if not is_tracker_available():
        return None
    try:
        return _build_relay_tracker_tab(ctx, gui_module)
    except Exception as exc:
        logger.warning("[MysteryTrackerBridge] failed to build relay tracker tab: %s", exc)
        return None


def _build_relay_tracker_tab(ctx: Any, gui_module: Any = None) -> Any:
    """Build the Relay Tracker tab that shows TrackerCore state for each relay."""
    # Import lazily inside function to avoid hard dependency at generation time
    from kivy.uix.boxlayout import BoxLayout  # type: ignore
    from kivy.uix.gridlayout import GridLayout  # type: ignore
    from kivy.uix.scrollview import ScrollView  # type: ignore
    from kvui import MDLabel, MDButton, MDButtonText  # type: ignore

    from worlds.tracker.TrackerCore import TrackerCore  # type: ignore
    from worlds import AutoWorld

    class RelayTrackerTab(BoxLayout):
        """Tab that tracks each relayed slot using TrackerCore."""

        def __init__(self, mctx: Any, **kwargs: Any) -> None:
            super().__init__(orientation="vertical", **kwargs)
            self.mctx = mctx
            # Keep cores per slot
            self.cores: dict[str, Any] = {}
            self.status_label = MDLabel(text="Relay Tracker – tracking relayed slots", halign="center", size_hint_y=None, height=40)
            self.add_widget(self.status_label)

            # Controls
            ctrl = BoxLayout(orientation="horizontal", size_hint_y=None, height=36, spacing=4)
            refresh_btn = MDButton(MDButtonText(text="Refresh"), style="filled")
            refresh_btn.bind(on_release=lambda *_: self.refresh_all())
            ctrl.add_widget(refresh_btn)
            clear_btn = MDButton(MDButtonText(text="Clear"), style="filled")
            clear_btn.bind(on_release=lambda *_: self.clear_all())
            ctrl.add_widget(clear_btn)
            self.add_widget(ctrl)

            scroll = ScrollView(size_hint=(1, 1))
            self.grid = GridLayout(cols=1, spacing=4, size_hint_y=None, padding=8)
            self.grid.bind(minimum_height=self.grid.setter("height"))
            scroll.add_widget(self.grid)
            self.add_widget(scroll)

            # Register for ctx callbacks
            mctx.relay_tracker_tab = self
            self.refresh_all()

        def clear_all(self) -> None:
            self.cores.clear()
            self.grid.clear_widgets()
            self.status_label.text = "Relay Tracker – cleared"

        def refresh_all(self) -> None:
            self.grid.clear_widgets()
            relays = getattr(self.mctx, "relays", {})
            if not relays:
                self.grid.add_widget(MDLabel(text="No relays connected yet. Use Proxy tab to connect.", halign="left", size_hint_y=None, height=28))
                self.status_label.text = f"Relay Tracker – 0 relay(s)"
                return
            self.status_label.text = f"Relay Tracker – {len(relays)} relay(s)"
            for slot in sorted(relays.keys()):
                relay = relays[slot]
                core = self.cores.get(slot)
                # Lazily init core on first refresh for this slot
                if core is None:
                    try:
                        core = TrackerCore(logging.getLogger(f"RelayTracker:{slot}"), False, False)
                        # Mirror slot params from relay
                        game = getattr(relay, "game", "") or getattr(relay, "real_game", "") or self.mctx.real_slots.get(slot, "")
                        slot_id = getattr(relay, "slot", None)
                        team = getattr(relay, "team", getattr(self.mctx, "team", 0))
                        core.set_slot_params(game, slot_id, slot, team)
                        # Try to init with world class and relay's slot_data if available
                        slot_data = getattr(relay, "slot_data", None)
                        if slot_data is None:
                            # Try stored_data cache for slot_data? fall back to empty
                            slot_data = {}
                        world_cls = AutoWorld.AutoWorldRegister.world_types.get(game)
                        if world_cls is not None:
                            try:
                                core.initalize_tracker_core(world_cls, slot_data if isinstance(slot_data, dict) else {})
                            except Exception as e:
                                logger.debug("RelayTracker init failed for %s: %s", slot, e)
                        self.cores[slot] = core
                    except Exception as exc:
                        self.grid.add_widget(MDLabel(text=f"{slot}: Tracker init failed: {exc}", halign="left", size_hint_y=None, height=24))
                        continue

                # Feed relay data into core
                try:
                    missing = getattr(relay, "missing_locations", set())
                    if isinstance(missing, set):
                        core.set_missing_locations(set(missing))
                    items = getattr(relay, "items_received", [])
                    # items_received may be NetUtils.NetworkItem list
                    core.set_items_received(list(items) if items else [])
                    # hints
                    team = getattr(relay, "team", 0)
                    slot_id = getattr(relay, "slot", 0)
                    hints = {}
                    try:
                        sd = getattr(relay, "stored_data", {})
                        hk = f"_read_hints_{team}_{slot_id}"
                        if hk in sd:
                            from NetUtils import HintStatus
                            hints = {h["location"]: h["status"] for h in sd[hk] if h["status"] not in [HintStatus.HINT_FOUND, HintStatus.HINT_AVOID]}
                    except Exception:
                        hints = {}
                    core.set_hints(hints)
                    state = core.updateTracker()
                    # Render
                    self.grid.add_widget(MDLabel(text=f"── {slot} [{core.game or '?'}] ──", halign="left", size_hint_y=None, height=28))
                    if getattr(core, "tracker_disabled", False):
                        self.grid.add_widget(MDLabel(text="  (UT disabled for this world)", halign="left", size_hint_y=None, height=24))
                        continue
                    # Show counts
                    self.grid.add_widget(MDLabel(text=f"  Locations: {len(getattr(relay, 'checked_locations', []))}/{getattr(relay, 'total_locations', '?')} checked | In logic: {len(state.in_logic_locations)} | Glitched: {len(state.glitched_locations)} | Hinted: {len(state.hinted_locations)}", halign="left", size_hint_y=None, height=24))
                    # Show readable locations (first few)
                    readable = getattr(state, "readable_locations", [])[:10]
                    for line in readable:
                        self.grid.add_widget(MDLabel(text=f"    • {line}", halign="left", size_hint_y=None, height=22))
                    if len(getattr(state, "readable_locations", [])) > 10:
                        self.grid.add_widget(MDLabel(text=f"    ... and {len(state.readable_locations)-10} more", halign="left", size_hint_y=None, height=22))
                except Exception as exc:
                    self.grid.add_widget(MDLabel(text=f"{slot}: update failed: {exc}", halign="left", size_hint_y=None, height=24))

        def on_relay_update(self, slot: str) -> None:
            """Refresh the tab when a relay updates."""
            try:
                self.refresh_all()
            except Exception:
                pass

    return RelayTrackerTab(ctx)
