"""Entry point for the local conform QC tool.

Core behavior lives in the local_conform_qc package. This file should stay
thin as the project grows.
"""

from __future__ import annotations

from pathlib import Path
import sys

from local_conform_qc.cli import config_from_args, parse_args
from local_conform_qc.gui_picker import pick_config
from local_conform_qc.logging_utils import configure_logging, get_logger
from local_conform_qc.runner import run_config


LOGGER = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    configure_logging()
    args = parse_args(argv)
    config = pick_config() if args.gui else config_from_args(args)
    reports = run_config(config, Path(__file__).resolve().parent)
    for json_path, html_path in reports:
        LOGGER.info("Wrote reports: %s and %s", json_path, html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
