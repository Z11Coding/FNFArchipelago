from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
from typing import TYPE_CHECKING

from Utils import output_path
from worlds.APAPI import build_playthrough_model
from worlds.APAPI.hard_patch import register_after_patch

if TYPE_CHECKING:
    from BaseClasses import MultiWorld


logger = logging.getLogger("HydraPlugin")


_patched = False


def _export_hydra_json(multiworld: "MultiWorld") -> None:
    model = build_playthrough_model(multiworld)
    target = Path(output_path(f"AP_{multiworld.seed_name}.hydra.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(model.to_json(indent=2), encoding="utf-8")
    logger.info("[HydraPlugin] Wrote hydra playthrough JSON: %s", target)


def _after_main(
    result,
    args,
    seed: int | None = None,
    baked_server_options: dict[str, object] | None = None,
):
    if result is not None:
        try:
            from BaseClasses import MultiWorld

            if isinstance(result, MultiWorld):
                _export_hydra_json(result)
            else:
                logger.warning(
                    "[HydraPlugin] Main.main returned non-MultiWorld result of type %s",
                    type(result).__name__,
                )
        except Exception as exc:
            logger.warning("[HydraPlugin] Failed to export hydra JSON: %s", exc)
    return result


def _patch_main() -> None:
    global _patched
    if _patched:
        return

    for _ in range(240):
        if "Main" in sys.modules:
            try:
                register_after_patch("Main.main", _after_main, load_missing=False)
                _patched = True
            except Exception as exc:
                logger.warning("[HydraPlugin] Could not patch Main.main yet: %s", exc)
            return
        time.sleep(0.5)


threading.Thread(target=_patch_main, name="HydraPlugin-PatchMain", daemon=True).start()
