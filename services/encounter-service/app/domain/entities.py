"""Small domain value set for encounter lifecycle decisions."""

from enum import StrEnum


class QrPurpose(StrEnum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class EncounterStatus(StrEnum):
    OPEN = "OPEN"
    CHECKED_OUT = "CHECKED_OUT"
    CLOSED_WITH_EXCEPTION = "CLOSED_WITH_EXCEPTION"
    CANCELLED = "CANCELLED"


class PresenceStatus(StrEnum):
    QR_VERIFIED = "QR_VERIFIED"
    EXCEPTION_DOCUMENTED = "EXCEPTION_DOCUMENTED"
    UNVERIFIED = "UNVERIFIED"
