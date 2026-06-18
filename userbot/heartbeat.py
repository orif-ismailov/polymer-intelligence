"""
Redis heartbeat for the Telegram userbot process.

The userbot writes a heartbeat key to Redis every USERBOT_HEARTBEAT_SECONDS
(default 60). The check_userbot_health Celery beat task reads this key every
5 minutes and raises a deduped admin alert if the heartbeat is absent or
stale by more than USERBOT_SILENCE_SECONDS (300 s = 5 min).

Key contract:
  HEARTBEAT_KEY = "userbot:heartbeat"
  Value = float (Unix timestamp of last write, as a decimal string)
  TTL   = USERBOT_HEARTBEAT_SECONDS * 10 (so the key auto-expires if the
          userbot is permanently gone — prevents stale-forever entries)

Security (T-05-08):
  - The heartbeat is the observable liveness signal for the monitoring outage
    risk. Its absence triggers a deduped admin alert within 5 min.
  - TTL ensures the key does not persist across a permanent userbot shutdown,
    avoiding false "ok" reads on a revived cluster.
"""

from __future__ import annotations

import time

# Key written by the userbot and read by the health service
HEARTBEAT_KEY = "userbot:heartbeat"


def write_heartbeat(redis: object) -> None:
    """Write the current UTC epoch as the heartbeat value.

    Sets HEARTBEAT_KEY to the current time.time() float (as a string) with a
    TTL of USERBOT_HEARTBEAT_SECONDS * 10 so that the key auto-expires if the
    userbot is permanently shut down.

    Args:
        redis: A redis.Redis (or fakeredis.FakeRedis) client instance.
               Accepts any object with a ``set`` method matching the redis-py API.
    """
    from app.core.config import settings  # noqa: PLC0415

    ttl_seconds = settings.USERBOT_HEARTBEAT_SECONDS * 10
    redis.set(HEARTBEAT_KEY, str(time.time()), ex=ttl_seconds)  # type: ignore[union-attr]


def read_heartbeat(redis: object) -> float | None:
    """Read the last heartbeat epoch from Redis.

    Returns the stored float timestamp, or None if the key is absent
    (userbot has never run, or TTL expired after a prolonged outage).

    Args:
        redis: A redis.Redis (or fakeredis.FakeRedis) client instance.

    Returns:
        float epoch or None.
    """
    raw = redis.get(HEARTBEAT_KEY)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None
