"""Provider-neutral investigation orchestration and evidence-bound validation."""

from investigations.prompts import FACTS_SCHEMA, PROMPT_VERSION, REPORT_SCHEMA, messages_for
from investigations.providers import ChatCompletionsAdapter
from investigations.validation import validate_facts, validate_report


def run_investigation(
    *, provider, model, entries, temperature, max_tokens, prompt_profile, adapter=None
):
    client = adapter if adapter is not None else ChatCompletionsAdapter(provider)
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}

    def call(messages, schema, token_limit):
        result, usage = client.complete(
            model=model,
            messages=messages,
            schema=schema,
            temperature=temperature,
            max_tokens=token_limit,
        )
        for field in usage_total:
            value = usage.get(field)
            if isinstance(value, int) and value >= 0:
                usage_total[field] += value
        return result

    observed = None
    if prompt_profile == "decomposed_verified":
        observed = validate_facts(
            call(messages_for("extract", entries), FACTS_SCHEMA, min(max_tokens, 1024)), entries
        )

    report = call(
        messages_for(prompt_profile, entries, observed=observed), REPORT_SCHEMA, max_tokens
    )
    return validate_report(report, entries), usage_total, PROMPT_VERSION
