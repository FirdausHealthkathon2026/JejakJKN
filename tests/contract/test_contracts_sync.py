"""The contract validator must complete without a print-only false positive."""

import subprocess
import sys
from pathlib import Path


def test_contract_validator() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, str(root / "scripts/validate-contracts.py")], cwd=root, check=True)
