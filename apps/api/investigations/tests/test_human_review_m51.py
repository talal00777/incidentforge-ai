import hashlib
import json
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from incidents.models import Incident
from investigations.models import (
    InvestigationAttempt,
    InvestigationReport,
    InvestigationReview,
    InvestigationReviewRevision,
)


@pytest.fixture
def saved_report(db):
    user = get_user_model().objects.create_user(
        f"reviewer-{uuid4()}@example.org", "test-password-1234"
    )
    incident = Incident.objects.create(owner=user, title="Gateway timeout")
    entry = {
        "event_id": str(uuid4()),
        "source_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "source_name": "gateway.log",
        "source_lines": [1, 1],
        "occurred_at": "2026-11-04T03:40:00Z",
        "timestamp_quality": "explicit",
        "severity": "ERROR",
        "service": "gateway",
        "message": "payment timeout",
    }
    payload = json.dumps(
        {
            "selection_version": "1.0",
            "privacy_policy_version": "1.0",
            "incident_id": str(incident.id),
            "events": [entry],
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    snapshot = EvidenceSnapshot.objects.create(
        incident=incident,
        created_by=user,
        entries=[entry],
        sha256=hashlib.sha256(payload).hexdigest(),
        item_count=1,
        characters=len(entry["message"]),
        payload_bytes=len(payload),
        selection_version="1.0",
        privacy_policy_version="1.0",
        consent_accepted_at="2026-11-04T03:40:00Z",
    )
    attempt = InvestigationAttempt.objects.create(
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="openai",
        model_id="gpt-4o-mini",
        prompt_profile="few_shot",
        consent_accepted_at="2026-11-04T03:40:00Z",
        status="succeeded",
    )
    report_body = {
        "schema_version": "1.0",
        "incident_summary": "Checkout timed out.",
        "observed_facts": [{"statement": "Timeout", "event_ids": [entry["event_id"]]}],
        "hypotheses": [
            {
                "title": "Provider timeout",
                "status": "plausible_unconfirmed",
                "supporting_event_ids": [entry["event_id"]],
                "contradicting_event_ids": [],
                "alternative_explanations": [],
                "further_checks": [],
            },
            {
                "title": "Gateway issue",
                "status": "insufficient_evidence",
                "supporting_event_ids": [],
                "contradicting_event_ids": [],
                "alternative_explanations": [],
                "further_checks": [],
            },
        ],
        "suggested_actions": [],
        "limitations": [],
    }
    report = InvestigationReport.objects.create(
        attempt=attempt,
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="openai",
        model_id="gpt-4o-mini",
        temperature=0.2,
        max_output_tokens=2048,
        prompt_profile="few_shot",
        prompt_version="1.0",
        response_schema_version="1.0",
        report=report_body,
        consent_accepted_at="2026-11-04T03:40:00Z",
    )
    client = Client()
    client.force_login(user)
    url = f"/api/v1/incidents/{incident.id}/investigations/{report.id}/review"
    return client, user, incident, report, url


def review_payload(revision=0, status="draft"):
    return {
        "expected_revision": revision,
        "status": status,
        "impact_notes": "Checkout degraded for several minutes.",
        "remediation_notes": "Verify provider latency and gateway retries.",
        "hypotheses": [
            {
                "index": 0,
                "decision": "accepted_as_working_hypothesis",
                "note": "Correlates with gateway logs",
            },
            {"index": 1, "decision": "reviewed", "note": "Still needs more data"},
        ],
    }


@pytest.mark.django_db
def test_empty_review_is_read_only(saved_report):
    client, _, _, report, url = saved_report
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["revision"] == 0
    assert [h["decision"] for h in response.json()["hypotheses"]] == ["needs_review"] * 2
    assert InvestigationReview.objects.count() == 0
    assert report.report["hypotheses"][0]["status"] == "plausible_unconfirmed"


@pytest.mark.django_db
def test_save_and_revise_records_history_without_modifying_ai_report(saved_report):
    client, _, _, report, url = saved_report
    first = client.put(url, data=json.dumps(review_payload()), content_type="application/json")
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert first.json()["updated_at"]
    second = client.put(
        url, data=json.dumps(review_payload(1, "reviewed")), content_type="application/json"
    )
    assert second.status_code == 200
    assert second.json()["status"] == "reviewed"
    assert second.json()["revision"] == 2
    assert InvestigationReviewRevision.objects.filter(review__report=report).count() == 2
    assert list(
        InvestigationReviewRevision.objects.filter(review__report=report).values_list(
            "number", flat=True
        )
    ) == [2, 1]
    report.refresh_from_db()
    assert report.report["hypotheses"][0]["status"] == "plausible_unconfirmed"
    assert report.report["incident_summary"] == "Checkout timed out."
    assert client.get(url).json()["revision"] == 2


@pytest.mark.django_db
def test_stale_edits_conflict_and_do_not_create_revision(saved_report):
    client, _, _, report, url = saved_report
    data = review_payload()
    assert (
        client.put(url, data=json.dumps(data), content_type="application/json").status_code == 200
    )
    conflict = client.put(url, data=json.dumps(data), content_type="application/json")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "review_conflict"
    assert InvestigationReviewRevision.objects.filter(review__report=report).count() == 1


@pytest.mark.django_db
def test_invalid_hypothesis_decisions_are_rejected(saved_report):
    client, _, _, _, url = saved_report
    invalid = review_payload()
    invalid["hypotheses"] = invalid["hypotheses"][:1]
    assert (
        client.put(url, data=json.dumps(invalid), content_type="application/json").status_code
        == 400
    )
    invalid = review_payload()
    invalid["hypotheses"][0]["index"] = 999
    assert (
        client.put(url, data=json.dumps(invalid), content_type="application/json").status_code
        == 400
    )
    invalid = review_payload(status="reviewed")
    invalid["hypotheses"][1]["decision"] = "needs_review"
    assert (
        client.put(url, data=json.dumps(invalid), content_type="application/json").status_code
        == 400
    )
    invalid = review_payload()
    invalid["remediation_notes"] = "x" * 4001
    assert (
        client.put(url, data=json.dumps(invalid), content_type="application/json").status_code
        == 400
    )
    assert InvestigationReviewRevision.objects.count() == 0


@pytest.mark.django_db
def test_owner_scope_and_authentication(saved_report):
    client, owner, incident, report, url = saved_report
    other = get_user_model().objects.create_user(
        f"outsider-{uuid4()}@example.org", "test-password-1234"
    )
    client.force_login(other)
    assert client.get(url).status_code == 404
    assert (
        client.put(
            url, data=json.dumps(review_payload()), content_type="application/json"
        ).status_code
        == 404
    )
    assert InvestigationReview.objects.count() == 0
    client.logout()
    assert client.get(url).status_code in (401, 403)
    client.force_login(owner)
    unrelated = Incident.objects.create(owner=owner, title="Different incident")
    assert (
        client.get(
            f"/api/v1/incidents/{unrelated.id}/investigations/{report.id}/review"
        ).status_code
        == 404
    )
    incident.deleted_at = timezone.now()
    incident.save(update_fields=["deleted_at"])
    assert client.get(url).status_code == 404
