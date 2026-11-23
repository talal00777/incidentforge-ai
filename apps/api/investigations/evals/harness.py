"""Conservative HAR-01..07 evidence ledger; offline tests cannot certify a release."""

HARNESS = {
    "HAR-01": {
        "requirement": "Stand-alone investigation workflow",
        "m63_evidence": "30-case offline reference evaluation and existing Compose build",
        "remaining_gate": "Fresh-clone authenticated browser end-to-end demonstration",
    },
    "HAR-02": {
        "requirement": "Operational frontend and backend",
        "m63_evidence": "Existing Django and Next.js suites; production service invocation",
        "remaining_gate": "Playwright incident workflow executed in CI",
    },
    "HAR-03": {
        "requirement": "Internal and external API integration",
        "m63_evidence": "Provider adapter contract; offline fake adapter never uses network",
        "remaining_gate": "Separate approved real-provider smoke test",
    },
    "HAR-04": {
        "requirement": "Substantive evidence-grounded AI generation",
        "m63_evidence": "Pinned case corpus and human fact/hypothesis adjudication template",
        "remaining_gate": "Independently scored real generated reports",
    },
    "HAR-05": {
        "requirement": "Supported and measured inference parameters",
        "m63_evidence": "Model/temperature/token/profile metadata and live call budget",
        "remaining_gate": "Effective-parameter capability test and controlled results",
    },
    "HAR-06": {
        "requirement": "Two distinct prompting techniques",
        "m63_evidence": "All three profiles exercise production service with fake adapter",
        "remaining_gate": "Actual live three-profile ablation and review",
    },
    "HAR-07": {
        "requirement": "Safe error handling",
        "m63_evidence": "Tampered fixtures, unknown citations, privacy and unsafe-action rejection",
        "remaining_gate": "Complete browser/provider timeout, rate-limit, cancellation and fault suite",
    },
}


def pending_ledger() -> dict:
    """Return ALL conditions pending until independent proof is attached and reviewed."""
    return {key: {"status": "pending_release_evidence", **value} for key, value in HARNESS.items()}
