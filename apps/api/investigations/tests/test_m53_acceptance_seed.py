"""Ensure the optional local acceptance fixture exercises real version-finalization APIs."""

import json
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from investigations.models import PostmortemVersion
from investigations.postmortem_content import content_sha256


def test_acceptance_seed_requires_explicit_consent(monkeypatch):
    monkeypatch.delenv("IF_M53_FIXTURE_ALLOWED", raising=False)
    with pytest.raises(CommandError, match="Requires both"):
        call_command("seed_m53_acceptance", confirm_local=True)


@pytest.mark.django_db(transaction=True)
def test_acceptance_seed_creates_two_distinct_finalized_versions(monkeypatch):
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        pytest.skip("Acceptance fixture explicitly targets PostgreSQL")
    monkeypatch.setenv("IF_M53_FIXTURE_ALLOWED", "1")
    monkeypatch.setenv("DJANGO_SECURE_SSL_REDIRECT", "false")
    buffer = StringIO()
    with override_settings(
        DEBUG=True, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver", "localhost"]
    ):
        call_command("seed_m53_acceptance", confirm_local=True, stdout=buffer)
    data = json.loads(buffer.getvalue())
    assert data["synthetic"] is True
    assert data["IF_M53_EMAIL"] != data["IF_M53_OTHER_EMAIL"]
    assert data["IF_M53_VERSION_ID"] != data["IF_M53_OLD_VERSION_ID"]
    old = PostmortemVersion.objects.get(pk=data["IF_M53_OLD_VERSION_ID"])
    latest = PostmortemVersion.objects.get(pk=data["IF_M53_VERSION_ID"])
    assert old.incident_id == latest.incident_id
    assert old.version == 1
    assert latest.version == 2
    assert old.content["human"]["revision"] == 1
    assert latest.content["human"]["revision"] == 2
    assert old.content_sha256 == content_sha256(old.content)
    assert latest.content_sha256 == content_sha256(latest.content)
    assert old.content != latest.content
