"""Configuration parsing rejects ambiguous production settings."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import env_bool, env_csv


def test_env_bool_accepts_known_values(monkeypatch):
    monkeypatch.setenv("IF_TEST_BOOL", "YeS")
    assert env_bool("IF_TEST_BOOL") is True
    monkeypatch.setenv("IF_TEST_BOOL", "0")
    assert env_bool("IF_TEST_BOOL") is False


def test_env_bool_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("IF_TEST_BOOL", "perhaps")
    with pytest.raises(ImproperlyConfigured):
        env_bool("IF_TEST_BOOL")


def test_env_csv_trims_and_discards_empty_members(monkeypatch):
    monkeypatch.setenv("IF_TEST_CSV", "localhost, api, , 127.0.0.1")
    assert env_csv("IF_TEST_CSV") == ["localhost", "api", "127.0.0.1"]
