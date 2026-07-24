"""External-service integration gateways (R1+).

Bounded-context adapters for third-party services the app calls OUT to (as
opposed to `app/ingest/`, which pulls data IN). Each integration is isolated so a
dead provider degrades gracefully instead of taking a request path down.

- `sms/` — outbound SMS (Eskiz in prod, console driver in dev/CI) for OTP auth.
"""

from __future__ import annotations
