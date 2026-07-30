"""Minimal in-memory Redis fake for hermetic OTP tests (R1 W3).

Implements only the subset otp_service uses, with decode_responses=True semantics
(get returns str). TTLs are stored but not auto-expired — tests exercise logic
paths, not wall-clock expiry, and simulate expiry by delete(). Not a pytest
module (leading underscore ⇒ not collected).
"""

from __future__ import annotations


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def set(
        self,
        key: str,
        value: object,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex
        return True

    def setex(self, key: str, seconds: int, value: object) -> bool:
        self.store[key] = str(value)
        self.ttls[key] = seconds
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def getdel(self, key: str) -> str | None:
        value = self.store.pop(key, None)
        self.ttls.pop(key, None)
        return value

    def incr(self, key: str) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    def expire(self, key: str, seconds: int) -> bool:
        if key in self.store:
            self.ttls[key] = seconds
            return True
        return False

    def ttl(self, key: str) -> int:
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.ttls.pop(key, None)
                removed += 1
        return removed
