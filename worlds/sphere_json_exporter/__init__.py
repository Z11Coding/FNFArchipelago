from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from BaseClasses import MultiWorld

from Utils import output_path
from worlds.APAPI import build_playthrough_model
from worlds.APAPI.hard_patch import hard_patches


logger = logging.getLogger("SphereJsonExporter")


_patched = False


def _export_sphere_json(multiworld: "MultiWorld") -> None:
    model = build_playthrough_model(multiworld)
    target = Path(output_path(f"AP_{multiworld.seed_name}.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(model.to_json(indent=2), encoding="utf-8")
    logger.info("[SphereJsonExporter] Wrote sphere playthrough JSON: %s", target)


def _main_wrapper(
    next_callable,
    args,
    seed: int | None = None,
    baked_server_options: dict[str, object] | None = None,
):
    result = next_callable(args, seed, baked_server_options)
    if result is not None:
        try:
            from BaseClasses import MultiWorld

            if isinstance(result, MultiWorld):
                _export_sphere_json(result)
            else:
                logger.warning(
                    "[SphereJsonExporter] Main.main returned non-MultiWorld result of type %s",
                    type(result).__name__,
                )
        except Exception as exc:
            logger.warning("[SphereJsonExporter] Failed to export sphere JSON: %s", exc)
    return result


def _patch_main() -> None:
    global _patched
    if _patched:
        return

    for _ in range(240):
        if "Main" in sys.modules:
            try:
                hard_patches.add_wrapper("Main.main", _main_wrapper, load_missing=False)
                _patched = True
            except Exception as exc:
                logger.warning("[SphereJsonExporter] Could not patch Main.main yet: %s", exc)
            return
        time.sleep(0.5)


threading.Thread(target=_patch_main, name="SphereJsonExporter-PatchMain", daemon=True).start()
