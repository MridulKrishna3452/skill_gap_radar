"""Fixed-window rate limiting in Redis (INCR + EXPIRE), and the client IP.

Keys never contain raw emails: identifiers are hashed. If Redis is unreachable, limits on
login and registration fail closed (503), so brute force cannot ride on an outage. Limits on
ordinary reads fail open, so a Redis outage does not take the read API down.
"""

import hashlib
import logging
import time
from ipaddress import ip_address

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.config import Settings, parse_rate
from app.core.errors import RateLimitedError, ServiceUnavailableError

logger = logging.getLogger(__name__)
PREFIX = "rl:"


def hashed(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


async def hit(
    redis: Redis, bucket: str, identifier: str, rate: str, *, fail_closed: bool = False
) -> None:
    """Count one request; raise RateLimitedError once the window's limit is exceeded."""
    count, seconds = parse_rate(rate)
    window = int(time.time()) // seconds
    key = f"{PREFIX}{bucket}:{hashed(identifier)}:{window}"
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, seconds + 1)
            current, _ = await pipe.execute()
    except (RedisError, OSError) as exc:
        if fail_closed:
            logger.warning("Rate limiter unavailable for %s; refusing request", bucket)
            raise ServiceUnavailableError("Service temporarily unavailable") from exc
        logger.warning("Rate limiter unavailable for %s; allowing request", bucket)
        return
    if int(current) > count:
        retry_after = seconds - int(time.time()) % seconds
        raise RateLimitedError(max(retry_after, 1))


def client_ip(request: Request, settings: Settings) -> str:
    """The peer address, or the client named in X-Forwarded-For when the peer is a trusted
    proxy (the right-most address that is not itself a trusted proxy)."""
    peer = request.client.host if request.client else "unknown"
    if peer not in settings.TRUSTED_PROXIES:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    for candidate in reversed([p.strip() for p in forwarded.split(",") if p.strip()]):
        try:
            ip_address(candidate)
        except ValueError:
            break
        if candidate not in settings.TRUSTED_PROXIES:
            return candidate
    return peer
