"""Tests for explicit, conservative orphan-file reconciliation."""

import os
import time
from io import StringIO
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings

from incidents.models import Incident
from ingestion.models import IngestionJob, LogSource
from ingestion.storage import path_for, store


@pytest.mark.django_db
def test_orphan_cleanup_dry_run_and_safe_execute(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        owner = get_user_model().objects.create_user(
            "m23-cleanup@example.org", "valid-passphrase-205"
        )
        incident = Incident.objects.create(owner=owner, title="Orphan cleanup")
        job = IngestionJob.objects.create(incident=incident, owner=owner)
        key, checksum, size = store(SimpleUploadedFile("referenced.log", b"INFO live\n"))
        LogSource.objects.create(
            incident=incident,
            job=job,
            filename="referenced.log",
            object_key=key,
            sha256=checksum,
            byte_size=size,
        )
        orphan = path_for(uuid4().hex)
        orphan.write_bytes(b"old unreferenced bytes")
        os.utime(orphan, (time.time() - 2 * 86400,) * 2)
        recent = path_for(uuid4().hex)
        recent.write_bytes(b"unreferenced but too recent")
        notes = tmp_path / "unrelated.txt"
        notes.write_text("do not remove")
        output = StringIO()
        call_command("sweep_orphan_evidence", stdout=output)
        assert "orphan_candidates=1" in output.getvalue()
        assert orphan.exists()
        output = StringIO()
        call_command("sweep_orphan_evidence", "--execute", stdout=output)
        assert "deleted=1" in output.getvalue()
        assert not orphan.exists()
        assert recent.exists() and path_for(key).exists() and notes.exists()


@pytest.mark.django_db
def test_cleanup_skips_symlinks_and_nonhex_names(tmp_path):
    with override_settings(INGESTION_STORAGE_ROOT=str(tmp_path)):
        outside = tmp_path.parent / f"m23-outside-{uuid4().hex}.txt"
        outside.write_text("must survive")
        symlink = path_for(uuid4().hex)
        try:
            symlink.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        os.utime(outside, (time.time() - 2 * 86400,) * 2)
        call_command("sweep_orphan_evidence", "--execute")
        assert symlink.is_symlink() and outside.exists()
        outside.unlink()
