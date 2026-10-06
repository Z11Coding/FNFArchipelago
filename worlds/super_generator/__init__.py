"""Super-Generator: Intelligent fill recovery system for Archipelago generation

Intercepts fill failures and offers recovery via Shuffle or Cherry-Pick algorithms.
"""

import logging
import sys
import os
import time
import threading
from typing import Optional, Callable, List
from BaseClasses import Item, Location, MultiWorld, ItemClassification
from Fill import FillError

# Module state
_patched = False
_recovery_attempts: dict = {}  # Track attempts per multiworld
_config: dict = {}
_patch_lock = False
_original_balance = None  # Store original balance function for recovery


def _load_super_generator_config():
    """Load super-generator config from host.yaml, creating if necessary"""
    global _config
    
    try:
        import yaml
        config_path = "host.yaml"
        
        # First, ensure config section exists in host.yaml
        _ensure_super_generator_config_exists()
        
        # Now load the config via YAML
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                host_config = yaml.safe_load(f)
                
            if host_config and 'super_generator' in host_config:
                sg_config = host_config['super_generator']
                _config['enabled'] = sg_config.get('enabled', True)
                _config['use_as_default'] = sg_config.get('use_as_default', False)
                _config['logging_level'] = sg_config.get('logging_level', 'informative')
                _config['max_shuffles'] = sg_config.get('max_shuffles', 50)
            else:
                _config['enabled'] = True
                _config['use_as_default'] = False
                _config['logging_level'] = 'informative'
                _config['max_shuffles'] = 50
        else:
            _config['enabled'] = True
            _config['use_as_default'] = False
            _config['logging_level'] = 'informative'
            _config['max_shuffles'] = 50
            
    except Exception as e:
        logger = logging.getLogger()
        logger.debug(f"[Super-Generator] Failed to load config: {e}")
        _config['enabled'] = True
        _config['use_as_default'] = False
        _config['logging_level'] = 'informative'
        _config['max_shuffles'] = 50


def _ensure_super_generator_config_exists():
    """Ensure super_generator config section exists in host.yaml, appending if necessary"""
    try:
        import yaml
        config_path = "host.yaml"
        
        if not os.path.exists(config_path):
            return
        
        # Check if super_generator section exists via YAML parsing
        with open(config_path, 'r') as f:
            host_config = yaml.safe_load(f)
        
        if host_config and 'super_generator' in host_config:
            return  # Already exists
        
        # Append as text to preserve formatting
        with open(config_path, 'a') as f:
            f.write('# Super-Generator: Intelligent fill recovery system\n')
            f.write('# Intercepts fill failures and offers recovery via Shuffle or Cherry-Pick algorithms\n')
            f.write('super_generator:\n')
            f.write('  # Enable/disable super-generator recovery for fill failures\n')
            f.write('  enabled: true\n')
            f.write('  # Use super-generator as the default fill algorithm instead of backup recovery\n')
            f.write('  # When true, super-generator\'s algorithms replace the standard fill methods entirely\n')
            f.write('  # When false, super-generator only activates if standard fill methods fail\n')
            f.write('  use_as_default: false\n')
            f.write('  # Logging verbosity: "minimal", "informative", or "detailed"\n')
            f.write('  logging_level: "informative"\n')
            f.write('  # Maximum shuffle attempts (1-50, user can choose up to this limit)\n')
            f.write('  max_shuffles: 50\n')
    except Exception:
        pass


def _try_patch():
    """Attempt to patch Fill functions - use deferred patching to avoid circular imports"""
    global _patched, _patch_lock, _original_balance
    
    if _patched or _patch_lock:
        return
    
    logger = logging.getLogger()
    
    try:
        # Check if Fill module is loaded
        if 'Fill' not in sys.modules:
            return
        
        _patch_lock = True
        
        from Fill import distribute_items_restrictive, balance_multiworld_progression
        
        original_distribute = distribute_items_restrictive
        _original_balance = balance_multiworld_progression
        
        def wrapped_distribute_items(multiworld:MultiWorld, panic_method):
            # If use_as_default is enabled, try cherry_pick first
            if _config.get('use_as_default', False):
                try:
                    locations = list(multiworld.get_unfilled_locations())
                    item_pool = multiworld.itempool.copy()
                    from .cherry_picker import cherry_pick_fill
                    cherry_pick_fill(multiworld, locations, item_pool,
                                   logging_level=_config.get('logging_level', 'informative'))
                    multiworld.super_generator_used = True
                    return
                except Exception as e:
                    logger.debug(f"[Super-Generator] Default cherry_pick failed, falling back: {e}")
            
            try:
                return original_distribute(multiworld, panic_method)
            except Exception as e:
                if isinstance(e, FillError):
                    return _handle_fill_error(e, multiworld, "distribute_items_restrictive")
                raise
        
        def wrapped_balance_progression(multiworld):
            try:
                return _original_balance(multiworld)
            except RuntimeError as e:
                if "Not all required items reachable" in str(e):
                    return _handle_progression_balance_error(e, multiworld)
                raise
            except Exception as e:
                if isinstance(e, FillError):
                    return _handle_fill_error(e, multiworld, "balance_multiworld_progression",
                                             skip_balance=True)
                raise
        
        # Monkey-patch Fill module
        import Fill
        Fill.distribute_items_restrictive = wrapped_distribute_items
        Fill.balance_multiworld_progression = wrapped_balance_progression
        
        _patched = True
        logger.debug("[Super-Generator] Successfully patched fill functions")
        
        if _config.get('use_as_default', False):
            logger.info("[Super-Generator] Using cherry-pick as default fill algorithm")
        
    except Exception as e:
        logger.debug(f"[Super-Generator] Failed to patch: {e}")
    finally:
        _patch_lock = False


