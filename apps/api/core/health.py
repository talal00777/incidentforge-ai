"""Operational readiness probes for mandatory M0 dependencies."""

import logging

import redis
from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)


def dependencies_ready() -> bool:
    database_ready = False
    redis_ready = False

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            database_ready = cursor.fetchone() == (1,)
    except Exception:
        logger.warning("Readiness probe failed for database", exc_info=True)

    try:
        with redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        ) as client:
            redis_ready = bool(client.ping())
    except (redis.RedisError, OSError, ValueError):
        logger.warning("Readiness probe failed for broker", exc_info=True)

    return database_ready and redis_ready
