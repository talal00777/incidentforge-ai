"""Deterministic, synthetic multi-service demo outage scenarios seeded via production parsers."""

import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from evidence.models import EvidenceSnapshot
from evidence.selection import build_package
from incidents.models import Incident, IncidentAuditEvent
from ingestion.models import IngestionJob, LogEvent, LogSource
from ingestion.parser import VERSION as PARSER_VERSION
from ingestion.parser import iter_records


@dataclass(frozen=True)
class DemoScenarioSpec:
    id: str
    title: str
    subtitle: str
    description: str
    service_name: str
    environment: str
    severity: str
    status: str
    impact_notes: str
    services: tuple[str, ...]
    expected_signals: tuple[str, ...]


SCENARIOS: tuple[DemoScenarioSpec, ...] = (
    DemoScenarioSpec(
        id="checkout-db-pool",
        title="Checkout API 503 surge after payment-worker v2.14.0 rollout",
        subtitle="Multi-service DB connection-pool exhaustion with burst anomaly and stack trace",
        description=(
            "Elevated HTTP 503 responses observed on checkout-api beginning 15 minutes after "
            "deploying payment-worker v2.14.0. Upstream payment calls timed out at 5000ms while "
            "worker connection pools hit 100% saturation."
        ),
        service_name="checkout-api",
        environment=Incident.Environment.PRODUCTION,
        severity=Incident.Severity.CRITICAL,
        status=Incident.Status.INVESTIGATING,
        impact_notes="14% of production checkout requests failed with HTTP 503 across a 12-minute window.",
        services=("edge-gateway", "checkout-api", "payment-worker"),
        expected_signals=(
            "LOO MAD anomaly burst",
            "3-service trace chain",
            "Multiline psycopg PoolTimeout traceback",
        ),
    ),
    DemoScenarioSpec(
        id="auth-jwt-rotation",
        title="Intermittent 401 token failures following JWKS key rotation",
        subtitle="Stale JWKS cache across session-verifier causing downstream order rejections",
        description=(
            "Following scheduled signing-key rotation, a subset of session-verifier pods retained "
            "the expired JWKS document past TTL, causing intermittent 401 responses on orders-api "
            "while catalog-api remained unaffected."
        ),
        service_name="edge-auth",
        environment=Incident.Environment.PRODUCTION,
        severity=Incident.Severity.HIGH,
        status=Incident.Status.OPEN,
        impact_notes="Elevated sign-in and order submission retries on 2 of 6 verifier pods.",
        services=("edge-auth", "session-verifier", "orders-api"),
        expected_signals=(
            "Cross-service trace correlation",
            "Counterevidence on healthy pod",
            "Normalized signature-error clustering",
        ),
    ),
    DemoScenarioSpec(
        id="redis-cache-stampede",
        title="Catalog search latency spike during Redis eviction cascade",
        subtitle="Cache miss stampede triggering fallback database timeouts on staging",
        description=(
            "Batch catalog re-index pushed Redis cluster memory past maxmemory, triggering rapid "
            "key evictions and a fallback query storm against the read replica."
        ),
        service_name="catalog-search",
        environment=Incident.Environment.STAGING,
        severity=Incident.Severity.MEDIUM,
        status=Incident.Status.INVESTIGATING,
        impact_notes="P95 search latency rose from 65ms to 2800ms during staging load replay.",
        services=("web-bff", "catalog-search", "redis-proxy"),
        expected_signals=(
            "Memory eviction warning ramp",
            "Service transition web-bff -> catalog-search -> redis-proxy",
            "Recovery slope post-flush",
        ),
    ),
)

SCENARIOS_BY_ID = {spec.id: spec for spec in SCENARIOS}


def list_demo_scenarios() -> list[dict]:
    return [
        {
            "id": spec.id,
            "title": spec.title,
            "subtitle": spec.subtitle,
            "service_name": spec.service_name,
            "environment": spec.environment,
            "severity": spec.severity,
            "services": list(spec.services),
            "expected_signals": list(spec.expected_signals),
        }
        for spec in SCENARIOS
    ]


def _iso(base: datetime, minutes_offset: float) -> str:
    stamp = (base + timedelta(minutes=minutes_offset)).astimezone(UTC)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _jsonl(records: list[dict]) -> bytes:
    return ("\n".join(json.dumps(item, separators=(",", ":")) for item in records) + "\n").encode(
        "utf-8"
    )


