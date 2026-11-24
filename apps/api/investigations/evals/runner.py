"""Exercise production investigation orchestration, prompt profiles and citation validator."""

import copy
import json
import time
from dataclasses import dataclass

from investigations.evals.scoring import score_valid_report


@dataclass
class ReferenceAdapter:
    """Offline invariant fixture. NEVER use its outputs as empirical LLM results."""

    case: dict

    def complete(self, *, model, messages, schema, temperature, max_tokens):
        from investigations.prompts import FACTS_SCHEMA

        if model != "offline-reference":
            raise ValueError("The reference adapter can only be used in offline mode")
        supplied = json.loads(messages[-1]["content"])
        if {event["event_id"] for event in supplied["events"]} != {
            event["event_id"] for event in self.case["entries"]
        }:
            raise ValueError("Evaluation evidence diverged from case under test")
        if schema == FACTS_SCHEMA:
            report = reference_report(self.case)
            return {
                "observed_facts": copy.deepcopy(report["observed_facts"]),
                "limitations": copy.deepcopy(report["limitations"]),
            }, {}
        if supplied.get("task") == "verify":
            if "draft_report" not in supplied or "extracted_facts" not in supplied:
                raise ValueError("Verification stage must receive extracted_facts and draft_report")
        return reference_report(self.case), {}


def reference_report(case: dict) -> dict:
    """Translate annotations to the production contract; never call an LLM."""
    gold = case["gold"]
    first_id = case["entries"][0]["event_id"]
    abstain = gold["expected_abstention"]
    return {
        "schema_version": "1.0",
        "incident_summary": (
            "A synthetic incident was observed; evidence does not establish its cause."
            if abstain
            else "Synthetic incident evidence supports further investigation; cause unconfirmed."
        ),
        "observed_facts": [
            {
                "statement": gold["observed_fact"].capitalize() + ".",
                "event_ids": list(gold["observed_event_ids"]),
            }
        ],
        "hypotheses": [
            {
                "title": gold["hypothesis"],
                "status": "insufficient_evidence" if abstain else "plausible_unconfirmed",
                "supporting_event_ids": [] if abstain else list(gold["observed_event_ids"]),
                "contradicting_event_ids": list(gold["counterevidence_ids"]),
                "alternative_explanations": [gold["alternative"]],
                "further_checks": [gold["check"]],
            }
        ],
        "suggested_actions": [
            {
                "action": gold["check"],
                "safety": "review_only",
                "rationale_event_ids": [first_id],
            }
        ],
        "limitations": list(gold["limitations"]),
    }


def run_case(
    case: dict,
    profile: str,
    *,
    mode: str,
    provider=None,
    model=None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> dict:
    from investigations.evals.dataset import PROFILES
    from investigations.prompts import prompt_sha256
    from investigations.providers import ProviderFailure
    from investigations.service import run_investigation

    if profile not in PROFILES:
        raise ValueError("Unsupported prompt profile")
    if mode not in {"offline", "live"}:
        raise ValueError("Unsupported evaluation mode")
    adapter = ReferenceAdapter(case) if mode == "offline" else None
    model_id = "offline-reference" if mode == "offline" else model
    start = time.perf_counter()
    output = {
        "case_id": case["case_id"],
        "category": case["category"],
        "profile": profile,
        "temperature": temperature,
        "provider_calls": 3 if profile == "decomposed_verified" else 1,
        "valid": False,
        "error_code": None,
        "latency_ms": None,
        "scores": None,
        "token_usage": None,
        "report": None,
        "prompt_version": None,
        "prompt_sha256": prompt_sha256(profile),
    }
    try:
        report, usage, prompt_version = run_investigation(
            provider=provider,
            model=model_id,
            entries=case["entries"],
            temperature=temperature,
            max_tokens=max_tokens,
            prompt_profile=profile,
            adapter=adapter,
        )
        output["valid"] = True
        output["report"] = report
        output["prompt_version"] = prompt_version
        output["scores"] = score_valid_report(report, case)
        if (
            mode == "live"
            and isinstance(usage, dict)
            and any(
                type(usage.get(field)) is int and usage[field] > 0
                for field in ("prompt_tokens", "completion_tokens")
            )
        ):
            output["token_usage"] = {
                "prompt_tokens": max(0, usage.get("prompt_tokens", 0)),
                "completion_tokens": max(0, usage.get("completion_tokens", 0)),
            }
    except ProviderFailure as exc:
        output["error_code"] = exc.code  # Safe internal code; no provider body.
    finally:
        if mode == "live":
            output["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    return output
