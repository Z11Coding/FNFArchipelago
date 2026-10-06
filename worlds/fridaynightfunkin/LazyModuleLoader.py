"""
Lazy Module Loader - Handles deferred importing to support recursive imports.

This module provides a LazyModule class that acts as a proxy for imported modules,
deferring the actual import until the module is first accessed. This helps resolve
circular import issues by allowing modules to reference each other without requiring
them to be fully loaded at the time of the import statement.
"""

import importlib
import inspect
import sys
from typing import Any


class LazyModule:
    """
    A proxy object that defers importing a module until it's actually used.
    
    This class acts as if it were the imported module itself, transparently
    forwarding all attribute accesses to the real module once it's loaded.
    
    Benefits:
    - Resolves circular import dependencies
    - Defers costly imports until needed
    - Provides transparent access to the real module's attributes
    
    Example:
        # Instead of: from .MyModule import SomeClass
        # Use: MyModule = LazyModule(".MyModule")
        # Then access normally: MyModule.SomeClass
    """
    
    def __init__(self, module_name: str):
        """
        Initialize a lazy module loader.
        
        Args:
            module_name: The name of the module to import (e.g., ".MyModule" or "os.path")
        
        The package is automatically detected from the caller's module context,
        so relative imports will work correctly regardless of where LazyModule is used.
        """
        # Use object.__setattr__ to bypass our custom __setattr__
        object.__setattr__(self, '_module_name', module_name)
        object.__setattr__(self, '_module', None)
        object.__setattr__(self, '_loading', False)
        
        # Auto-detect the caller's package for relative imports
        # Get the frame of the code that called this __init__
        caller_frame = inspect.currentframe().f_back
        caller_module = inspect.getmodule(caller_frame)
        
        if caller_module and hasattr(caller_module, '__package__'):
            detected_package = caller_module.__package__
        else:
            detected_package = None
        
        object.__setattr__(self, '_package', detected_package)
    
    def _ensure_loaded(self) -> Any:
        """
        Ensure the module is loaded, waiting if necessary.
        
        This method imports the module on first access and returns it.
        Subsequent calls return the cached module.
        
        Returns:
            The imported module object
            
        Raises:
            ImportError: If the module cannot be imported
        """
        module = object.__getattribute__(self, '_module')
        
        # Module already loaded
        if module is not None:
            return module
        
        # Prevent infinite recursion during import
        loading = object.__getattribute__(self, '_loading')
        if loading:
            module_name = object.__getattribute__(self, '_module_name')
            raise ImportError(
                f"Circular import detected while loading '{module_name}'. "
                f"This may indicate a recursive import loop."
            )
        
        # Mark as loading
        object.__setattr__(self, '_loading', True)
        
        try:
            module_name = object.__getattribute__(self, '_module_name')
            package = object.__getattribute__(self, '_package')
            
            # Handle relative imports (starting with .)
            if module_name.startswith('.'):
                # For relative imports, use the detected package context
                if package:
                    module = importlib.import_module(module_name, package=package)
                else:
                    # Fallback: try absolute import if no package detected
                    module = importlib.import_module(module_name)
            else:
                # Absolute import
                module = importlib.import_module(module_name)
            
            # Cache the module
            object.__setattr__(self, '_module', module)
            object.__setattr__(self, '_loading', False)
            
            return module
        
        except Exception as e:
            # Reset loading state on failure
            object.__setattr__(self, '_loading', False)
            raise ImportError(f"Failed to import module '{module_name}': {e}") from e
    
    def __getattr__(self, name: str) -> Any:
        """
        Forward attribute access to the real module.
        
        Args:
            name: The attribute name to access
            
        Returns:
            The attribute from the real module
        """
        if name.startswith('_'):
            # Handle private attributes directly to avoid recursion
            raise AttributeError(f"LazyModule has no attribute '{name}'")
        
        module = self._ensure_loaded()
        return getattr(module, name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        """
        Forward attribute assignment to the real module (if loaded).
        
        Args:
            name: The attribute name to set
            value: The value to assign
        """
        if name.startswith('_'):
            # Handle private attributes on the LazyModule itself
            object.__setattr__(self, name, value)
        else:
            # Forward to the real module
            module = self._ensure_loaded()
            setattr(module, name, value)
    
    def __dir__(self) -> list:
        """List all attributes available on the real module."""
        module = self._ensure_loaded()
        return dir(module)
    
    def __repr__(self) -> str:
        """Return a string representation."""
        module_name = object.__getattribute__(self, '_module_name')
        module = object.__getattribute__(self, '_module')
        
        if module is None:
            return f"<LazyModule '{module_name}' (not yet loaded)>"
        else:
            return f"<LazyModule '{module_name}' (loaded as {module})>"
    
    def __str__(self) -> str:
        """Return a string representation."""
        return repr(self)


# Example usage documentation
"""
# INSTEAD OF (which causes circular import issues):
from .MyModule import MyClass

# USE:
MyModule = LazyModule('.MyModule')
# Then access normally:
# MyClass = MyModule.MyClass

# This defers the import until MyModule is actually accessed, allowing
# MyModule to be initialized without immediately loading its dependencies.
"""
