from uuid import uuid4

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.throttling import ScopedRateThrottle


@pytest.fixture(autouse=True)
def isolated_auth_throttle_cache(monkeypatch):
    cache = LocMemCache(
        f"incidentforge-auth-throttle-tests-{uuid4().hex}",
        {},
    )
    monkeypatch.setattr(ScopedRateThrottle, "cache", cache)
