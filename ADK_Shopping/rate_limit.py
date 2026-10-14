"""Atomic Redis counters, shared across agents and server processes."""
import asyncio
import hashlib
from dataclasses import dataclass
from functools import lru_cache

import redis

from config import get_settings

# Increment and expiration happen atomically; a worker crash cannot leave an immortal key.
COUNTER_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


class RateLimitUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Rate limiting is unavailable. Check the Redis connection.")


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, retry_after)
        super().__init__(f"Rate limit reached. Retry in {self.retry_after} seconds.")


@dataclass(frozen=True)
class Decision:
    limit: int
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self, client, window_seconds: int):
        self.client = client
        self.window_seconds = window_seconds

    def check_sync(self, scope: str, identity: str, limit: int) -> Decision:
        # Do not store user IDs, names, emails or mobile numbers in Redis keys.
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        key = f"adk-shopping:rate:{scope}:{digest}"
        try:
            count, ttl = self.client.eval(COUNTER_SCRIPT, 1, key, self.window_seconds)
        except redis.RedisError:
            raise RateLimitUnavailable() from None
        if count > limit:
            raise RateLimitExceeded(int(ttl))
        return Decision(limit, max(0, limit - count), max(1, int(ttl)))

    async def check(self, scope: str, identity: str, limit: int) -> Decision:
        return await asyncio.to_thread(self.check_sync, scope, identity, limit)

    async def ping(self):
        try:
            await asyncio.to_thread(self.client.ping)
        except redis.RedisError:
            raise RateLimitUnavailable() from None


@lru_cache
def get_limiter() -> RateLimiter:
    settings = get_settings()
    client = redis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=3, socket_timeout=3,
        decode_responses=True,
    )
    return RateLimiter(client, settings.window_seconds)