def _build_checkout_sources(base: datetime) -> list[tuple[str, bytes]]:
    edge_records: list[dict] = []
    checkout_records: list[dict] = []
    worker_lines: list[str] = []

    # Baseline traffic across 0..20 min and recovery across 32..45 min
    for idx, minute in enumerate(
        [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 33, 35, 37, 39, 41, 43, 45], start=1
    ):
        trace = f"tr-chk-base-{idx:03d}"
        edge_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "INFO",
                "service": "edge-gateway",
                "trace_id": trace,
                "message": f"POST /v2/checkout completed status=200 latency={38 + (idx % 14)}ms",
            }
        )
        checkout_records.append(
            {
                "timestamp": _iso(base, minute + 0.05),
                "level": "INFO",
                "service": "checkout-api",
                "trace_id": trace,
                "message": f"Payment intent authorized order_id=ord-{1000 + idx} duration={21 + (idx % 9)}ms",
            }
        )
        worker_lines.append(
            f"{_iso(base, minute + 0.1)} INFO service=payment-worker trace_id={trace} "
            f"pool_active={6 + (idx % 4)}/32 ledger commit ok"
        )

    # Deployment marker at minute 20
    worker_lines.append(
        f"{_iso(base, 20.0)} WARN service=payment-worker trace_id=tr-deploy-2140 "
        "rollout v2.14.0 started: eager settlement transaction lock enabled"
    )

    # Concentrated 10-minute anomaly burst (minutes 22..30)
    for burst_idx in range(1, 23):
        minute = 22.0 + (burst_idx * 0.35)
        trace = f"tr-chk-burst-{burst_idx:03d}"
        edge_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "ERROR" if burst_idx % 4 != 0 else "WARN",
                "service": "edge-gateway",
                "trace_id": trace,
                "message": (
                    f"POST /v2/checkout upstream timeout status=503 latency={5005 + burst_idx}ms"
                    if burst_idx % 4 != 0
                    else f"POST /v2/checkout slow response status=200 latency={2420 + burst_idx * 10}ms"
                ),
            }
        )
        checkout_records.append(
            {
                "timestamp": _iso(base, minute + 0.04),
                "level": "ERROR",
                "service": "checkout-api",
                "trace_id": trace,
                "message": f"Upstream payment-worker timed out after 5000ms (attempt={1 + (burst_idx % 3)}, status=503)",
            }
        )
        if burst_idx in (4, 11, 18):
            worker_lines.append(
                f"{_iso(base, minute + 0.08)} ERROR service=payment-worker trace_id={trace} "
                "Database connection pool exhausted (32/32 active, wait=5000ms)\n"
                "Traceback (most recent call last):\n"
                '  File "/srv/worker/payments/ledger.py", line 148, in reserve_funds\n'
                "    with pool.connection(timeout=5.0) as conn:\n"
                "psycopg_pool.PoolTimeout: couldn't get a connection after 5.00 sec"
            )
        else:
            worker_lines.append(
                f"{_iso(base, minute + 0.08)} WARN service=payment-worker trace_id={trace} "
                f"pool_active=32/32 queued_waiters={8 + burst_idx} lock_wait_ms={1800 + burst_idx * 45}"
            )

    checkout_records.append(
        {
            "timestamp": _iso(base, 31.2),
            "level": "WARN",
            "service": "checkout-api",
            "trace_id": "tr-chk-recover-001",
            "message": "Circuit breaker transitioned to half-open after payment-worker rollback to v2.13.9",
        }
    )

    return [
        ("edge-gateway-access.jsonl", _jsonl(edge_records)),
        ("checkout-api-app.jsonl", _jsonl(checkout_records)),
        ("payment-worker-pool.log", ("\n".join(worker_lines) + "\n").encode("utf-8")),
    ]


