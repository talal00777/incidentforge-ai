"""SSRF-protected outbound webhook formatter, HMAC signer, and delivery audit engine."""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

from celery import shared_task
from django.utils import timezone

from workspaces.models import AlertWebhook, WebhookDelivery

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
WEBHOOK_TIMEOUT_SECONDS = 5


class UnsafeWebhookTarget(ValueError):
    """Raised when a webhook target URL violates SSRF or transport security policy."""


def _is_forbidden_ip(ip_str: str) -> bool:
    addr = ipaddress.ip_address(ip_str)
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_webhook_url(url: str, *, resolve_dns: bool = False) -> str:
    """Validate webhook URL scheme, hostname, and (optionally) resolved IP addresses."""
    cleaned = (url or "").strip()
    parsed = urllib.parse.urlsplit(cleaned)
    allow_http = os.getenv("WEBHOOK_ALLOW_HTTP", "").lower() in ("1", "true", "yes")
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme not in allowed_schemes:
        raise UnsafeWebhookTarget("Webhook URL must use HTTPS.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeWebhookTarget("Webhook URL must specify a valid host without credentials.")

    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise UnsafeWebhookTarget("Local and internal metadata hostnames are blocked.")

    ip_obj = None
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None
    if ip_obj is not None and _is_forbidden_ip(str(ip_obj)):
        raise UnsafeWebhookTarget("Private, loopback, and link-local IP addresses are blocked.")

    if resolve_dns:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeWebhookTarget(f"Unable to resolve webhook hostname: {host}") from exc
        if not infos:
            raise UnsafeWebhookTarget(f"No network addresses resolved for host: {host}")
        for info in infos:
            ip_str = info[4][0]
            if _is_forbidden_ip(ip_str):
                raise UnsafeWebhookTarget(
                    f"Resolved address {ip_str} is inside a restricted network range."
                )

    return cleaned


def mask_signing_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 10:
        return "••••••••"
    return f"{secret[:6]}••••{secret[-4:]}"


def sign_webhook_payload(secret: str, timestamp: int, body_bytes: bytes) -> str:
    signed_input = f"{timestamp}.".encode() + body_bytes
    digest = hmac.new(secret.encode("utf-8"), signed_input, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def format_webhook_payload(
    provider: str,
    event_type: str,
    workspace_name: str,
    incident_summary: dict,
) -> dict:
    """Build a strictly structured, PII-safe payload tailored to the target provider."""
    title = incident_summary.get("title", "IncidentForge alert")
    severity = str(incident_summary.get("severity", "medium")).upper()
    status_val = str(incident_summary.get("status", "open")).upper()
    service = incident_summary.get("service_name") or "unassigned"
    environment = incident_summary.get("environment") or "production"
    incident_id = incident_summary.get("id") or ""
    occurred_at = timezone.now().isoformat().replace("+00:00", "Z")

    base = {
        "event": event_type,
        "workspace": workspace_name,
        "timestamp": occurred_at,
        "incident": {
            "id": incident_id,
            "title": title,
            "severity": severity.lower(),
            "status": status_val.lower(),
            "service_name": service,
            "environment": environment,
        },
    }

    if provider == AlertWebhook.Provider.SLACK:
        return {
            "text": f"[{severity}] {event_type}: {title} ({service}/{environment})",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"[{severity}] {title[:120]}"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Event:*\n`{event_type}`"},
                        {"type": "mrkdwn", "text": f"*Workspace:*\n{workspace_name}"},
                        {"type": "mrkdwn", "text": f"*Service:*\n`{service}` ({environment})"},
                        {"type": "mrkdwn", "text": f"*Status:*\n{status_val}"},
                    ],
                },
            ],
        }

    if provider == AlertWebhook.Provider.DISCORD:
        color = {
            "CRITICAL": 0xDC2626,
            "HIGH": 0xEA580C,
            "MEDIUM": 0xD97706,
            "LOW": 0x2563EB,
        }.get(severity, 0x2563EB)
        return {
            "username": "IncidentForge Alerts",
            "embeds": [
                {
                    "title": f"[{severity}] {title[:200]}",
                    "description": f"Event `{event_type}` in workspace **{workspace_name}**",
                    "color": color,
                    "fields": [
                        {"name": "Service", "value": f"`{service}`", "inline": True},
                        {"name": "Environment", "value": environment, "inline": True},
                        {"name": "Status", "value": status_val, "inline": True},
                    ],
                    "timestamp": occurred_at,
                }
            ],
        }

    if provider == AlertWebhook.Provider.PAGERDUTY:
        pd_sev = {
            "CRITICAL": "critical",
            "HIGH": "error",
            "MEDIUM": "warning",
            "LOW": "info",
        }.get(severity, "warning")
        return {
            "event_action": "resolve" if status_val == "RESOLVED" else "trigger",
            "dedup_key": f"incidentforge-{incident_id or 'test'}",
            "payload": {
                "summary": f"[{workspace_name}] {title[:200]}",
                "source": service,
                "severity": pd_sev,
                "timestamp": occurred_at,
                "component": service,
                "group": environment,
                "custom_details": base["incident"],
            },
        }

    return base


