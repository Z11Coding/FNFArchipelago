"""
YAML Recreator - Detects randomization in YAML and generates format metadata.

The YAML representation PRESERVES the actual randomization structure:
- Lists stay as lists (random choice among items)
- Dicts with numeric values stay as dicts (weighted random choice)
- Scalars stay as scalars (no randomization)

String patterns like "random", "random-low", etc. are only for Range options.

Format types detected:
- "basic": Single game with scalar options
- "weighted": Weighted game selection (dict with numeric weights)
- "multi-game": Multiple games or game selections

Note: plando_items and plando_connections can appear in any format type,
they don't define the format themselves.

The metadata identifies which fields use randomization and how.
"""

from typing import Dict, Any, List, Tuple, Set
import yaml as yaml_module
import re


def is_weighted_dict(value: Any) -> bool:
    """Check if a value is a weighted dict (dict with all numeric values)."""
    if not isinstance(value, dict) or not value:
        return False
    return all(isinstance(v, (int, float)) for v in value.values())


def is_random_list(value: Any) -> bool:
    """Check if a value is a random choice list."""
    return isinstance(value, list) and len(value) > 0


def is_range_pattern(value: Any) -> bool:
    """Check if value is a string range pattern like 'random', 'random-low', etc."""
    if not isinstance(value, str):
        return False
    patterns = {
        "random",
        "random-low", "random-middle", "random-high",
        # Dynamic patterns like random-range-10-20
    }
    if value in patterns:
        return True
    # Check for random-range-* patterns
    if re.match(r'^random-range-(low|middle|high)?-?\d+-\d+$', value):
        return True
    return False


def detect_randomization_in_value(key: str, value: Any) -> Dict[str, Any]:
    """Detect if a value uses randomization and return metadata about it.
    
    Returns dict with:
    - is_randomized: bool
    - randomization_type: "list", "weighted_dict", "range_pattern", or None
    - details: additional info (e.g., number of choices)
    """
    if is_random_list(value):
        return {
            "is_randomized": True,
            "randomization_type": "random_list",
            "option_count": len(value)
        }
    elif is_weighted_dict(value):
        total_weight = sum(value.values())
        return {
            "is_randomized": True,
            "randomization_type": "weighted_dict",
            "option_count": len(value),
            "total_weight": total_weight
        }
    elif is_range_pattern(value):
        return {
            "is_randomized": True,
            "randomization_type": "range_pattern",
            "pattern": value
        }
    else:
        return {
            "is_randomized": False,
            "randomization_type": None
        }


def collect_randomization_metadata_recursive(data: Any, path: str = "") -> Dict[str, Any]:
    """Recursively collect metadata about all randomization found in YAML.
    
    Returns dict mapping field paths to randomization info.
    """
    metadata = {}
    
    if isinstance(data, dict):
        for key, value in data.items():
            field_path = f"{path}.{key}" if path else key
            
            # Check if this field is randomized
            rand_info = detect_randomization_in_value(key, value)
            if rand_info["is_randomized"]:
                metadata[field_path] = rand_info
            
            # Recurse into nested dicts
            if isinstance(value, dict) and not is_weighted_dict(value):
                # Only recurse if it's not a weighted dict (weighted dicts shouldn't have nested structures)
                nested = collect_randomization_metadata_recursive(value, field_path)
                metadata.update(nested)
    
    return metadata


def detect_yaml_format_in_doc(yaml_dict: Dict[str, Any]) -> str:
    """Detect format type for a single YAML document.
    
    Returns: "basic", "weighted", or "multi-game"
    
    Note: plando_items and plando_connections can be present in any format type,
    they don't define the format themselves.
    """
    if not isinstance(yaml_dict, dict):
        return "basic"
    
    # Check for weighted game selection
    if "game" in yaml_dict:
        game_val = yaml_dict["game"]
        if is_weighted_dict(game_val):
            # Dict with weights = weighted random
            return "weighted"
        elif is_random_list(game_val):
            # List of games = multi-game
            return "multi-game"
        elif isinstance(game_val, str):
            # Single game selection
            return "basic"
    
    # Check for multiple game sections (ignoring plando keys)
    game_sections = {k for k in yaml_dict.keys() 
                     if isinstance(yaml_dict[k], dict) and k not in ('plando_items', 'plando_connections')}
    if len(game_sections) > 1:
        return "multi-game"
    
    return "basic"