def _build_auth_sources(base: datetime) -> list[tuple[str, bytes]]:
    auth_records: list[dict] = []
    verifier_records: list[dict] = []
    orders_lines: list[str] = []

    for idx, minute in enumerate([1, 4, 7, 10, 13, 30, 33, 36, 39], start=1):
        trace = f"tr-auth-ok-{idx:03d}"
        auth_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "INFO",
                "service": "edge-auth",
                "trace_id": trace,
                "message": "Issued RS256 access token kid=key-2026-11b ttl=900s",
            }
        )
        verifier_records.append(
            {
                "timestamp": _iso(base, minute + 0.04),
                "level": "INFO",
                "service": "session-verifier",
                "trace_id": trace,
                "message": f"Verified token kid=key-2026-11b pod=verifier-{(idx % 2) + 1} latency=4ms",
            }
        )
        orders_lines.append(
            f"{_iso(base, minute + 0.09)} INFO service=orders-api trace_id={trace} "
            f"GET /v1/orders status=200 duration={28 + idx}ms"
        )

    auth_records.append(
        {
            "timestamp": _iso(base, 15.0),
            "level": "WARN",
            "service": "edge-auth",
            "trace_id": "tr-jwks-rotate-01",
            "message": "JWKS signing key rotated from kid=key-2026-11a to kid=key-2026-11b",
        }
    )

    for idx in range(1, 20):
        minute = 16.0 + (idx * 0.6)
        trace = f"tr-auth-fail-{idx:03d}"
        auth_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "INFO",
                "service": "edge-auth",
                "trace_id": trace,
                "message": "Token introspection request forwarded kid=key-2026-11b",
            }
        )
        verifier_records.append(
            {
                "timestamp": _iso(base, minute + 0.04),
                "level": "ERROR",
                "service": "session-verifier",
                "trace_id": trace,
                "message": f"Unknown JWKS kid=key-2026-11b on pod=verifier-{(idx % 2) + 5} (cache_age={3640 + idx * 30}s)",
            }
        )
        orders_lines.append(
            f"{_iso(base, minute + 0.08)} ERROR service=orders-api trace_id={trace} "
            f"POST /v1/orders rejected status=401 reason=invalid_token_signature attempt={1 + (idx % 2)}"
        )

    verifier_records.append(
        {
            "timestamp": _iso(base, 28.5),
            "level": "INFO",
            "service": "session-verifier",
            "trace_id": "tr-jwks-flush-01",
            "message": "Forced JWKS refresh completed on verifier-5 and verifier-6; kid=key-2026-11b loaded",
        }
    )

    return [
        ("edge-auth-jwks.jsonl", _jsonl(auth_records)),
        ("session-verifier.jsonl", _jsonl(verifier_records)),
        ("orders-api-errors.log", ("\n".join(orders_lines) + "\n").encode("utf-8")),
    ]


def _build_redis_sources(base: datetime) -> list[tuple[str, bytes]]:
    bff_records: list[dict] = []
    search_records: list[dict] = []
    redis_lines: list[str] = []

    for idx, minute in enumerate([1, 4, 7, 10, 13, 32, 35, 38, 41], start=1):
        trace = f"tr-cat-ok-{idx:03d}"
        bff_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "INFO",
                "service": "web-bff",
                "trace_id": trace,
                "message": f"GET /search/catalog status=200 latency={54 + (idx % 12)}ms",
            }
        )
        search_records.append(
            {
                "timestamp": _iso(base, minute + 0.03),
                "level": "INFO",
                "service": "catalog-search",
                "trace_id": trace,
                "message": "Cache hit ratio=0.96 shard=catalog-02",
            }
        )
        redis_lines.append(
            f"{_iso(base, minute + 0.06)} INFO service=redis-proxy trace_id={trace} "
            f"used_memory_pct={68 + (idx % 5)} evicted_keys=0"
        )

    for idx in range(1, 20):
        minute = 16.0 + (idx * 0.65)
        trace = f"tr-cat-spike-{idx:03d}"
        bff_records.append(
            {
                "timestamp": _iso(base, minute),
                "level": "WARN" if idx % 3 != 0 else "ERROR",
                "service": "web-bff",
                "trace_id": trace,
                "message": (
                    f"GET /search/catalog degraded latency={2450 + idx * 35}ms status=504"
                    if idx % 3 == 0
                    else f"GET /search/catalog slow response latency={1680 + idx * 20}ms status=200"
                ),
            }
        )
        search_records.append(
            {
                "timestamp": _iso(base, minute + 0.04),
                "level": "ERROR" if idx % 2 == 0 else "WARN",
                "service": "catalog-search",
                "trace_id": trace,
                "message": f"Cache miss stampede fallback to replica timed out after {1800 + idx * 25}ms (in_flight={42 + idx})",
            }
        )
        redis_lines.append(
            f"{_iso(base, minute + 0.08)} WARN service=redis-proxy trace_id={trace} "
            f"used_memory_pct=99 evicted_keys={420 + idx * 35} policy=allkeys-lru"
        )

    return [
        ("web-bff-requests.jsonl", _jsonl(bff_records)),
        ("catalog-search-worker.jsonl", _jsonl(search_records)),
        ("redis-proxy-evictions.log", ("\n".join(redis_lines) + "\n").encode("utf-8")),
    ]


