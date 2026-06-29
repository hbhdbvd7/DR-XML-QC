#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/local_conform_qc_cli.py" --gui "$@"
fi

exec python "$SCRIPT_DIR/local_conform_qc_cli.py" --gui "$@"