def detect_randomization_patterns_in_value(value: Any) -> List[str]:
    """Detect randomization pattern types in a value.
    
    Returns list of detected pattern types.
    """
    patterns = []
    
    if is_random_list(value):
        patterns.append("random_list")
    elif is_weighted_dict(value):
        patterns.append("weighted_dict")
    elif is_range_pattern(value):
        patterns.append("range_pattern")
    
    return patterns


def collect_randomization_types_recursive(data: Any) -> Set[str]:
    """Recursively collect all randomization types found in YAML structure."""
    found_types = set()
    
    if isinstance(data, dict):
        for key, value in data.items():
            patterns = detect_randomization_patterns_in_value(value)
            found_types.update(patterns)
            # Recurse into nested dicts
            if isinstance(value, dict) and not is_weighted_dict(value):
                found_types.update(collect_randomization_types_recursive(value))
    elif isinstance(data, list):
        for item in data:
            patterns = detect_randomization_patterns_in_value(item)
            found_types.update(patterns)
            # Recurse if item is a dict
            if isinstance(item, dict):
                found_types.update(collect_randomization_types_recursive(item))
    
    return found_types


def recreate_yaml_with_options(yaml_dict: Dict[str, Any], selected_values: Dict[str, Any]) -> str:
    """Recreate YAML from the dict and show what values were selected.
    
    Args:
        yaml_dict: The original YAML data (with lists/dicts for randomization)
        selected_values: Dict of option_name -> the actual value that was selected
    
    Returns:
        YAML string with comments showing what was randomly selected
    """
    try:
        result = _annotate_selections(yaml_dict, selected_values)
        yaml_str = yaml_module.dump(result, default_flow_style=False)
        return yaml_str
    except Exception as e:
        import logging
        logger = logging.getLogger("YAML Embedder")
        logger.debug(f"YAML recreation failed: {e}", exc_info=True)
        # Return original dict as YAML if recreation fails
        return yaml_module.dump(yaml_dict, default_flow_style=False)


def _annotate_selections(data: Any, selected_values: Dict[str, Any], path: str = "") -> Any:
    """Recursively process YAML and add comments about selections.
    
    Note: YAML comments in PyYAML require using custom representers, which is complex.
    For now, we'll return the data structure with metadata embedded.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            field_path = key if not path else f"{path}.{key}"
            
            # Check if this field had a selection made
            if field_path in selected_values:
                selected = selected_values[field_path]
                rand_info = detect_randomization_in_value(key, value)
                
                # Store both the data and the selection info
                # In real YAML output, we'd add a comment
                result[key] = {
                    "_value": selected,
                    "_randomization_info": rand_info,
                    "_original": value
                }
            elif isinstance(value, dict) and not is_weighted_dict(value):
                # Recurse into nested dicts
                result[key] = _annotate_selections(value, selected_values, field_path)
            else:
                # Keep the value as-is
                result[key] = value
        
        return result
    else:
        return data


def get_randomization_summary(metadata: Dict[str, Any]) -> str:
    """Get a human-readable summary of randomization types found."""
    if not metadata.get("randomization_types"):
        return "No randomization detected"
    
    types_str = ", ".join(sorted(set(metadata["randomization_types"])))
    
    if metadata.get("is_multi_document"):
        return f"Multi-document YAML ({metadata['document_count']} docs) with: {types_str}"
    else:
        fmt = metadata.get("format_type", "unknown")
        return f"{fmt.title()} YAML with: {types_str}"


def validate_yaml_format_metadata(metadata: Dict[str, Any]) -> bool:
    """Validate that format metadata has all required fields."""
    required_fields = {
        "format_type",
        "format_types_per_document",
        "randomization_types",
        "randomization_metadata",
        "is_multi_document",
        "document_count"
    }
    
    return all(field in metadata for field in required_fields)


def split_multi_yaml(yaml_str: str) -> List[str]:
    """Split multi-document YAML (separated by ---) into individual documents."""
    parts = re.split(r'^---\s*$', yaml_str, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def split_multi_document_yaml(yaml_str: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Split and parse multi-document YAML.
    
    Returns: (list of parsed YAML dicts, list of original YAML strings)
    """
    raw_docs = split_multi_yaml(yaml_str)
    parsed_docs = []
    
    for doc_str in raw_docs:
        if not doc_str:
            continue
        try:
            parsed = yaml_module.safe_load(doc_str)
            parsed_docs.append(parsed)
        except Exception:
            # If parsing fails, keep raw string
            parsed_docs.append({"_raw": doc_str})
    
    return parsed_docs, raw_docs


