# IncidentForge M6.3 — HAR-01 through HAR-07 evidence matrix

**Status:** preliminary / no release certification. A harness condition is marked **verified** only after the linked test or demonstration actually runs in the target environment. Existing implementation claims are not equivalent to completed evidence.

| Harness | Evidence path | M6.3 addition | Remaining independent gate |
|---|---|---|---|
| HAR-01 — standalone product | Existing Compose and incident workflow | Pinned 30-case offline evaluation | Fresh clone and full create→upload→analyze→review→export browser E2E, with retained artifacts |
| HAR-02 — UI/backend | Existing Next.js and Django tests | Offline runner test across production service boundary | Live Playwright workflow with browser assertions and CI wiring |
| HAR-03 — external API | Provider adapters and mock tests | Real provider optional benchmark with explicit consent | One separately authorized live smoke with safe recorded outcome and provider failure behavior |
| HAR-04 — substantive GenAI | Existing grounded report schema | Case fixtures, human-review template, structural and abstention metrics | Independent factual-precision and hypothesis-usefulness annotations, measured results |
| HAR-05 — parameter control | Model allowlist, temperature, tokens, profile | Pinned requested parameter metadata and call budget | Supported/effective parameter capability evidence and controlled evaluation |
| HAR-06 — prompting techniques | `zero_shot`, `few_shot`, `decomposed_verified` | Same-corpus three-profile runner | Measured, independently adjudicated live comparison with limitations |
| HAR-07 — failure handling | Existing timeouts, retries, authorization, redaction | Offline fail-closed citation, safety, privacy and integrity tests | Complete rate limit / cancellation / timeout / provider outage / browser recovery matrix |

**New deterministic gate:** `python -m pytest -q investigations/tests/test_m63_evaluation.py` + `python -m investigations.evals.cli --mode offline`; see `.github/workflows/m63-evaluation.yml`.

**Do not check every HAR box based on offline fake-adapter success.** Quantitative reports and release sign-off require actual test logs, commit SHA, dataset SHA, environment and reviewer agreement where appropriate.