def deliver_webhook(
    webhook: AlertWebhook,
    event_type: str,
    incident_summary: dict,
    *,
    dry_run: bool = False,
) -> WebhookDelivery:
    """Validate SSRF rules, sign, deliver (or dry-run), and record a WebhookDelivery audit row."""
    payload = format_webhook_payload(
        webhook.provider, event_type, webhook.workspace.name, incident_summary
    )
    body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ts = int(time.time())
    signature = sign_webhook_payload(webhook.signing_secret, ts, body_bytes)

    raw_inc_id = incident_summary.get("id")
    parsed_inc_id = None
    if raw_inc_id:
        try:
            parsed_inc_id = UUID(str(raw_inc_id))
        except ValueError:
            parsed_inc_id = None

    try:
        target = validate_webhook_url(webhook.target_url, resolve_dns=not dry_run)
    except UnsafeWebhookTarget as exc:
        return WebhookDelivery.objects.create(
            webhook=webhook,
            event_type=event_type,
            incident_id=parsed_inc_id,
            status=WebhookDelivery.Status.BLOCKED,
            request_payload=payload,
            error_message=str(exc)[:300],
        )

    if dry_run:
        return WebhookDelivery.objects.create(
            webhook=webhook,
            event_type=event_type,
            incident_id=parsed_inc_id,
            status=WebhookDelivery.Status.DRY_RUN,
            http_status=None,
            latency_ms=0,
            request_payload=payload,
            response_excerpt=f"Signed dry-run ({signature[:28]}…); no outbound HTTP call made.",
        )

    delivery = WebhookDelivery(
        webhook=webhook,
        event_type=event_type,
        incident_id=parsed_inc_id,
        request_payload=payload,
    )
    req = urllib.request.Request(  # noqa: S310
        target,
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "IncidentForge-Webhook/1.0",
            "X-IncidentForge-Event": event_type,
            "X-IncidentForge-Signature": signature,
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT_SECONDS) as resp:  # noqa: S310
            elapsed_ms = int((time.monotonic() - started) * 1000)
            body_excerpt = resp.read(380).decode("utf-8", errors="replace")
            delivery.status = (
                WebhookDelivery.Status.DELIVERED
                if 200 <= resp.status < 300
                else WebhookDelivery.Status.FAILED
            )
            delivery.http_status = resp.status
            delivery.latency_ms = elapsed_ms
            delivery.response_excerpt = body_excerpt[:400]
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.http_status = exc.code
        delivery.latency_ms = elapsed_ms
        delivery.error_message = f"HTTP {exc.code}: {exc.reason}"[:300]
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.latency_ms = elapsed_ms
        delivery.error_message = str(exc)[:300]

    delivery.save()
    return delivery


def _matches_webhook(webhook: AlertWebhook, event_type: str, severity: str) -> bool:
    if not webhook.is_active:
        return False
    if webhook.event_types and event_type not in webhook.event_types:
        return False
    inc_rank = SEVERITY_RANK.get(severity.lower(), 1)
    min_rank = SEVERITY_RANK.get(webhook.min_severity.lower(), 1)
    return inc_rank >= min_rank


@shared_task(ignore_result=True)
def deliver_workspace_webhooks_task(workspace_id: str, event_type: str, incident_summary: dict):
    webhooks = list(
        AlertWebhook.objects.select_related("workspace").filter(
            workspace_id=workspace_id, is_active=True
        )
    )
    severity = str(incident_summary.get("severity", "medium"))
    for wh in webhooks:
        if _matches_webhook(wh, event_type, severity):
            deliver_webhook(wh, event_type, incident_summary, dry_run=False)


def dispatch_workspace_webhooks(incident, event_type: str) -> None:
    """Enqueue outbound alert webhooks for a workspace-scoped incident."""
    if not getattr(incident, "workspace_id", None):
        return
    summary = {
        "id": str(incident.id),
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "service_name": incident.service_name,
        "environment": incident.environment,
    }
    try:
        deliver_workspace_webhooks_task.delay(str(incident.workspace_id), event_type, summary)
    except Exception:
        logger.warning(
            "Unable to enqueue webhook dispatch for workspace %s event %s",
            incident.workspace_id,
            event_type,
        )
