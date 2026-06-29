"""GUI path selection boundary.

GUI code belongs here and should only collect paths, not run business logic.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import Tk, filedialog, simpledialog

from .models import ToolConfig


def pick_config() -> ToolConfig:
    """Return a GUI-selected config."""
    root = Tk()
    root.withdraw()
    try:
        project_root = filedialog.askdirectory(title="Select project root")
        xml_paths = filedialog.askopenfilenames(
            title="Select XML file(s), optional",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        media_root = filedialog.askdirectory(title="Select shot media folder, optional")
        look_references = filedialog.askopenfilenames(
            title="Select look reference media, optional",
            filetypes=[("Media files", "*.mov *.mp4 *.mxf *.m4v *.jpg *.jpeg *.png"), ("All files", "*.*")],
        )
        project_name = simpledialog.askstring(
            "Resolve project",
            "Resolve project name",
            initialvalue="LocalConform_QC_Test",
            parent=root,
        )
    finally:
        root.destroy()

    return ToolConfig(
        project_root=Path(project_root) if project_root else None,
        xml_paths=[Path(path) for path in xml_paths],
        media_root=Path(media_root) if media_root else None,
        look_references=[Path(path) for path in look_references],
        project_name=project_name or None,
    )
