"""Immutable, versioned report acceptance and authorization tests."""

import json
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from incidents.models import Incident
from investigations.models import PostmortemVersion
from investigations.postmortem_content import canonical_bytes, content_sha256
from investigations.postmortem_service import PostmortemConflict, _verified_entries
from investigations.tests.test_human_review_m51 import review_payload
from investigations.tests.test_human_review_m51 import saved_report as saved_report


@pytest.mark.django_db
def test_finalize_only_completed_review_and_reuse_same_revision(saved_report):
    client, _, incident, report, review_url = saved_report
    root = f"/api/v1/incidents/{incident.id}/reports"
    data = {"investigation_id": str(report.id), "expected_review_revision": 1}
    assert (
        client.post(root, data=json.dumps(data), content_type="application/json").status_code == 409
    )
    review = review_payload(status="reviewed")
    assert (
        client.put(review_url, data=json.dumps(review), content_type="application/json").status_code
        == 200
    )
    created = client.post(root, data=json.dumps(data), content_type="application/json")
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["version"] == 1
    assert body["review_revision_number"] == 1
    assert body["content"]["ai"]["findings"] == report.report
    assert body["content"]["human"]["status"] == "reviewed"
    assert (
        body["content"]["evidence_manifest"][0]["event_id"]
        == report.report["observed_facts"][0]["event_ids"][0]
    )
    assert "message" not in body["content"]["evidence_manifest"][0]
    assert len(canonical_bytes(body["content"])) < 50_000
    assert body["content_sha256"] == content_sha256(body["content"])
    repeated = client.post(root, data=json.dumps(data), content_type="application/json")
    assert repeated.status_code == 200
    assert repeated.json()["id"] == body["id"]
    assert PostmortemVersion.objects.count() == 1
    listed = client.get(root)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]
    assert "content" not in listed.json()[0]
    detail = client.get(f"{root}/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["content_sha256"] == body["content_sha256"]


@pytest.mark.django_db
def test_review_updates_create_new_version_without_rewriting_old(saved_report):
    client, _, incident, report, review_url = saved_report
    root = f"/api/v1/incidents/{incident.id}/reports"
    assert (
        client.put(
            review_url,
            data=json.dumps(review_payload(status="reviewed")),
            content_type="application/json",
        ).status_code
        == 200
    )
    first = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
        content_type="application/json",
    ).json()
    revision = review_payload(revision=1, status="reviewed")
    revision["impact_notes"] = "Different downstream impact after follow-up."
    assert (
        client.put(
            review_url, data=json.dumps(revision), content_type="application/json"
        ).status_code
        == 200
    )
    stale = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
        content_type="application/json",
    )
    assert stale.status_code == 409
    second = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 2}),
        content_type="application/json",
    )
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["content"]["human"]["impact_notes"] == revision["impact_notes"]
    original = client.get(f"{root}/{first['id']}").json()
    assert original["content"] == first["content"]
    assert original["content_sha256"] == first["content_sha256"]
    assert client.get(root).json()[0]["version"] == 2


@pytest.mark.django_db
def test_draft_review_and_malformed_inputs_do_not_generate_reports(saved_report):
    client, _, incident, report, review_url = saved_report
    root = f"/api/v1/incidents/{incident.id}/reports"
    assert (
        client.put(
            review_url,
            data=json.dumps(review_payload(status="draft")),
            content_type="application/json",
        ).status_code
        == 200
    )
    draft = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
        content_type="application/json",
    )
    assert draft.status_code == 409
    assert draft.json()["code"] == "review_incomplete"
    for payload in (
        {"investigation_id": "bad-id", "expected_review_revision": 1},
        {"investigation_id": str(report.id), "expected_review_revision": 0},
        {"expected_review_revision": 1},
    ):
        assert (
            client.post(root, data=json.dumps(payload), content_type="application/json").status_code
            == 400
        )
    assert PostmortemVersion.objects.count() == 0


@pytest.mark.django_db
def test_cross_user_and_deleted_incident_are_not_visible(saved_report):
    client, owner, incident, report, review_url = saved_report
    root = f"/api/v1/incidents/{incident.id}/reports"
    client.put(
        review_url,
        data=json.dumps(review_payload(status="reviewed")),
        content_type="application/json",
    )
    created = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
        content_type="application/json",
    ).json()
    other = get_user_model().objects.create_user(
        f"other-{uuid4()}@example.org", "test-password-1234"
    )
    client.force_login(other)
    assert client.get(root).status_code == 404
    assert client.get(f"{root}/{created['id']}").status_code == 404
    assert (
        client.post(
            root,
            data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
            content_type="application/json",
        ).status_code
        == 404
    )
    client.logout()
    assert client.get(root).status_code in (401, 403)
    client.force_login(owner)
    incident.deleted_at = timezone.now()
    incident.save(update_fields=["deleted_at"])
    assert client.get(root).status_code == 404
    assert client.get(f"{root}/{created['id']}").status_code == 404


@pytest.mark.django_db
def test_corrupted_report_is_never_served_and_direct_save_rejected(saved_report):
    client, _, incident, report, review_url = saved_report
    root = f"/api/v1/incidents/{incident.id}/reports"
    client.put(
        review_url,
        data=json.dumps(review_payload(status="reviewed")),
        content_type="application/json",
    )
    created = client.post(
        root,
        data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
        content_type="application/json",
    ).json()
    version = PostmortemVersion.objects.get(id=created["id"])
    version.content = {"tampered": True}
    with pytest.raises(ValueError, match="immutable"):
        version.save()
    assert client.get(f"{root}/{created['id']}").status_code == 200
    if connection.vendor == "postgresql":
        with pytest.raises(DatabaseError), transaction.atomic():
            PostmortemVersion.objects.filter(id=version.id).update(content={"tampered": True})
        assert client.get(f"{root}/{created['id']}").status_code == 200
    else:
        PostmortemVersion.objects.filter(id=version.id).update(content={"tampered": True})
        response = client.get(f"{root}/{created['id']}")
        assert response.status_code == 409
        assert response.json()["code"] == "report_integrity"


@pytest.mark.django_db
def test_source_tampering_and_cross_incident_source_rejected(saved_report):
    client, owner, incident, report, review_url = saved_report
    client.put(
        review_url,
        data=json.dumps(review_payload(status="reviewed")),
        content_type="application/json",
    )
    root = f"/api/v1/incidents/{incident.id}/reports"
    second = Incident.objects.create(owner=owner, title="Other")
    assert (
        client.post(
            f"/api/v1/incidents/{second.id}/reports",
            data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
            content_type="application/json",
        ).status_code
        == 404
    )
    snapshot = report.snapshot
    tampered = deepcopy(snapshot.entries)
    tampered[0]["message"] = "changed evidence"
    snapshot.entries = tampered
    with pytest.raises(PostmortemConflict, match="source could not be verified"):
        _verified_entries(report)
    with patch(
        "investigations.postmortem_service._verified_entries",
        side_effect=PostmortemConflict(
            "source_integrity", "The investigation source could not be verified."
        ),
    ):
        response = client.post(
            root,
            data=json.dumps({"investigation_id": str(report.id), "expected_review_revision": 1}),
            content_type="application/json",
        )
    assert response.status_code == 409
    assert response.json()["code"] == "source_integrity"
