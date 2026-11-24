# Architecture

IncidentForge uses a Next.js frontend and a modular Django REST API backed by PostgreSQL, private file storage, Redis, and Celery workers.

```text
Browser -> Next.js (same-origin /api/v1 proxy) -> Django REST API -> PostgreSQL
                                                      |     |
                                                      |     +-> Private evidence volume
                                                      +-> Redis -> Celery worker / beat
                                                                      +-> Interchangeable LLM adapter (opt-in)
```

## Service boundaries

- **Next.js (`web`)** owns the browser UI, session-aware views, and same-origin proxying to `/api/v1/*` and `/health/*`. It never connects directly to PostgreSQL, Redis, or external LLM providers.
- **Django REST API (`api`)** owns session/CSRF authentication, owner-scoped authorization, request validation, OpenAPI schema generation, deterministic analytics, human review revisions, and immutable postmortem downloads.
- **Celery (`worker` and `beat`)** runs durable, lease-fenced log ingestion, asynchronous AI investigations, periodic lease reconciliation, and opt-in retention cleanup (`purge_deleted_reports` and `purge_deleted_evidence`).
- **PostgreSQL (`postgres`)** stores domain state, normalized redacted log events, immutable evidence snapshots, AI investigation jobs/reports, append-only human reviews, and checksum-verified postmortem versions.
- **Redis (`redis`)** brokers Celery queues and rate-limit caches; it is never the system of record.
- **Evidence init (`evidence-init`)** initializes ownership and `0700` permissions on the private raw-evidence volume before `api` and `worker` start.

## Interchangeable AI Provider Boundary

External model execution lives behind the backend `LLMAdapter` interface in `apps/api/investigations/providers.py`. Current built-in profiles support OpenAI-compatible chat-completion endpoints (`groq`, `openai`, `openrouter`) using server-held API keys and allowlisted model IDs, while offline tests and deterministic evaluations substitute in-memory adapters.

All external model calls require explicit per-snapshot and per-run user consent, redacted evidence snapshots, fail-closed schema/citation/safety validation (`investigations/validation.py`), and never expose execution tools.

## Contracts & Deployment

The Compose stack contains `web`, `api`, `worker`, `beat`, `evidence-init`, `postgres`, and `redis`. Only `web` and `api` bind to `127.0.0.1`; PostgreSQL and Redis stay strictly on the internal bridge network. OpenAPI schemas and TypeScript client declarations are validated in CI via `scripts/verify-contract.sh` and `contracts/api-surface.json`.
