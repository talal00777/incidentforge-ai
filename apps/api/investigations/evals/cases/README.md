# IncidentForge M6.3 synthetic evaluation corpus

`incidents-v1.jsonl` contains 30 synthetic, human-authored incident scenarios and explicit reference annotations. It is not sampled from customer, university, or production logs. The dataset is pinned by the SHA-256 in `manifest.json`; any edit requires a new reviewed dataset version and manifest update. Do not modify fixtures after viewing live model results, because this would compromise the comparison.

The six categories are clear evidence (6), cross-service evidence (6), misleading correlation (5), insufficient evidence (5), prompt-injection attempts in log **data** (4), and sanitized malformed/privacy-related records (4). These intentionally vary the evidence strength and expected abstention. A `gold.hypothesis` is a plausible *annotation for study*, **not** a proven diagnosis. Each case records the expected factual observation, plausible hypothesis, alternative, next check, counterevidence where present, and limitations.

The offline runner returns the authored reference reports through a fake adapter to exercise the *production* `run_investigation` validator and evidence-citation boundary. Its 100% scores are **test-fixture behavior, not measured model accuracy**. Live experiments are separate and opt-in. Human review is required before claiming factual precision or hypothesis usefulness.
