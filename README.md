# IncidentForge

IncidentForge is a web application for evidence-grounded software incident investigation, deterministic log analytics, human-in-the-loop AI synthesis, and immutable postmortem reporting.

## Stack

- Next.js, React, TypeScript (generated OpenAPI client types)
- Django, Django REST Framework, Celery, Celery Beat
- PostgreSQL, Redis, Matplotlib/Seaborn, ReportLab
- Interchangeable backend LLM provider adapters (Groq, OpenAI, OpenRouter)
- Docker Compose

## Implemented Capabilities

- Session/CSRF authentication and owner-scoped incident CRUD with audit logging
- Bounded multipart log upload (`.log`, `.txt`, `.json`, `.jsonl`), streaming parsers, multiline stack traces, redaction, and idempotent Celery ingestion
- Deterministic analytics (normalized fingerprinting, time-bucket aggregations, leave-one-out MAD anomaly detection, trace/request correlation, and Matplotlib/Seaborn charts)
- Redacted immutable evidence snapshots with per-snapshot and per-run transfer consent
- Asynchronous Celery-backed AI investigations with `zero_shot`, `few_shot`, and 3-stage `decomposed_verified` (extract -> synthesize -> critique) prompting, strict citation validation, unsafe-action screening, cancellation, and reconciliation
- Append-only human review revisions and immutable SHA-256 postmortem versions with deterministic PDF and canonical JSON exports
- Pinned 30-case synthetic offline evaluation suite (`apps/api/investigations/evals`)

## Local setup

Requires Docker Engine or Docker Desktop with Compose v2.

```powershell
Copy-Item .env.example .env
# Review local configuration in .env before starting services.
docker compose up --build -d --wait
docker compose ps
```

The database host in `.env` must be `postgres` when accessed from the Compose network.

- Web UI: http://localhost:3000
- API readiness: http://localhost:8000/health/ready
- API schema: http://localhost:8000/api/v1/openapi/
- API reference: http://localhost:8000/api/v1/docs/

Stop services with `docker compose down`. This preserves the PostgreSQL volume.

## Source layout

```text
apps/web/       Next.js application and Playwright/Vitest suites
apps/api/       Django API, Celery worker/beat, and evaluation suite
contracts/      OpenAPI contract policy and verification specs
scripts/        Contract validation utilities
docs/           Architecture, development, and evaluation documentation
compose.yaml    Local service configuration
```

See [Development](docs/development.md) for checks and troubleshooting, [Architecture](docs/architecture.md) for service boundaries, and [Evaluation Methodology](docs/M6_3_EVALUATION_METHODOLOGY.md) for reproducible offline evaluation details.

## License

No license has been assigned.
