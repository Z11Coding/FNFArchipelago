"""Shuffle-based fill retry algorithm for super-generator"""

import logging
import random
from typing import List, Callable, Optional
from BaseClasses import Item, Location, MultiWorld, CollectionState
from Fill import fill_restrictive, FillError


def shuffle_and_retry(multiworld: MultiWorld,
                     locations: List[Location],
                     item_pool: List[Item],
                     max_attempts: int = 5,
                     logging_level: str = "informative") -> None:
    """
    Attempt to fill the multiworld by shuffling the item pool multiple times.
    
    :param multiworld: The multiworld to fill
    :param locations: Locations to fill (will be mutated)
    :param item_pool: Items to place (will be mutated)
    :param max_attempts: Maximum shuffle attempts (1-50)
    :param logging_level: How verbose the logging should be
    :raises FillError: If all shuffle attempts fail
    """
    logger = logging.getLogger()

    if logging_level in ("informative", "detailed"):
        logger.info(f"[Super-Generator] Starting shuffle recovery with {max_attempts} attempts...")

    for attempt in range(1, max_attempts + 1):
        try:
            # Create copies to avoid mutating on failed attempts
            locations_copy = locations.copy()
            item_pool_copy = item_pool.copy()

            # Shuffle the item pool
            multiworld.random.shuffle(item_pool_copy)

            if logging_level == "detailed":
                logger.info(f"[Super-Generator] Shuffle attempt {attempt}/{max_attempts}")

            # Try to fill with shuffled pool
            fill_restrictive(
                multiworld,
                multiworld.state,
                locations_copy,
                item_pool_copy,
                single_player_placement=False,
                lock=False,
                swap=True,
                allow_partial=False
            )

            # Success! Update the original lists with filled state
            locations[:] = locations_copy
            item_pool[:] = item_pool_copy

            if logging_level in ("informative", "detailed"):
                logger.info(f"[Super-Generator] Shuffle recovery succeeded on attempt {attempt}/{max_attempts}")

            return

        except FillError as e:
            if logging_level == "detailed":
                logger.debug(f"[Super-Generator] Shuffle attempt {attempt}/{max_attempts} failed")
            continue

    # All attempts exhausted
    raise FillError(f"[Super-Generator] Shuffle recovery failed after {max_attempts} attempts. "
                   "Please try Cherry-Pick or increase attempt limit.", multiworld=multiworld)
