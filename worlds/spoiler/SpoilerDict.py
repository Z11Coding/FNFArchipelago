"""
SpoilerDict - A custom dict that hides sensitive keys behind spoiler-free labels.

When iterating or displaying keys, the dict shows spoiler-free labels.
Normal access via [] and get() still works with the real keys.
Use revealed_keys() to get the original keys.
"""

from typing import Dict, Any, Iterator, Set, Optional, Mapping
import logging

logger = logging.getLogger("SpoilerDict")


class SpoilerDict(dict):
    """
    A dict subclass that shows spoiler-free labels for keys when iterating or displaying.
    
    Normal dict access ([], get()) uses the real keys internally.
    Iteration, keys(), items(), values() show the spoiler-free versions.
    Use revealed_keys() to get the actual keys.
    
    Example:
        sd = SpoilerDict(
            real_data={"secret_location": "cool_item", "another_secret": "gem"},
            key_labels={"secret_location": "Location A", "another_secret": "Location B"}
        )
        
        # Access works normally
        sd["secret_location"]  # Returns "cool_item"
        sd.get("secret_location")  # Returns "cool_item"
        
        # Iteration shows spoiler-free labels
        for key in sd:  # Iterates as "Location A", "Location B"
            print(key, sd[key])  # But sd[key] needs the REAL key!
        
        # Get real keys
        sd.revealed_keys()  # Returns {"secret_location", "another_secret"}
    """
    
    def __init__(self, real_data: Optional[Mapping[str, Any]] = None, 
                 key_labels: Optional[Dict[str, str]] = None,
                 **kwargs):
        """
        Initialize a SpoilerDict.
        
        Args:
            real_data: Dict with real keys and values
            key_labels: Mapping from real_key -> spoiler_free_label
            **kwargs: Additional dict arguments
        """
        # Initialize parent with real data
        if real_data:
            super().__init__(real_data, **kwargs)
        else:
            super().__init__(**kwargs)
        
        # Store the mapping from real keys to spoiler-free labels
        self._key_labels: Dict[str, str] = {}
        
        if key_labels:
            self._key_labels = dict(key_labels)
        else:
            # Generate generic labels if not provided
            for idx, real_key in enumerate(self.keys()):
                if real_key not in self._key_labels:
                    if idx == 0:
                        self._key_labels[real_key] = "???"
                    else:
                        self._key_labels[real_key] = f"???_{idx}"
    
    def revealed_keys(self) -> Set[str]:
        """Get the actual keys (before spoiler-free translation)."""
        return set(dict.keys(self))
    
    def revealed_items(self):
        """Get actual (real_key, value) pairs."""
        return dict.items(self)
    
    def revealed_values(self):
        """Get values (same as normal values, but clearer intent)."""
        return dict.values(self)
    
    def __iter__(self) -> Iterator[str]:
        """Iterate over spoiler-free key labels."""
        real_keys = dict.keys(self)
        for real_key in real_keys:
            yield self._key_labels.get(real_key, real_key)
    
    def keys(self):
        """Return spoiler-free key labels."""
        real_keys = dict.keys(self)
        return [self._key_labels.get(real_key, real_key) for real_key in real_keys]
    
    def items(self):
        """Return (spoiler_free_label, value) pairs."""
        real_keys_list = list(dict.keys(self))
        return [(self._key_labels.get(real_key, real_key), dict.__getitem__(self, real_key)) 
                for real_key in real_keys_list]
    
    def values(self):
        """Return values (same as normal, but for consistency)."""
        return dict.values(self)
    
    def __repr__(self) -> str:
        """Show spoiler-free version in repr."""
        items = ", ".join(f"{repr(label)}: {repr(value)}" 
                         for label, value in self.items())
        return f"{{{items}}}"
    
    def __str__(self) -> str:
        """Show spoiler-free version in str."""
        items = ", ".join(f"{label}: {value}" 
                         for label, value in self.items())
        return f"{{{items}}}"
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value by real key (normal dict behavior)."""
        return dict.get(self, key, default)
    
    def __getitem__(self, key: str) -> Any:
        """Get value by real key (normal dict behavior)."""
        return dict.__getitem__(self, key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Set value with real key."""
        dict.__setitem__(self, key, value)
        # Ensure label exists for new keys
        if key not in self._key_labels:
            idx = len(self._key_labels)
            if idx == 0:
                self._key_labels[key] = "???"
            else:
                self._key_labels[key] = f"???_{idx}"
    
    def __delitem__(self, key: str) -> None:
        """Delete by real key."""
        dict.__delitem__(self, key)
        if key in self._key_labels:
            del self._key_labels[key]
    
    def __contains__(self, key: str) -> bool:
        """Check if real key exists."""
        return dict.__contains__(self, key)
    
    def __eq__(self, other: Any) -> bool:
        """
        Equality check.
        
        Compares the underlying dict data only, not the labels.
        This ensures datapackage comparisons work correctly.
        """
        if isinstance(other, SpoilerDict):
            # Compare actual data, not labels
            return dict.__eq__(self, other)
        elif isinstance(other, dict):
            # Compare with regular dict using actual data
            return dict.__eq__(self, other)
        return False
    
    def __hash__(self) -> int:
        """Hash based on actual data."""
        # Dicts aren't hashable normally, but if needed for some reason
        try:
            return hash(frozenset(dict.items(self)))
        except TypeError:
            return hash(id(self))
    
    def copy(self) -> "SpoilerDict":
        """Create a shallow copy preserving the spoiler labels."""
        return SpoilerDict(
            real_data=dict.copy(self),
            key_labels=self._key_labels.copy()
        )
    
    def update(self, other: Any = None, **kwargs) -> None:
        """Update dict and handle labels for new keys."""
        if other is not None:
            if isinstance(other, dict):
                dict.update(self, other)
                # Add labels for new keys
                for key in other.keys():
                    if key not in self._key_labels:
                        idx = len(self._key_labels)
                        if idx == 0:
                            self._key_labels[key] = "???"
                        else:
                            self._key_labels[key] = f"???_{idx}"
            else:
                # Handle sequence of key-value pairs
                for key, value in other:
                    self[key] = value
        
        if kwargs:
            for key, value in kwargs.items():
                self[key] = value
    
    def set_label(self, real_key: str, label: str) -> None:
        """Set a custom spoiler-free label for a real key."""
        if real_key not in self:
            raise KeyError(f"Key {real_key} not in dict")
        self._key_labels[real_key] = label
    
    def get_label(self, real_key: str) -> str:
        """Get the spoiler-free label for a real key."""
        return self._key_labels.get(real_key, real_key)
    
    def get_revealed_key_for_label(self, label: str) -> Optional[str]:
        """Get the real key that corresponds to a spoiler-free label (reverse lookup)."""
        for real_key, real_label in self._key_labels.items():
            if real_label == label:
                return real_key
        return None
    
    def to_dict(self) -> dict:
        """Convert to a regular dict with spoiler-free labels as keys."""
        return dict(self.items())
    
    @staticmethod
    def from_dict(regular_dict: dict, key_labels: Optional[Dict[str, str]] = None) -> "SpoilerDict":
        """Create a SpoilerDict from a regular dict."""
        return SpoilerDict(real_data=regular_dict, key_labels=key_labels)
