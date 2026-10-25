import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "services/encounter-service"), str(ROOT / "libs/python-auth"), str(ROOT / "libs/canonical-data")]
os.environ.setdefault("PARTICIPANT_LOOKUP_HMAC_KEY", "11" * 32)
os.environ.setdefault("FIELD_ENCRYPTION_MASTER_KEY", "22" * 32)

