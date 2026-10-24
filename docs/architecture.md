# Architecture

IncidentForge uses a Next.js frontend and a Django REST API. PostgreSQL stores application data; Redis brokers Celery background jobs.

```text
Browser -> Next.js -> Django REST API -> PostgreSQL
                       |
                       +-> Redis -> Celery worker
```

The frontend obtains service readiness through the API. Health checks distinguish process liveness from database/Redis readiness. The backend owns validation and persistent state; the browser does not access PostgreSQL or Redis directly.

The Compose stack contains `web`, `api`, `worker`, `postgres`, and `redis`. The web and API ports bind to the local host. Database and broker traffic stays on the Compose network.

OpenAPI is generated from Django, and contract checks run in CI. Authentication, incident ingestion, investigation, and external model integrations require separate implementation and security review before use with real incident data.
