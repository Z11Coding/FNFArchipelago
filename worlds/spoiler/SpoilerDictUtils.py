"""
Utility functions for working with SpoilerDict in existing worlds.

Provides helpers for:
- Converting existing dicts to SpoilerDict
- Modifying already-loaded worlds to use spoiler protection
- Validating spoiler data integrity
- Debugging spoiler labels
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from .SpoilerDict import SpoilerDict

logger = logging.getLogger("SpoilerDict Utils")


def batch_convert_dicts(source_dict: dict, key_list: Optional[List[str]] = None) -> dict:
    """
    Recursively find and convert dicts in a structure to SpoilerDict.
    
    Useful for converting complex nested data structures.
    
    Args:
        source_dict: The dict to scan and convert
        key_list: Optional list of keys to specifically convert
                 If None, converts all dicts at top level
    
    Returns:
        New dict with converted SpoilerDicts
    
    Example:
        original = {
            "locations": {"secret_1": "item_a", "secret_2": "item_b"},
            "other": {"data": "value"}
        }
        converted = batch_convert_dicts(original, key_list=["locations"])
        # Now original["locations"] is a SpoilerDict
    """
    result = dict(source_dict)
    
    if key_list:
        # Convert specific keys
        for key in key_list:
            if key in result and isinstance(result[key], dict) and not isinstance(result[key], SpoilerDict):
                result[key] = SpoilerDict.from_dict(result[key])
                logger.debug(f"Converted dict at '{key}' to SpoilerDict")
    else:
        # Convert all dict values at top level
        for key, value in result.items():
            if isinstance(value, dict) and not isinstance(value, SpoilerDict):
                result[key] = SpoilerDict.from_dict(value)
                logger.debug(f"Converted dict at '{key}' to SpoilerDict")
    
    return result


def inject_default_labels(spoiler_dict: SpoilerDict, prefix: str = "???") -> None:
    """
    Inject default spoiler-free labels into a SpoilerDict.
    
    Useful for ensuring all keys have labels when labels weren't explicitly set.
    
    Args:
        spoiler_dict: The SpoilerDict to modify in place
        prefix: The prefix for generated labels (default: "???")
    
    Example:
        sd = SpoilerDict({"a": 1, "b": 2})
        inject_default_labels(sd, prefix="Hidden")
        # Now labels are "Hidden", "Hidden_1", etc
    """
    revealed_keys = spoiler_dict.revealed_keys()
    label_count = 0
    
    for real_key in revealed_keys:
        current_label = spoiler_dict.get_label(real_key)
        
        # Only set label if it's still the default generic one
        if current_label in ["???", "???_0"] or current_label.startswith("???_"):
            if label_count == 0:
                new_label = prefix
            else:
                new_label = f"{prefix}_{label_count}"
            
            spoiler_dict.set_label(real_key, new_label)
            label_count += 1
            logger.debug(f"Set label for '{real_key}': {new_label}")


def validate_spoiler_dict(spoiler_dict: SpoilerDict) -> Tuple[bool, List[str]]:
    """
    Validate a SpoilerDict for common issues.
    
    Returns:
        Tuple of (is_valid, list_of_issues)
    
    Checks for:
    - Duplicate labels (multiple keys with same label)
    - Missing labels (keys without labels)
    - Label/key count mismatch
    """
    issues = []
    
    real_keys = spoiler_dict.revealed_keys()
    labels = {}
    
    # Check for duplicates and missing labels
    for real_key in real_keys:
        label = spoiler_dict.get_label(real_key)
        
        if not label:
            issues.append(f"Key '{real_key}' has no label")
        else:
            if label in labels:
                issues.append(f"Duplicate label '{label}' for keys '{labels[label]}' and '{real_key}'")
            else:
                labels[label] = real_key
    
    # Check count mismatch
    if len(labels) != len(real_keys):
        issues.append(f"Label count ({len(labels)}) doesn't match key count ({len(real_keys)})")
    
    is_valid = len(issues) == 0
    
    if is_valid:
        logger.info(f"SpoilerDict validation passed: {len(real_keys)} keys, {len(labels)} unique labels")
    else:
        logger.warning(f"SpoilerDict validation found {len(issues)} issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    
    return is_valid, issues


def print_spoiler_dict_debug_info(spoiler_dict: SpoilerDict, 
                                   title: str = "SpoilerDict Debug Info") -> None:
    """
    Print debug information about a SpoilerDict.
    
    Useful for development and troubleshooting.
    
    Args:
        spoiler_dict: The SpoilerDict to inspect
        title: Title for the debug output
    """
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    
    real_keys = spoiler_dict.revealed_keys()
    print(f"Total keys: {len(real_keys)}")
    print(f"\nKey -> Label Mapping:")
    for real_key in real_keys:
        label = spoiler_dict.get_label(real_key)
        value = spoiler_dict[real_key]
        print(f"  '{real_key}' -> '{label}' = {repr(value)}")
    
    print(f"\nSpoiler-free view (what network will see):")
    for spoiler_key, value in spoiler_dict.items():
        print(f"  '{spoiler_key}': {repr(value)}")
    
    is_valid, issues = validate_spoiler_dict(spoiler_dict)
    print(f"\nValidation: {'PASSED' if is_valid else 'FAILED'}")
    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
    
    print(f"{'='*60}\n")


def compare_spoiler_dicts(dict1: SpoilerDict, dict2: SpoilerDict) -> Dict[str, Any]:
    """
    Compare two SpoilerDicts and report differences.
    
    Returns:
        Dict with comparison results
    """
    result = {
        "are_equal": dict1 == dict2,
        "keys_equal": dict1.revealed_keys() == dict2.revealed_keys(),
        "only_in_first": dict1.revealed_keys() - dict2.revealed_keys(),
        "only_in_second": dict2.revealed_keys() - dict1.revealed_keys(),
        "different_values": {},
        "different_labels": {}
    }
    
    # Check values and labels for common keys
    common_keys = dict1.revealed_keys() & dict2.revealed_keys()
    for key in common_keys:
        if dict1[key] != dict2[key]:
            result["different_values"][key] = {
                "first": dict1[key],
                "second": dict2[key]
            }
        
        if dict1.get_label(key) != dict2.get_label(key):
            result["different_labels"][key] = {
                "first": dict1.get_label(key),
                "second": dict2.get_label(key)
            }
    
    return result


def merge_spoiler_dicts(base: SpoilerDict, *others: SpoilerDict) -> SpoilerDict:
    """
    Merge multiple SpoilerDicts into one.
    
    Later dicts override earlier ones. Labels from the first occurrence are used.
    
    Args:
        base: The base SpoilerDict to merge into
        *others: Additional SpoilerDicts to merge
    
    Returns:
        New merged SpoilerDict
    """
    merged_data = dict(base.revealed_items())
    merged_labels = dict(base._key_labels)
    
    for other in others:
        for real_key, value in other.revealed_items():
            merged_data[real_key] = value
            if real_key not in merged_labels and real_key in other._key_labels:
                merged_labels[real_key] = other._key_labels[real_key]
    
    return SpoilerDict(real_data=merged_data, key_labels=merged_labels)


def get_spoiler_json_preview(spoiler_dict: SpoilerDict) -> str:
    """
    Get a preview of what the JSON serialization will look like.
    
    Shows what the network will transmit (spoiler-free labels as keys).
    
    Args:
        spoiler_dict: The SpoilerDict to preview
    
    Returns:
        JSON string representation
    """
    import json
    
    # JSON serialization will use the spoiler-free labels
    json_dict = dict(spoiler_dict.items())
    return json.dumps(json_dict, indent=2)


def create_reverse_label_lookup(spoiler_dict: SpoilerDict) -> Dict[str, str]:
    """
    Create a reverse mapping from spoiler-free labels to real keys.
    
    Useful for client-side reference.
    
    Args:
        spoiler_dict: The SpoilerDict to create reverse lookup for
    
    Returns:
        Dict mapping spoiler_free_label -> real_key
    """
    return {
        label: real_key
        for real_key, label in spoiler_dict._key_labels.items()
    }


__all__ = [
    'batch_convert_dicts',
    'inject_default_labels',
    'validate_spoiler_dict',
    'print_spoiler_dict_debug_info',
    'compare_spoiler_dicts',
    'merge_spoiler_dicts',
    'get_spoiler_json_preview',
    'create_reverse_label_lookup',
]
