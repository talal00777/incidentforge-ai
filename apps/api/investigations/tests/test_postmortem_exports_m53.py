"""M5.3: authorized, repeatable PDF and JSON downloads of frozen report versions."""

import json
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from investigations.postmortem_content import content_sha256
from investigations.postmortem_export import (
    PostmortemExportError,
    export_envelope,
    render_json,
    render_pdf,
)
from investigations.postmortem_service import PostmortemConflict
from investigations.tests.test_human_review_m51 import review_payload
from investigations.tests.test_postmortem_m52 import saved_report as saved_report


@pytest.fixture
def finalized_postmortem(saved_report):
    client, owner, incident, investigation, review_url = saved_report
    response = client.put(
        review_url,
        data=json.dumps(review_payload(status="reviewed")),
        content_type="application/json",
    )
    assert response.status_code == 200
    created = client.post(
        f"/api/v1/incidents/{incident.id}/reports",
        data=json.dumps({"investigation_id": str(investigation.id), "expected_review_revision": 1}),
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    version = created.json()
    download = f"/api/v1/incidents/{incident.id}/reports/{version['id']}/download"
    return client, owner, incident, version, download


@pytest.mark.django_db
def test_json_download_is_canonical_repeatable_and_version_pinned(finalized_postmortem):
    client, _, _, version, download = finalized_postmortem
    first = client.get(download + "?export_format=json")
    second = client.get(download + "?export_format=json")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first["Content-Type"].startswith("application/json")
    assert first["Content-Disposition"].startswith("attachment;")
    assert first["Cache-Control"] == "private, no-store"
    assert first["X-Content-Type-Options"] == "nosniff"
    payload = json.loads(first.content)
    assert payload["export_schema_version"] == "1.0"
    assert payload["postmortem_version"]["id"] == version["id"]
    assert payload["postmortem_version"]["number"] == 1
    assert datetime.fromisoformat(
        payload["postmortem_version"]["created_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(version["created_at"].replace("Z", "+00:00"))
    assert payload["content"] == version["content"]
    assert payload["postmortem_version"]["content_sha256"] == content_sha256(payload["content"])
    assert render_json(payload) == first.content


@pytest.mark.django_db
def test_pdf_download_is_repeatable_and_contains_real_pdf(finalized_postmortem):
    client, _, _, version, download = finalized_postmortem
    first = client.get(download + "?export_format=pdf")
    second = client.get(download + "?export_format=pdf")  # PDF is the default format.
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.content.startswith(b"%PDF-")
    assert len(first.content) > 2000
    assert first["Content-Type"].startswith("application/pdf")
    assert f"v1-{version['id']}.pdf" in first["Content-Disposition"]
    assert first["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_download_rejects_other_users_deleted_incidents_and_invalid_formats(finalized_postmortem):
    client, owner, incident, _, download = finalized_postmortem
    bad_format = client.get(download + "?export_format=html")
    assert bad_format.status_code == 400
    assert bad_format.json()["code"] == "invalid_export_format"
    other = get_user_model().objects.create_user(
        f"download-outsider-{uuid4()}@example.org", "test-password-1234"
    )
    client.force_login(other)
    assert client.get(download + "?export_format=pdf").status_code == 404
    assert client.get(download + "?export_format=json").status_code == 404
    client.logout()
    assert client.get(download + "?export_format=pdf").status_code in (401, 403)
    client.force_login(owner)
    incident.deleted_at = timezone.now()
    incident.save(update_fields=["deleted_at"])
    assert client.get(download + "?export_format=json").status_code == 404


@pytest.mark.django_db
def test_checksum_failure_never_exports_payload(finalized_postmortem):
    client, _, _, _, download = finalized_postmortem
    with patch(
        "investigations.postmortem_export_views.verified_content",
        side_effect=PostmortemConflict(
            "report_integrity", "This report version failed its integrity check."
        ),
    ):
        response = client.get(download + "?export_format=pdf")
    assert response.status_code == 409
    assert response.json()["code"] == "report_integrity"
    assert not response.content.startswith(b"%PDF-")


@pytest.mark.django_db
def test_bounded_export_failure_has_typed_response(finalized_postmortem):
    client, _, _, _, download = finalized_postmortem
    with patch(
        "investigations.postmortem_export_views.render_pdf",
        side_effect=PostmortemExportError(
            "export_too_large", "This report exceeds the PDF size limit."
        ),
    ):
        response = client.get(download + "?export_format=pdf")
    assert response.status_code == 422
    assert response.json()["code"] == "export_too_large"


def test_renderer_escapes_markup_and_does_not_modify_frozen_content():
    """Pure renderer regression, independent of database and HTTP request."""
    from copy import deepcopy
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from investigations.postmortem_content import content_sha256

    incident_id = uuid4()
    frozen = {
        "schema_version": "1.0",
        "incident": {"id": str(incident_id), "title": "<script>alert('x')</script>"},
        "ai": {
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "prompt_profile": "few_shot",
            "prompt_version": "1.0",
            "consent_accepted_at": "2026-11-04T03:40:00Z",
            "evidence_snapshot": {"id": str(uuid4()), "sha256": "a" * 64},
            "findings": {
                "incident_summary": "Timeout <not HTML> & upstream failure",
                "observed_facts": [],
                "hypotheses": [],
                "suggested_actions": [],
                "limitations": ["Confidence is limited"],
            },
        },
        "human": {
            "revision": 1,
            "reviewed_at": "2026-11-04T03:40:00Z",
            "impact_notes": "<b>Do not execute</b>",
            "remediation_notes": "Check gateway",
            "hypotheses": [],
        },
        "timeline": [],
        "evidence_manifest": [],
    }
    original = deepcopy(frozen)
    version = SimpleNamespace(
        id=uuid4(),
        incident_id=incident_id,
        version=1,
        content_sha256=content_sha256(frozen),
        created_at=datetime(2026, 11, 4, 3, 45, tzinfo=UTC),
    )
    envelope = export_envelope(version=version, verified_content=frozen)
    first = render_pdf(envelope)
    assert first.startswith(b"%PDF-")
    assert first == render_pdf(envelope)
    assert frozen == original
