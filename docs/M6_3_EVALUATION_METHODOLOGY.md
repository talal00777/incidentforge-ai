# M6.3 — IncidentForge evaluation methodology

**Document:** IF-EVAL-001-PUBLIC · **Status:** engineering protocol, not evidence of measured model quality. **Baseline:** `main` containing `c58122a`. Private acceptance amendments are stored in the sibling `incidentforge-private` folder, never in this repository.

## Scope and reproducibility

The pinned `apps/api/investigations/evals/cases/incidents-v1.jsonl` contains 30 synthetic and independently authored scenarios covering: clear diagnostics (6), multi-service incidents (6), misleading correlation (5), insufficient/contradictory evidence (5), prompt-injection content in logs (4), and safe malformed/privacy examples (4). See `manifest.json` for the SHA-256. Case text is intentionally permission-cleared and must not be replaced with actual production logs in live evaluation.

Evaluation calls **existing production** `investigations.service.run_investigation`, which invokes `investigations.prompts.messages_for`, `ChatCompletionsAdapter` when explicitly enabled, and authoritative `validate_facts` / `validate_report`. No separate evaluation model backend or new API routes are created.

## Offline mode — required CI gate

From `apps/api` with backend dev dependencies installed:

```bash
python -m pytest -q investigations/tests/test_m63_evaluation.py
python -m investigations.evals.cli --mode offline
```

The CLI uses an **authored reference-output adapter** in place of a generative model. This checks all 30 cases across `zero_shot`, `few_shot`, and `decomposed_verified` (90 report paths, plus the extraction stage of decomposed runs), production output validation, source membership, redaction eligibility and safety invariants. It cannot prove that an actual LLM generated correct findings. A 100% offline citation score is **expected behavior of a test fixture**, not evidence of GenAI model accuracy.

By default results go to `../incidentforge-private/evaluation-results/m63-<UTC timestamp>/`, not the public repository. `runs.json` contains synthetic validated reports; `summary.json` labels unmeasured semantic fields as `null`; `human-review.csv` is a blank independent adjudication form. CI uses a temporary directory and uploads only synthetic offline artifacts.

## Live mode — explicit operator authorization only

All of the following are mandatory: pinned corpus integrity, production redaction gate, `INCIDENTFORGE_EVAL_LIVE=1`, `--mode live`, `--confirm-synthetic-transfer`, `--provider`, `--model`, `--limit`, and a bounded provider-call budget. **Never enable this mode in CI.** For example, from `apps/api`, after configuring server-held provider credentials in the local environment:

```bash
INCIDENTFORGE_EVAL_LIVE=1 python -m investigations.evals.cli \
  --mode live --confirm-synthetic-transfer \
  --provider openai --model <server-approved-model> \
  --profiles zero_shot few_shot decomposed_verified \
  --limit 1 --max-live-calls 4
```

Use the actual model identifier from your provider allowlist. The profile comparison should keep the *same provider, model, pinned corpus, prompts, evidence, supported temperature, output-token budget and run environment*. A `decomposed_verified` run uses three provider calls (fact extraction, report synthesis, and independent grounded critique); quota and latency must be compared on that basis. Use `--temperatures 0.0 0.2 0.7` for controlled temperature sweeps where supported. The service logs requested parameters, not provider-guaranteed effective values. If unsupported, provider rejection is recorded as an error, not silently reinterpreted.

## Metrics and interpretation

| Measure | Automated? | Meaning / limitation |
|---|---|---|
| `validation_rate` | Yes | Fraction accepted by the production schema/evidence validator; invalid outputs are failures |
| `citation_membership_rate_on_validated` | Yes | Strict invariant for valid reports; must not be mistaken for semantic groundedness |
| `abstention_match_rate_on_validated` | Yes | Match between label and supported status vocabulary; limited by the reference annotations |
| `exact_fact_anchor_coverage_on_validated` | Yes | Conservative phrase/event-ID check, sensitive to paraphrasing; **not observed-fact precision** |
| `observed_fact_precision` | No | Requires independent review of each generated fact against source evidence |
| `hypothesis_usefulness` | No | Requires reviewer rubric accounting for alternatives, risk and appropriate caution |
| tokens / latency | Live only | Report token usage when available; compare per case and per provider call |

Independent reviewers should annotate each live `human-review.csv` row with `0` or `1` and notes. Do not combine unchecked blanks into quantitative claims. Do not treat sparse or misleading synthetic fixtures as proof of real-world performance. If later adding reviewer agreement, specify agreement statistics and adjudication protocol before measuring.

## Release gating

The M6.3 offline gate tests the deterministic harness and confirms absence of unauthorized outbound calls under fake adapters. It does not alone prove HAR-01–HAR-07 are complete. `M6_3_HARNESS_MATRIX.md` documents the missing independent proofs. Full P0 readiness requires real end-to-end browser workflow, auth/cross-user checks, private exports, fault injection, and an opt-in documented live provider smoke test as described in IF-SPEC-001 and IF-ARCH-001.

## Safety and integrity

- Uploaded logs, filenames, IDs and model completions remain untrusted; no model output may execute remediation.
- Only synthetic fixed cases with validated SHA-256 and `_safe_text` redaction checks can be transmitted during live tests.
- Offline tests must never require external credentials or network access.
- Keep private specs, credentials, raw live outputs, human reviews and results outside the public Git repository.
- No evaluation result should be presented as a calibrated root-cause probability.