def generate_format_metadata(yaml_str: str) -> Dict[str, Any]:
    """Generate comprehensive format metadata for a YAML.
    
    Returns dict with:
    - format_type: "basic", "weighted", or "multi-game"
    - format_types_per_document: list of format types if multi-document
    - randomization_types: list of detected randomization types (random_list, weighted_dict, range_pattern)
    - randomization_metadata: detailed info about which fields use randomization
    - is_multi_document: bool
    - document_count: int
    """
    metadata = {
        "format_type": None,
        "format_types_per_document": [],
        "randomization_types": [],
        "randomization_metadata": {},
        "is_multi_document": False,
        "document_count": 1
    }
    
    try:
        # Check if multi-document
        raw_docs = split_multi_yaml(yaml_str)
        
        if len(raw_docs) > 1:
            metadata["is_multi_document"] = True
            metadata["document_count"] = len(raw_docs)
            
            # Parse each document and detect format
            for doc_idx, doc_str in enumerate(raw_docs):
                try:
                    doc_data = yaml_module.safe_load(doc_str)
                    if isinstance(doc_data, dict):
                        fmt = detect_yaml_format_in_doc(doc_data)
                        metadata["format_types_per_document"].append(fmt)
                        
                        # Collect randomization types and metadata
                        rand_types = collect_randomization_types_recursive(doc_data)
                        metadata["randomization_types"].extend(rand_types)
                        
                        # Collect per-field metadata
                        field_metadata = collect_randomization_metadata_recursive(doc_data)
                        if field_metadata:
                            metadata["randomization_metadata"][f"doc{doc_idx}"] = field_metadata
                except Exception:
                    metadata["format_types_per_document"].append("unknown")
            
            # Overall format is multi-document
            metadata["format_type"] = "multi-document"
        else:
            # Single document
            yaml_data = yaml_module.safe_load(yaml_str)
            if isinstance(yaml_data, dict):
                fmt = detect_yaml_format_in_doc(yaml_data)
                metadata["format_type"] = fmt
                
                # Collect randomization types and metadata
                rand_types = collect_randomization_types_recursive(yaml_data)
                metadata["randomization_types"] = sorted(list(rand_types))
                
                # Collect per-field metadata
                field_metadata = collect_randomization_metadata_recursive(yaml_data)
                if field_metadata:
                    metadata["randomization_metadata"] = field_metadata
            else:
                metadata["format_type"] = "basic"
    
    except Exception as e:
        metadata["format_type"] = "unknown"
        metadata["randomization_types"] = []
    
    # Remove duplicates and sort randomization types
    metadata["randomization_types"] = sorted(list(set(metadata["randomization_types"])))
    
    return metadata
