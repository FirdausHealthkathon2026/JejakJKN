"""Gate 0 database roles can connect only to the database they own."""

import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="requires the Compose stack"
)


def psql(user: str, password: str, database: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            f"PGPASSWORD={password}",
            "postgres",
            "psql",
            "-h",
            "127.0.0.1",
            "-U",
            user,
            "-d",
            database,
            "-Atc",
            "SELECT current_database()",
        ],
        capture_output=True,
        text=True,
    )


def test_encounter_role_cannot_connect_to_evidence_database() -> None:
    own = psql("encounter_app", os.environ["ENCOUNTER_DB_PASSWORD"], "encounter_db")
    cross = psql("encounter_app", os.environ["ENCOUNTER_DB_PASSWORD"], "evidence_db")
    assert own.returncode == 0 and own.stdout.strip() == "encounter_db"
    assert cross.returncode != 0
