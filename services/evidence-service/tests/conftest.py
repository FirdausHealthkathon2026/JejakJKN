import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "services/evidence-service"), str(ROOT / "libs/python-auth"), str(ROOT / "libs/canonical-data")]
os.environ.setdefault("FIELD_ENCRYPTION_MASTER_KEY", "22" * 32)
