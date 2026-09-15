from __future__ import annotations

"""Mystery Code Builder: Launcher component for generating base64 codes from yamls."""

import base64
import gzip
import io
import os
import zipfile
from pathlib import Path
from typing import Any

from worlds.LauncherComponents import Component, components, Type as ComponentType


def _encode_content(content: bytes) -> str:
    """Gzip and base64 encode content."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as f:
        f.write(content)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def _handle_single_yaml(path: Path) -> str:
    """Read single yaml file and encode."""
    data = path.read_bytes()
    return _encode_content(data)


def _handle_multiple_yamls(paths: list[Path]) -> str:
    """Read multiple yaml files, concatenate with --- separator, and encode."""
    combined = b""
    for i, p in enumerate(paths):
        data = p.read_bytes()
        if i > 0:
            combined += b"\n---\n"
        combined += data
    return _encode_content(combined)


def _handle_zip(path: Path) -> str:
    """Read zip file and encode its raw bytes."""
    # For zip, we just encode the raw zip bytes (which already contains yamls)
    # The decoder will handle both gzipped yaml and raw zip
    data = path.read_bytes()
    # If it's a zip, we can either encode the zip directly or extract and recombine
    # For simplicity, encode the raw zip bytes
    return _encode_content(data)


def generate_code_from_selection(paths: list[str]) -> tuple[str, str]:
    """Generate base64 code from selected files.
    
    Returns (code, set_name suggestion).
    """
    if not paths:
        raise ValueError("No files selected")
    
    path_objs = [Path(p) for p in paths]
    
    # Check if any is a zip
    zip_files = [p for p in path_objs if p.suffix.lower() == '.zip']
    yaml_files = [p for p in path_objs if p.suffix.lower() in ('.yaml', '.yml')]
    
    # If single zip, handle as zip
    if len(path_objs) == 1 and zip_files:
        code = _handle_zip(path_objs[0])
        set_name = path_objs[0].stem
        return code, set_name
    
    # If all are yamls, handle accordingly
    if yaml_files and len(yaml_files) == len(path_objs):
        if len(yaml_files) == 1:
            code = _handle_single_yaml(yaml_files[0])
            set_name = yaml_files[0].stem
        else:
            code = _handle_multiple_yamls(yaml_files)
            # Use common prefix or first file's name
            set_name = "My Set"
            if len(yaml_files) > 1:
                # Try to find common prefix
                stems = [p.stem for p in yaml_files]
                # Simple: use first file's stem + etc
                set_name = f"{stems[0]} +{len(stems)-1}"
        return code, set_name
    
    # Mixed or other: treat as multiple yamls, ignoring non-yaml
    # Filter to just yamls and zips
    all_valid = yaml_files + zip_files
    if not all_valid:
        raise ValueError("No valid yaml or zip files selected")
    
    # For mixed, just handle yamls
    if yaml_files:
        if len(yaml_files) == 1:
            code = _handle_single_yaml(yaml_files[0])
            set_name = yaml_files[0].stem
        else:
            code = _handle_multiple_yamls(yaml_files)
            set_name = "My Set"
        return code, set_name
    
    # Only zips (multiple)
    if zip_files:
        # For multiple zips, combine their contents?
        # For now, just use first zip
        code = _handle_zip(zip_files[0])
        set_name = zip_files[0].stem
        return code, set_name
    
    raise ValueError("No valid files to encode")


def launch_code_builder(*args: Any) -> None:
    """Launcher entry for Mystery Code Builder."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
    import subprocess
    import sys

    root = tk.Tk()
    root.withdraw()  # Hide main window
    root.attributes('-topmost', True)

    # Ask user what they want to do (similar to website: single, multiple, zip)
    # Use file dialog that allows multiple selection and zip filtering
    filetypes = [
        ("YAML files", "*.yaml *.yml"),
        ("Zip files", "*.zip"),
        ("All files", "*.*"),
    ]
    
    # Let user select files (multiple)
    paths = filedialog.askopenfilenames(
        title="Select YAML file(s) or ZIP (like website - single yaml, multiple yamls, or zip)",
        filetypes=filetypes,
    )
    
    if not paths:
        root.destroy()
        return
    
    try:
        code, suggested_name = generate_code_from_selection(list(paths))
        
        # Ask for set name
        set_name = simpledialog.askstring(
            "Set Name",
            f"Enter a name for this set (suggested: {suggested_name}):",
            initialvalue=suggested_name,
            parent=root
        )
        if set_name is None:  # Cancelled
            root.destroy()
            return
        if not set_name.strip():
            set_name = suggested_name
        
        # Show the code and offer to copy to clipboard or save as text file
        # Create a new window to display the code
        code_window = tk.Toplevel(root)
        code_window.title(f"Mystery Code for '{set_name}'")
        code_window.geometry("700x400")
        code_window.attributes('-topmost', True)
        
        tk.Label(code_window, text=f"Game Code Sets entry for '{set_name}':", font=("Arial", 10, "bold")).pack(pady=5)
        tk.Label(code_window, text="Add this to your Mystery Game yaml under 'Mystery Game: game_code_sets':", font=("Arial", 8)).pack()
        example = f'  {set_name}: "{code[:60]}..." (truncated, full in box)'
        tk.Label(code_window, text=example, font=("Courier", 7), fg="gray").pack()
        
        text_box = tk.Text(code_window, wrap=tk.WORD, height=12)
        text_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        # Show full yaml snippet
        snippet = f'Mystery Game:\n  game_code_sets:\n    {set_name}: "{code}"'
        text_box.insert("1.0", snippet)
        text_box.config(state=tk.DISABLED)
        
        # Also show just the code
        tk.Label(code_window, text="Base64 code (full):", font=("Arial", 8)).pack()
        code_box = tk.Text(code_window, wrap=tk.WORD, height=4)
        code_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        code_box.insert("1.0", code)
        code_box.config(state=tk.DISABLED)
        
        def copy_to_clipboard():
            try:
                root.clipboard_clear()
                root.clipboard_append(code)
                root.update()  # Keep clipboard after window closes
                messagebox.showinfo("Copied", "Base64 code copied to clipboard!", parent=code_window)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy: {e}", parent=code_window)
        
        def save_as_file():
            try:
                file_path = filedialog.asksaveasfilename(
                    title="Save base64 code as text file",
                    initialfile=f"{set_name}_mystery_code.txt",
                    defaultextension=".txt",
                    filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                    parent=code_window
                )
                if file_path:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Mystery Game Code Set: {set_name}\n")
                        f.write(f"# Generated from: {', '.join([Path(p).name for p in paths])}\n")
                        f.write(f"# Add to your yaml as:\n")
                        f.write(f"Mystery Game:\n")
                        f.write(f"  game_code_sets:\n")
                        f.write(f"    {set_name}: \"{code}\"\n")
                        f.write(f"\n# Full base64 code:\n")
                        f.write(code)
                    messagebox.showinfo("Saved", f"Code saved to:\n{file_path}", parent=code_window)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}", parent=code_window)
        
        button_frame = tk.Frame(code_window)
        button_frame.pack(pady=5)
        
        tk.Button(button_frame, text="Copy to Clipboard", command=copy_to_clipboard, bg="lightblue", width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Save as Text File", command=save_as_file, bg="lightgreen", width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Close", command=lambda: (code_window.destroy(), root.destroy()), width=10).pack(side=tk.LEFT, padx=5)
        
        # Also auto-copy to clipboard
        try:
            root.clipboard_clear()
            root.clipboard_append(code)
            root.update()
        except Exception:
            pass
        
        code_window.mainloop()
        
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate code:\n{e}", parent=root)
        root.destroy()
    # Don't destroy root immediately, let code_window handle it


# Register with launcher
try:
    components.append(Component(
        "Mystery Code Builder",
        func=launch_code_builder,
        component_type=ComponentType.TOOL,
        description="Generate base64 codes for Mystery Game sets from yaml(s) or zip. Copies to clipboard or saves as text file. Like website: single yaml, multiple yamls, or zip.",
    ))
except Exception:
    pass
