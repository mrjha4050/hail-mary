

# notifications/rate_limiter.py
import time
import uuid

import redis
from django.conf import settings

# Lua script — runs atomically on the Redis server, no other client
# can interleave a command in the middle of these steps.
#
# KEYS[1] = the sorted-set key for this rate limit (e.g. "ratelimit:email")
# ARGV[1] = current unix timestamp (float, seconds)
# ARGV[2] = window size in seconds (60)
# ARGV[3] = max allowed requests in the window (200)
# ARGV[4] = unique member id for this attempt (avoids collisions if two
#           calls land at the exact same timestamp)
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

-- Step 1: prune anything older than the window
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

-- Step 2: count what's left after pruning
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- Step 3: reserve this slot
    redis.call('ZADD', key, now, member)
    -- Keep the key from growing forever if it's ever abandoned
    redis.call('EXPIRE', key, window * 2)
    return 1
else
    return 0
end
"""


class SlidingWindowRateLimiter:
    """
    Redis-backed sliding-window rate limiter.

    Usage:
        limiter = SlidingWindowRateLimiter(key="ratelimit:email", limit=200, window_seconds=60)
        if limiter.allow():
            send_email(...)
        else:
            raise RateLimitExceeded(...)
    """

    def __init__(self, key: str, limit: int, window_seconds: int, redis_url: str = None):
        self.key = key
        self.limit = limit
        self.window_seconds = window_seconds
        self._client = redis.from_url(
            redis_url or settings.REDIS_URL,
            ssl_cert_reqs=None,  # match the Upstash TLS behavior used elsewhere
        )
        self._script = self._client.register_script(SLIDING_WINDOW_LUA)

    def allow(self) -> bool:
        """
        Returns True if this call is allowed under the rate limit
        (and atomically reserves the slot), False if rejected.
        """
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex}"
        try:
            result = self._script(
                keys=[self.key],
                args=[now, self.window_seconds, self.limit, member],
            )
        except redis.exceptions.RedisError:
            # Redis is unreachable — fail CLOSED (see DESIGN.md rationale:
            # better to delay sends than risk blowing past the provider's
            # hard limit and getting the API key throttled/banned).
            return False

        return bool(result)