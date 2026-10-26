"""Atomic Redis reservation for single-use QR tokens."""

import hashlib
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from jejakjkn_canonical.problems import Problem


RESERVE_OR_REPLAY = """
local exists = redis.call('EXISTS', KEYS[1])
if exists == 0 then return {'EXPIRED_OR_UNKNOWN'} end
local state = redis.call('HGET', KEYS[1], 'state')
local purpose = redis.call('HGET', KEYS[1], 'purpose')
local fch = redis.call('HGET', KEYS[1], 'facility_hint')
local reserved_by = redis.call('HGET', KEYS[1], 'reserved_by_scanner')
if purpose ~= ARGV[2] then return {'WRONG_PURPOSE', purpose} end
if fch ~= '' and fch ~= ARGV[4] then return {'FACILITY_MISMATCH', fch} end
if state == 'ISSUED' then
  redis.call('HSET', KEYS[1], 'state', 'RESERVED', 'reserved_by_scanner', ARGV[1])
  if ARGV[2] == 'CHECK_IN' then redis.call('HSET', KEYS[1], 'encounter_id', ARGV[3]) end
  redis.call('EXPIRE', KEYS[1], 300)
  return {'RESERVED', redis.call('HGET', KEYS[1], 'patient_id'), redis.call('HGET', KEYS[1], 'encounter_id')}
end
if reserved_by == ARGV[1] then
  return {'IDEMPOTENT_RETRY', state, redis.call('HGET', KEYS[1], 'patient_id'), redis.call('HGET', KEYS[1], 'encounter_id')}
end
return {'ALREADY_CONSUMED_BY_OTHER'}
"""


def nonce_digest(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Reservation:
    state: str
    patient_id: str
    encounter_id: str


class RedisQrStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def issue(
        self,
        *,
        nonce: str,
        patient_id: str,
        purpose: str,
        encounter_id: str | None,
        facility_hint: str | None,
        ttl_seconds: int,
    ) -> None:
        key = f"qr:nonce:{nonce_digest(nonce)}"
        values: dict[str, Any] = {
            "state": "ISSUED",
            "patient_id": patient_id,
            "purpose": purpose,
            "encounter_id": encounter_id or "",
            "reserved_by_scanner": "",
            "facility_hint": facility_hint or "",
        }
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.hset(key, mapping=values)
                pipe.expire(key, ttl_seconds)
                await pipe.execute()
        except RedisError as exc:
            raise _unavailable(exc)

    async def reserve(
        self,
        *,
        nonce: str,
        reservation_key: str,
        purpose: str,
        encounter_id: str,
        facility_code: str,
    ) -> Reservation:
        try:
            raw = await self.redis.eval(
                RESERVE_OR_REPLAY,
                1,
                f"qr:nonce:{nonce_digest(nonce)}",
                reservation_key,
                purpose,
                encounter_id,
                facility_code,
            )
        except RedisError as exc:
            raise _unavailable(exc)
        values = [v.decode() if isinstance(v, bytes) else str(v) for v in raw]
        state = values[0]
        if state == "EXPIRED_OR_UNKNOWN":
            raise Problem(
                410,
                "QR_TOKEN_EXPIRED",
                "QR token expired",
                "Request a new QR token and scan it again.",
            )
        if state == "FACILITY_MISMATCH":
            raise Problem(
                403,
                "FACILITY_MISMATCH",
                "Facility mismatch",
                "This QR token is not valid for the scanner facility.",
            )
        if state == "WRONG_PURPOSE":
            raise Problem(
                422,
                "WRONG_QR_PURPOSE",
                "Wrong QR purpose",
                "The QR token has a different purpose.",
            )
        if state == "ALREADY_CONSUMED_BY_OTHER":
            raise Problem(
                409,
                "QR_ALREADY_CONSUMED",
                "QR token already consumed",
                "The single-use QR token has already been reserved or redeemed.",
            )
        return Reservation(state, values[-2], values[-1])

    async def commit(self, nonce: str) -> None:
        try:
            await self.redis.hset(
                f"qr:nonce:{nonce_digest(nonce)}", mapping={"state": "COMMITTED"}
            )
        except RedisError:
            return

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except RedisError:
            return False


def _unavailable(exc: Exception) -> Problem:
    return Problem(
        503,
        "QR_STORE_UNAVAILABLE",
        "QR service unavailable",
        "QR redemption is temporarily unavailable; no encounter was created.",
    )
