"""Data structures for Shortcut Manager."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path
import json


class ShortcutType(Enum):
    """Shortcut execution types."""
    SCRIPT = "script"
    EXECUTABLE = "executable"
    FOLDER = "folder"
    URL = "url"
    FUNCTION = "function"
    WINE = "wine"
    STEAM = "steam"


class LinkType(Enum):
    """Component link types."""
    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass
class Shortcut:
    """Standalone shortcut component."""
    name: str
    shortcut_type: ShortcutType
    target: str
    description: str = ""
    icon: str = "icon"
    args: str = ""
    working_dir: Optional[str] = None
    component_type: str = "MISC"
    metadata: Dict[str, Any] = field(default_factory=dict)
    temp_icon_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "type": self.shortcut_type.value,
            "target": self.target,
            "description": self.description,
            "icon": self.icon,
            "args": self.args,
            "working_dir": self.working_dir,
            "component_type": self.component_type,
            "metadata": self.metadata,
            "temp_icon_path": self.temp_icon_path,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Shortcut":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            shortcut_type=ShortcutType(data["type"]),
            target=data["target"],
            description=data.get("description", ""),
            icon=data.get("icon", "icon"),
            args=data.get("args", ""),
            working_dir=data.get("working_dir"),
            component_type=data.get("component_type", "MISC"),
            metadata=data.get("metadata", {}),
            temp_icon_path=data.get("temp_icon_path"),
        )


@dataclass
class LinkedShortcut:
    """Shortcut linked to an existing component."""
    name: str
    shortcut_type: ShortcutType
    target: str
    target_component: str
    link_type: LinkType
    description: str = ""
    icon: str = "icon"
    args: str = ""
    working_dir: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "type": self.shortcut_type.value,
            "target": self.target,
            "target_component": self.target_component,
            "link_type": self.link_type.value,
            "description": self.description,
            "icon": self.icon,
            "args": self.args,
            "working_dir": self.working_dir,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LinkedShortcut":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            shortcut_type=ShortcutType(data["type"]),
            target=data["target"],
            target_component=data["target_component"],
            link_type=LinkType(data["link_type"]),
            description=data.get("description", ""),
            icon=data.get("icon", "icon"),
            args=data.get("args", ""),
            working_dir=data.get("working_dir"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ShortcutCollection:
    """Collection of shortcuts."""
    shortcuts: List[Shortcut] = field(default_factory=list)
    linked_shortcuts: List[LinkedShortcut] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_shortcut(self, shortcut: Shortcut) -> None:
        """Add a shortcut, replacing if exists."""
        self.shortcuts = [s for s in self.shortcuts if s.name != shortcut.name]
        self.shortcuts.append(shortcut)
    
    def remove_shortcut(self, name: str) -> None:
        """Remove a shortcut by name."""
        self.shortcuts = [s for s in self.shortcuts if s.name != name]
    
    def add_linked_shortcut(self, linked: LinkedShortcut) -> bool:
        """Add linked shortcut, False if duplicate type on component."""
        for existing in self.linked_shortcuts:
            if (existing.target_component == linked.target_component and 
                existing.link_type == linked.link_type and
                existing.name != linked.name):
                return False
        self.linked_shortcuts = [l for l in self.linked_shortcuts if l.name != linked.name]
        self.linked_shortcuts.append(linked)
        return True
    
    def remove_linked_shortcut(self, name: str) -> None:
        """Remove a linked shortcut by name."""
        self.linked_shortcuts = [l for l in self.linked_shortcuts if l.name != name]
    
    def get_shortcut(self, name: str) -> Optional[Shortcut]:
        """Get shortcut by name."""
        for s in self.shortcuts:
            if s.name == name:
                return s
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "shortcuts": [s.to_dict() for s in self.shortcuts],
            "linked_shortcuts": [l.to_dict() for l in self.linked_shortcuts],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShortcutCollection":
        """Deserialize from dictionary."""
        shortcuts = [Shortcut.from_dict(s) for s in data.get("shortcuts", [])]
        linked = [LinkedShortcut.from_dict(l) for l in data.get("linked_shortcuts", [])]
        return cls(
            shortcuts=shortcuts,
            linked_shortcuts=linked,
            metadata=data.get("metadata", {}),
        )
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "ShortcutCollection":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