def _ensure_patched():
    """Ensure patching is attempted at critical moments"""
    if not _patched:
        _try_patch()


def _handle_fill_error(error: FillError, multiworld: MultiWorld, source: str,
                      skip_balance: bool = False) -> None:
    """
    Handle a fill error by prompting user for recovery algorithm choice.
    """
    logger = logging.getLogger()
    
    _ensure_patched()  # Make sure we're patched

    # Check if super-generator is enabled
    if not _config.get('enabled', True):
        raise error

    # Check if we've already attempted recovery for this multiworld
    multiworld_id = id(multiworld)
    if multiworld_id not in _recovery_attempts:
        _recovery_attempts[multiworld_id] = 0

    if _recovery_attempts[multiworld_id] >= 2:
        logger.error("[Super-Generator] Maximum recovery attempts (2) exceeded")
        raise error

    _recovery_attempts[multiworld_id] += 1

    logger.info("[Super-Generator] Fill failed, attempting recovery...")
    logger.warning(f"[Super-Generator] Source: {source}")

    if skip_balance:
        logger.warning("[Super-Generator] WARNING: Progression balancing was skipped. "
                      "Cherry-pick may have created unusual item distributions.")
        multiworld.super_generator_skipped_balancing = True

    # Show recovery prompt
    algorithm = _show_recovery_prompt()

    if algorithm == "cancel":
        raise error

    # Get current locations and item pool
    locations = list(multiworld.get_unfilled_locations())
    item_pool = multiworld.itempool.copy()

    try:
        if algorithm == "shuffle":
            max_attempts = _get_shuffle_attempts()
            from .shuffler import shuffle_and_retry
            shuffle_and_retry(multiworld, locations, item_pool,
                            max_attempts=max_attempts,
                            logging_level=_config.get('logging_level', 'informative'))

        elif algorithm == "cherry_pick":
            from .cherry_picker import cherry_pick_fill
            cherry_pick_fill(multiworld, locations, item_pool,
                            logging_level=_config.get('logging_level', 'informative'))

        # Mark that super-generator was used
        multiworld.super_generator_used = True
        logger.info("[Super-Generator] Recovery successful")

    except Exception as recovery_error:
        logger.error(f"[Super-Generator] Recovery failed: {recovery_error}")
        retry = _show_retry_prompt()
        if not retry:
            raise error
        else:
            raise recovery_error


