"""Reject unsafe asynchronous worker settings."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import bounded_env_int


@pytest.mark.parametrize(
    ("value", "result"),
    [("1", 1), ("3", 3), ("5", 5)],
)
def test_bounded_integer_accepts_range(monkeypatch, value, result):
    monkeypatch.setenv("IF_JOB_SETTING_TEST", value)
    assert bounded_env_int("IF_JOB_SETTING_TEST", 3, 1, 5) == result


@pytest.mark.parametrize("value", ["0", "6", "invalid", "1.5", ""])
def test_bounded_integer_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("IF_JOB_SETTING_TEST", value)
    with pytest.raises(ImproperlyConfigured):
        bounded_env_int("IF_JOB_SETTING_TEST", 3, 1, 5)


def test_bounded_integer_uses_default(monkeypatch):
    monkeypatch.delenv("IF_JOB_SETTING_TEST", raising=False)
    assert bounded_env_int("IF_JOB_SETTING_TEST", 3, 1, 5) == 3
