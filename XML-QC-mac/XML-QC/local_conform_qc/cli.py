"""Command-line parsing for local conform QC."""

from __future__ import annotations

import argparse
from pathlib import Path

from .models import ToolConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run DaVinci Resolve local conform QC.")
    parser.add_argument("--project-root", type=Path, help="Project root. If XML/media paths are omitted, edit/ and footage/ are used.")
    parser.add_argument("--xml", dest="xml_paths", type=Path, action="append", help="XML path. Can be repeated.")
    parser.add_argument("--media-root", type=Path, help="Shot media path. Defaults to PROJECT_ROOT/footage.")
    parser.add_argument(
        "--look-reference",
        dest="look_references",
        type=Path,
        action="append",
        default=[],
        help="Look reference media path to import into the look-reference Media Pool folder.",
    )
    parser.add_argument("--project-name", help="Resolve project name.")
    parser.add_argument("--import-all-media", action="store_true", help="Import all scanned media, not only matched media.")
    parser.add_argument("--gui", action="store_true", help="Use simple file dialogs to select paths.")
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> ToolConfig:
    """Build runtime config from parsed CLI arguments."""
    return ToolConfig(
        project_root=args.project_root,
        xml_paths=list(args.xml_paths or []),
        media_root=args.media_root,
        look_references=list(args.look_references or []),
        project_name=args.project_name,
        import_all_media=bool(args.import_all_media),
    )