SOURCE_BUILDERS = {
    "checkout-db-pool": _build_checkout_sources,
    "auth-jwt-rotation": _build_auth_sources,
    "redis-cache-stampede": _build_redis_sources,
}


@transaction.atomic
def seed_demo_scenario(user, scenario_id: str) -> dict:
    """Create a realistic synthetic incident with parsed sources, events, and evidence snapshot."""
    spec = SCENARIOS_BY_ID.get(scenario_id)
    if spec is None:
        raise ValueError(f"Unknown demo scenario: {scenario_id}")

    now = timezone.now()
    base_time = now - timedelta(minutes=50)

    incident = Incident.objects.create(
        owner=user,
        title=spec.title,
        description=spec.description,
        service_name=spec.service_name,
        environment=spec.environment,
        timezone="UTC",
        severity=spec.severity,
        status=spec.status,
        impact_notes=spec.impact_notes,
    )
    IncidentAuditEvent.objects.create(
        incident=incident,
        actor=user,
        action=IncidentAuditEvent.Action.CREATED,
        changed_fields=[],
    )

    job = IngestionJob.objects.create(
        incident=incident,
        owner=user,
        state=IngestionJob.State.SUCCEEDED,
        attempts=1,
        started_at=now,
        completed_at=now,
    )

    sources_created = 0
    all_events: list[LogEvent] = []
    source_files = SOURCE_BUILDERS[spec.id](base_time)

    for filename, payload in source_files:
        digest = hashlib.sha256(payload).hexdigest()
        source = LogSource.objects.create(
            incident=incident,
            job=job,
            filename=filename,
            object_key=f"demo/{incident.id}/{uuid.uuid4().hex}",
            sha256=digest,
            byte_size=len(payload),
            parser_version=PARSER_VERSION,
            state=LogSource.State.COMPLETE,
        )
        batch: list[LogEvent] = []
        rejected = 0
        for parsed, err in iter_records(io.BytesIO(payload)):
            if err or parsed is None:
                rejected += 1
                continue
            batch.append(
                LogEvent(
                    incident=incident,
                    source=source,
                    observed_at=now,
                    **parsed,
                )
            )
        LogEvent.objects.bulk_create(batch)
        source.accepted = len(batch)
        source.rejected = rejected
        source.save(update_fields=["accepted", "rejected"])
        all_events.extend(batch)
        sources_created += 1

    job.accepted = len(all_events)
    job.rejected = 0
    job.save(update_fields=["accepted", "rejected"])

    # Create a ready-to-investigate redacted evidence snapshot with up to 18 high-signal events.
    prioritized = [e for e in all_events if e.severity in ("ERROR", "FATAL", "CRITICAL", "WARN")]
    selected_events = (prioritized[:18] or all_events[:18])[:18]
    for event in selected_events:
        # Ensure .source relation is already attached for build_package()
        _ = event.source
    package = build_package(str(incident.id), selected_events)
    snapshot = EvidenceSnapshot.objects.create(
        incident=incident,
        created_by=user,
        entries=package["entries"],
        sha256=package["sha256"],
        item_count=package["event_count"],
        characters=package["characters"],
        payload_bytes=package["payload_bytes"],
        selection_version=package["selection_version"],
        privacy_policy_version=package["privacy_policy_version"],
        consent_accepted_at=now,
    )

    return {
        "scenario_id": spec.id,
        "incident": incident,
        "sources_created": sources_created,
        "events_created": len(all_events),
        "snapshot_id": str(snapshot.id),
    }
