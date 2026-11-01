"""Pure encounter transition guards."""

from jejakjkn_canonical.problems import Problem

from .entities import EncounterStatus


def require_checkout_eligible(status: str) -> None:
    if status != EncounterStatus.OPEN:
        raise Problem(
            409,
            "INVALID_ENCOUNTER_STATE",
            "Invalid encounter state",
            "Only an open encounter can be checked out.",
        )