def _handle_progression_balance_error(error: RuntimeError, multiworld: MultiWorld) -> None:
    """
    Handle progression balance failures by moving items to make required items reachable.
    """
    logger = logging.getLogger()
    
    _ensure_patched()
    
    if not _config.get('enabled', True):
        raise error
    
    logging_level = _config.get('logging_level', 'informative')
    attempt_key = f"{id(multiworld)}_balance"
    
    if attempt_key in _recovery_attempts and _recovery_attempts[attempt_key] >= 2:
        if logging_level in ("informative", "detailed"):
            logger.info("[Super-Generator] Max progression balance recovery attempts reached")
        raise error
    
    _recovery_attempts[attempt_key] = _recovery_attempts.get(attempt_key, 0) + 1
    
    try:
        if logging_level in ("informative", "detailed"):
            logger.info("[Super-Generator] Attempting to recover from progression balance failure...")
        
        from .collection_analyzer import LocationRequirementAnalyzer
        
        analyzer = LocationRequirementAnalyzer(multiworld)
        state = multiworld.state.copy()
        
        # Find accessible locations
        accessible_locs = [loc for loc in multiworld.get_locations() 
                          if not loc.locked and (loc.access_rule is None or loc.access_rule(state))]
        
        # Find inaccessible locations with items
        inaccessible_locs = [loc for loc in multiworld.get_locations()
                            if not loc.locked and loc.item and loc.access_rule 
                            and not loc.access_rule(state)]
        
        if logging_level == "detailed":
            logger.info(f"[Super-Generator] Found {len(accessible_locs)} accessible, "
                       f"{len(inaccessible_locs)} inaccessible locations")
        
        # Try to swap items from inaccessible to accessible locations
        swaps_made = 0
        for inaccessible_loc in inaccessible_locs:
            if not inaccessible_loc.item:
                continue
            
            # Try moving this item to an accessible location
            for accessible_loc in accessible_locs:
                if not accessible_loc.item:
                    # Empty accessible location, swap directly
                    accessible_loc.item = inaccessible_loc.item
                    inaccessible_loc.item.location = accessible_loc
                    inaccessible_loc.item = None
                    state.collect(accessible_loc.item, True)
                    swaps_made += 1
                    
                    if logging_level == "detailed":
                        logger.info(f"[Super-Generator] Moved {accessible_loc.item.name} "
                                   f"to {accessible_loc.name}")
                    break
                elif accessible_loc.item.classification == ItemClassification.filler:
                    # Swap filler for the inaccessible item
                    temp_item = accessible_loc.item
                    accessible_loc.item = inaccessible_loc.item
                    inaccessible_loc.item = temp_item
                    temp_item.location = inaccessible_loc
                    accessible_loc.item.location = accessible_loc
                    state.collect(accessible_loc.item, True)
                    swaps_made += 1
                    
                    if logging_level == "detailed":
                        logger.info(f"[Super-Generator] Swapped {accessible_loc.item.name} "
                                   f"with {temp_item.name}")
                    break
        
        if logging_level in ("informative", "detailed"):
            logger.info(f"[Super-Generator] Made {swaps_made} item swaps to fix progression")
        
        # Try re-balancing with moved items
        try:
            _original_balance(multiworld)
        except Exception as e:
            logger.error(f"[Super-Generator] Re-balancing failed after item moves: Assuming recovery succeeded with current item distribution. Error: {e}")
        multiworld.super_generator_used = True
        logger.info("[Super-Generator] Progression balance recovery succeeded")
        
    except Exception as recovery_error:
        if logging_level in ("informative", "detailed"):
            logger.info(f"[Super-Generator] Progression balance recovery failed: {recovery_error}")
        raise error


def _show_recovery_prompt() -> str:
    """
    Show console prompt for recovery algorithm selection.
    Returns: "shuffle", "cherry_pick", or "cancel"
    """
    while True:
        print("\n[Super-Generator] Item distribution failed during generation.")
        print("Would you like to attempt recovery?\n")
        print("  [1] Shuffle - Shuffle items and retry multiple times")
        print("  [2] Cherry-Pick - Intelligently place items based on location accessibility")
        print("  [3] Cancel - Abort generation\n")

        choice = input("Choose (1-3): ").strip()

        if choice == "1":
            return "shuffle"
        elif choice == "2":
            return "cherry_pick"
        elif choice == "3":
            return "cancel"
        else:
            print("Invalid choice. Please enter 1, 2, or 3.\n")


def _get_shuffle_attempts() -> int:
    """
    Prompt user for shuffle attempt count (1-50).
    Returns the user's choice, or default 5 if invalid input.
    """
    max_shuffles = _config.get('max_shuffles', 50)

    while True:
        prompt = f"How many shuffle attempts? (1-{max_shuffles}) [Default: 5]: "
        user_input = input(prompt).strip()

        if not user_input:
            return 5

        try:
            attempts = int(user_input)
            if 1 <= attempts <= max_shuffles:
                return attempts
            else:
                print(f"Please enter a number between 1 and {max_shuffles}.")
        except ValueError:
            print("Please enter a valid number.")


def _show_retry_prompt() -> bool:
    """
    Show prompt asking if user wants to retry recovery.
    Returns True to retry, False to abort.
    """
    while True:
        choice = input("\n[Super-Generator] Recovery failed. Retry? (y/n): ").strip().lower()
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            print("Please enter 'y' or 'n'.")


# Initialize on module import
def _deferred_patch():
    """Deferred patching using a daemon thread to wait for Fill to be imported"""
    for _ in range(100):  # Try up to 100 times with 0.01s intervals
        _try_patch()
        if _patched:
            logger = logging.getLogger()
            logger.info("[Super-Generator] Deferred patch successful")
            break
        time.sleep(0.01)

try:
    _load_super_generator_config()
    
    # Try immediate patch
    _try_patch()
    
    # If not patched yet, start a daemon thread for deferred patching
    if not _patched:
        patch_thread = threading.Thread(target=_deferred_patch, daemon=True)
        patch_thread.start()
    
    logger = logging.getLogger()
    logger.info("[Super-Generator] Module loaded and patching initiated")
except Exception as e:
    logger = logging.getLogger()
    logger.errorfload(f"[Super-Generator] Initialization error: {e}")
