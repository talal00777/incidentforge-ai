"""Create isolated local-only postmortem versions for read-only browser acceptance.

Synthetic test data, not AI inference. No existing incident/review is altered.
"""

import hashlib
import json
import os
import secrets
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import Client
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from incidents.models import Incident
from investigations.models import InvestigationAttempt, InvestigationReport, PostmortemVersion
from investigations.postmortem_content import content_sha256


def _assert_response(response, expected, action):
    if response.status_code != expected:
        raise CommandError(
            f"{action}: HTTP {response.status_code}, expected {expected}; "
            f"body={response.content[:600]!r}"
        )
    return response.json()


def _snapshot(user, incident):
    event = {
        "event_id": str(uuid4()),
        "source_id": str(uuid4()),
        "source_sha256": "a" * 64,
        "source_name": "synthetic-acceptance.log",
        "source_lines": [1, 1],
        "occurred_at": "2026-11-08T03:40:00Z",
        "timestamp_quality": "explicit",
        "severity": "ERROR",
        "service": "synthetic-gateway",
        "message": "SYNTHETIC TEST EVENT: upstream call exceeded latency threshold",
    }
    content = json.dumps(
        {
            "selection_version": "1.0",
            "privacy_policy_version": "1.0",
            "incident_id": str(incident.id),
            "events": [event],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    snapshot = EvidenceSnapshot.objects.create(
        incident=incident,
        created_by=user,
        entries=[event],
        sha256=hashlib.sha256(content).hexdigest(),
        item_count=1,
        characters=len(event["message"]),
        payload_bytes=len(content),
        selection_version="1.0",
        privacy_policy_version="1.0",
        consent_accepted_at=timezone.now(),
    )
    return event, snapshot


def _report(user, incident, event, snapshot):
    now = timezone.now()
    attempt = InvestigationAttempt.objects.create(
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="synthetic_fixture",
        model_id="no-model-called",
        prompt_profile="test_fixture",
        consent_accepted_at=now,
        status="succeeded",
    )
    report_body = {
        "schema_version": "1.0",
        "incident_summary": "SYNTHETIC E2E FIXTURE: checkout gateway timed out.",
        "observed_facts": [
            {
                "statement": "Synthetic gateway log reported an upstream timeout.",
                "event_ids": [event["event_id"]],
            }
        ],
        "hypotheses": [
            {
                "title": "Synthetic upstream latency",
                "status": "plausible_unconfirmed",
                "supporting_event_ids": [event["event_id"]],
                "contradicting_event_ids": [],
                "alternative_explanations": ["Synthetic gateway saturation"],
                "further_checks": ["Review synthetic latency traces"],
            },
            {
                "title": "Synthetic gateway saturation",
                "status": "insufficient_evidence",
                "supporting_event_ids": [],
                "contradicting_event_ids": [],
                "alternative_explanations": [],
                "further_checks": ["Collect more synthetic telemetry"],
            },
        ],
        "suggested_actions": [
            {
                "action": "Review a synthetic latency trace, without executing changes.",
                "safety": "review_only",
                "rationale_event_ids": [event["event_id"]],
            }
        ],
        "limitations": ["Synthetic acceptance fixture; no real AI inference occurred."],
    }
    report = InvestigationReport.objects.create(
        attempt=attempt,
        incident=incident,
        snapshot=snapshot,
        created_by=user,
        snapshot_sha256=snapshot.sha256,
        provider="synthetic_fixture",
        model_id="no-model-called",
        temperature=0,
        max_output_tokens=128,
        prompt_profile="test_fixture",
        prompt_version="1.0",
        response_schema_version="1.0",
        report=report_body,
        consent_accepted_at=now,
    )
    return report


def _review_payload(revision, impact):
    return {
        "expected_revision": revision,
        "status": "reviewed",
        "impact_notes": impact,
        "remediation_notes": "Synthetic acceptance test: inspect gateway retries.",
        "hypotheses": [
            {
                "index": 0,
                "decision": "accepted_as_working_hypothesis",
                "note": "For synthetic fixture only; not a confirmed cause.",
            },
            {
                "index": 1,
                "decision": "reviewed",
                "note": "More evidence would be needed in a real incident.",
            },
        ],
    }


class Command(BaseCommand):
    help = "Seed two synthetic finalized postmortem versions for M5.3 live-browser acceptance."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-local",
            action="store_true",
            help=(
                "Explicit acknowledgement that test records will be created "
                "in the current database."
            ),
        )

    def handle(self, *args, **options):
        if not options["confirm_local"] or os.getenv("IF_M53_FIXTURE_ALLOWED") != "1":
            raise CommandError("Requires both --confirm-local and IF_M53_FIXTURE_ALLOWED=1.")
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to seed unless DJANGO_DEBUG=true (local development only)."
            )
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError("Expected the local IncidentForge PostgreSQL database.")
        if os.getenv("DJANGO_SECURE_SSL_REDIRECT", "false").lower() in {"1", "yes", "true"}:
            raise CommandError("Refusing to seed with SSL redirect enabled.")

        owner_password = secrets.token_urlsafe(27)
        outsider_password = secrets.token_urlsafe(27)
        suffix = uuid4().hex[:12]
        owner_email = f"if-m53-owner-{suffix}@example.test"
        outsider_email = f"if-m53-outsider-{suffix}@example.test"

        with transaction.atomic():
            User = get_user_model()  # noqa: N806
            owner = User.objects.create_user(owner_email, owner_password)
            outsider = User.objects.create_user(outsider_email, outsider_password)
            incident = Incident.objects.create(
                owner=owner,
                title="SYNTHETIC ACCEPTANCE TEST - Gateway Timeout",
                description=(
                    "Isolated M5.3 browser test record. No real incident, "
                    "no AI provider calls."
                ),
                service_name="synthetic-gateway",
                environment=Incident.Environment.DEVELOPMENT,
                severity=Incident.Severity.LOW,
                status=Incident.Status.INVESTIGATING,
            )
            event, snapshot = _snapshot(owner, incident)
            report = _report(owner, incident, event, snapshot)

            client = Client()
            client.force_login(owner)
            review_url = f"/api/v1/incidents/{incident.id}/investigations/{report.id}/review"
            versions_url = f"/api/v1/incidents/{incident.id}/reports"

            first_review = _assert_response(
                client.put(
                    review_url,
                    data=json.dumps(
                        _review_payload(0, "Synthetic impact assessment, initial review.")
                    ),
                    content_type="application/json",
                ),
                200,
                "Complete review revision 1",
            )
            if first_review["revision"] != 1 or first_review["status"] != "reviewed":
                raise CommandError("Review revision 1 was not finalized correctly.")

            create_args = {"investigation_id": str(report.id), "expected_review_revision": 1}
            first = _assert_response(
                client.post(
                    versions_url, data=json.dumps(create_args), content_type="application/json"
                ),
                201,
                "Finalize version 1",
            )
            if first["version"] != 1:
                raise CommandError("Expected new version 1")

            repeated = _assert_response(
                client.post(
                    versions_url, data=json.dumps(create_args), content_type="application/json"
                ),
                200,
                "Verify idempotent finalization",
            )
            if repeated["id"] != first["id"]:
                raise CommandError("Re-finalization unexpectedly created a new version")

            second_review = _assert_response(
                client.put(
                    review_url,
                    data=json.dumps(
                        _review_payload(
                            1, "Synthetic impact assessment revised for second version."
                        )
                    ),
                    content_type="application/json",
                ),
                200,
                "Complete review revision 2",
            )
            if second_review["revision"] != 2 or second_review["status"] != "reviewed":
                raise CommandError("Review revision 2 was not finalized correctly.")

            second = _assert_response(
                client.post(
                    versions_url,
                    data=json.dumps(
                        {"investigation_id": str(report.id), "expected_review_revision": 2}
                    ),
                    content_type="application/json",
                ),
                201,
                "Finalize version 2",
            )
            if second["version"] != 2 or second["id"] == first["id"]:
                raise CommandError("Expected a distinct new version 2")

            first_db = PostmortemVersion.objects.get(pk=first["id"])
            second_db = PostmortemVersion.objects.get(pk=second["id"])
            if first_db.content_sha256 != content_sha256(first_db.content):
                raise CommandError("Version 1 checksum mismatch")
            if second_db.content_sha256 != content_sha256(second_db.content):
                raise CommandError("Version 2 checksum mismatch")
            if first_db.content["human"]["revision"] != 1:
                raise CommandError("Version 1 was unexpectedly changed")
            if second_db.content["human"]["revision"] != 2:
                raise CommandError("Version 2 was not based on review revision 2")
            if first_db.content == second_db.content:
                raise CommandError("Versions unexpectedly have identical content")
            for version_id in (first["id"], second["id"]):
                resource = f"{versions_url}/{version_id}"
                _assert_response(client.get(resource), 200, "Verify version detail")
                pdf = client.get(f"{resource}/download?export_format=pdf")
                if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF-"):
                    raise CommandError(f"PDF export failed for version {version_id}")
                exported_json = client.get(f"{resource}/download?export_format=json")
                if exported_json.status_code != 200:
                    raise CommandError(f"JSON export failed for version {version_id}")
                if exported_json.json()["postmortem_version"]["id"] != version_id:
                    raise CommandError("JSON export used wrong version")
            client.force_login(outsider)
            if client.get(f"{versions_url}/{second['id']}").status_code != 404:
                raise CommandError("Outsider could read the finalized report")
            if (
                client.get(f"{versions_url}/{second['id']}/download?export_format=pdf").status_code
                != 404
            ):
                raise CommandError("Outsider could download report PDF")
            if PostmortemVersion.objects.filter(incident=incident).count() != 2:
                raise CommandError("Expected exactly two finalized versions")

        result = {
            "IF_M53_EMAIL": owner_email,
            "IF_M53_PASSWORD": owner_password,
            "IF_M53_OTHER_EMAIL": outsider_email,
            "IF_M53_OTHER_PASSWORD": outsider_password,
            "IF_M53_INCIDENT_ID": str(incident.id),
            "IF_M53_VERSION_ID": second["id"],
            "IF_M53_OLD_VERSION_ID": first["id"],
            "IF_M53_BASE_URL": "http://localhost:3000",
            "report_url": f"http://localhost:3000/incidents/{incident.id}/reports/{second['id']}",
            "synthetic": True,
        }
        self.stdout.write(json.dumps(result, sort_keys=True))
