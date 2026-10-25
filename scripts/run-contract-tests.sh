#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
if [[ ! -d "$project_dir/.deps" ]]; then
  echo "Missing development environment. Run 'make install' first." >&2
  exit 2
fi
PYTHONPATH="$project_dir/.deps" "$python_bin" "$project_dir/scripts/validate-contracts.py"
