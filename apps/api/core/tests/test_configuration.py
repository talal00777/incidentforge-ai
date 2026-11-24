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


def test_retention_schedule_registers_both_report_and_evidence_purges(monkeypatch):
    import importlib

    import config.settings as settings_module

    monkeypatch.setenv("RETENTION_CLEANUP_ENABLED", "true")
    try:
        reloaded = importlib.reload(settings_module)
        assert "purge-deleted-reports" in reloaded.CELERY_BEAT_SCHEDULE
        assert "purge-deleted-evidence" in reloaded.CELERY_BEAT_SCHEDULE
        assert (
            reloaded.CELERY_BEAT_SCHEDULE["purge-deleted-evidence"]["task"]
            == "incidents.tasks.purge_deleted_evidence"
        )
    finally:
        monkeypatch.delenv("RETENTION_CLEANUP_ENABLED", raising=False)
        importlib.reload(settings_module)


def test_provider_timeout_is_configurable_and_bounded(monkeypatch):
    from investigations.providers import configured_timeout

    monkeypatch.delenv("AI_PROVIDER_TIMEOUT_SECONDS", raising=False)
    assert configured_timeout() == 16
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "45")
    assert configured_timeout() == 45
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "999")
    assert configured_timeout() == 16
