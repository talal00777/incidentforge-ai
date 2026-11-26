import hashlib
import hmac
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from workspaces.models import AlertWebhook
from workspaces.webhooks import (
    UnsafeWebhookTarget,
    format_webhook_payload,
    sign_webhook_payload,
    validate_webhook_url,
)

User = get_user_model()


def _client_for(email: str):
    user = User.objects.create_user(email=email)
    client = Client()
    client.force_login(user)
    return client, user


@pytest.mark.django_db
def test_workspace_rbac_members_and_shared_incident_permissions():
    owner_client, owner = _client_for("ws-owner@example.com")
    resp_client, responder = _client_for("ws-responder@example.com")
    view_client, viewer = _client_for("ws-viewer@example.com")
    outsider_client, _ = _client_for("ws-outsider@example.com")

    # Create workspace
    ws_resp = owner_client.post(
        "/api/v1/workspaces",
        {"name": "Payments SRE", "description": "Core checkout & billing reliability"},
        content_type="application/json",
    )
    assert ws_resp.status_code == 201
    ws_id = ws_resp.json()["id"]
    assert ws_resp.json()["my_role"] == "owner"

    # Add responder and viewer
    add_r = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        {"email": responder.email, "role": "responder"},
        content_type="application/json",
    )
    assert add_r.status_code == 201
    add_v = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        {"email": viewer.email, "role": "viewer"},
        content_type="application/json",
    )
    assert add_v.status_code == 201

    # Non-owners cannot invite members or modify workspace
    assert (
        resp_client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            {"email": "ws-outsider@example.com", "role": "viewer"},
            content_type="application/json",
        ).status_code
        == 403
    )

    # Cannot demote or remove the last owner
    members = owner_client.get(f"/api/v1/workspaces/{ws_id}/members").json()
    owner_membership = next(m for m in members if m["user_id"] == str(owner.id))
    assert (
        owner_client.patch(
            f"/api/v1/workspaces/{ws_id}/members/{owner_membership['id']}",
            {"role": "responder"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        owner_client.delete(
            f"/api/v1/workspaces/{ws_id}/members/{owner_membership['id']}"
        ).status_code
        == 400
    )

    # Owner creates a workspace-scoped incident
    inc_resp = owner_client.post(
        "/api/v1/incidents",
        {
            "title": "Payment gateway timeout spike",
            "service_name": "payments-api",
            "severity": "critical",
            "workspace_id": ws_id,
        },
        content_type="application/json",
    )
    assert inc_resp.status_code == 201
    inc_id = inc_resp.json()["id"]
    assert inc_resp.json()["workspace_name"] == "Payments SRE"

    # Responder can read & update status & post war-room notes, but cannot delete incident
    assert resp_client.get(f"/api/v1/incidents/{inc_id}").status_code == 200
    assert (
        resp_client.patch(
            f"/api/v1/incidents/{inc_id}",
            {"status": "investigating"},
            content_type="application/json",
        ).status_code
        == 200
    )
    assert (
        resp_client.post(
            f"/api/v1/incidents/{inc_id}/timeline",
            {"entry_type": "note", "body": "Checking Stripe upstream TLS handshakes."},
            content_type="application/json",
        ).status_code
        == 201
    )
    assert resp_client.delete(f"/api/v1/incidents/{inc_id}").status_code == 403

    # Viewer can read incident, timeline, analysis, and dashboard, but gets 403 on writes
    view_detail = view_client.get(f"/api/v1/incidents/{inc_id}")
    assert view_detail.status_code == 200
    assert view_detail.json()["user_role"] == "viewer"
    assert view_client.get(f"/api/v1/incidents/{inc_id}/timeline").status_code == 200
    assert view_client.get(f"/api/v1/incidents/{inc_id}/analysis").status_code == 200
    assert view_client.get("/api/v1/dashboard/summary").json()["counts"]["total"] == 1
    assert (
        view_client.patch(
            f"/api/v1/incidents/{inc_id}",
            {"status": "resolved"},
            content_type="application/json",
        ).status_code
        == 403
    )
    assert (
        view_client.post(
            f"/api/v1/incidents/{inc_id}/timeline",
            {"entry_type": "note", "body": "Viewer should be blocked"},
            content_type="application/json",
        ).status_code
        == 403
    )
    # Viewer cannot create new incidents inside the workspace
    assert (
        view_client.post(
            "/api/v1/incidents",
            {"title": "Unauthorized viewer incident", "workspace_id": ws_id},
            content_type="application/json",
        ).status_code
        == 400
    )

    # Outsider sees 404 everywhere
    assert outsider_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 404
    assert outsider_client.get(f"/api/v1/incidents/{inc_id}").status_code == 404


@pytest.mark.django_db
def test_webhooks_ssrf_blocking_signing_formatting_and_dry_run_deliveries():
    owner_client, _ = _client_for("wh-owner@example.com")
    ws_id = owner_client.post(
        "/api/v1/workspaces", {"name": "Platform Alerts"}, content_type="application/json"
    ).json()["id"]

    # SSRF & insecure URL rejections
    for bad_url in (
        "http://hooks.example.com/alert",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.5/internal",
        "https://localhost/webhook",
        "https://metadata.google.internal/computeMetadata/v1/",
    ):
        with pytest.raises(UnsafeWebhookTarget):
            validate_webhook_url(bad_url, resolve_dns=False)
        resp = owner_client.post(
            f"/api/v1/workspaces/{ws_id}/webhooks",
            {"name": "Blocked hook", "provider": "slack", "target_url": bad_url},
            content_type="application/json",
        )
        assert resp.status_code == 400, f"Expected 400 for {bad_url}"

    # Create valid Slack webhook — returns one-time full signing_secret
    created = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/webhooks",
        {
            "name": "Ops Slack Channel",
            "provider": "slack",
            "target_url": "https://hooks.slack.com/services/T000/B000/XXXX",
            "event_types": ["incident.created", "postmortem.finalized"],
            "min_severity": "high",
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    wh = created.json()
    assert wh["signing_secret"].startswith("whsec_")
    assert "••••" in wh["signing_secret_preview"]

    # Subsequent GET masks the secret
    listed = owner_client.get(f"/api/v1/workspaces/{ws_id}/webhooks").json()
    assert len(listed) == 1
    assert "signing_secret" not in listed[0]

    # Test dry-run delivery + delivery audit history
    ping = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/webhooks/{wh['id']}/test",
        {"dry_run": True},
        content_type="application/json",
    )
    assert ping.status_code == 200
    assert ping.json()["status"] == "dry_run"
    assert "blocks" in ping.json()["request_payload"]

    deliveries = owner_client.get(
        f"/api/v1/workspaces/{ws_id}/webhooks/{wh['id']}/deliveries"
    ).json()
    assert len(deliveries) == 1
    assert deliveries[0]["event_type"] == "webhook.test"

    # Verify HMAC-SHA256 signature & all provider payload shapes
    body = json.dumps({"ok": True}, sort_keys=True, separators=(",", ":")).encode()
    sig = sign_webhook_payload("whsec_test123", 1700000000, body)
    expected = hmac.new(b"whsec_test123", b"1700000000." + body, hashlib.sha256).hexdigest()
    assert sig == f"t=1700000000,v1={expected}"

    summary = {
        "id": "inc-1",
        "title": "DB pool exhausted",
        "severity": "critical",
        "status": "open",
    }
    assert "embeds" in format_webhook_payload(
        AlertWebhook.Provider.DISCORD, "incident.created", "Ops", summary
    )
    assert "dedup_key" in format_webhook_payload(
        AlertWebhook.Provider.PAGERDUTY, "incident.created", "Ops", summary
    )
    assert (
        format_webhook_payload(AlertWebhook.Provider.GENERIC, "incident.created", "Ops", summary)[
            "event"
        ]
        == "incident.created"
    )
