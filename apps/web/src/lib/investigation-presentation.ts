export type TimeDisplay = "local" | "utc";

type SuggestedAction = {
  action: string;
  safety: string;
  rationale_event_ids: string[];
};

const STATUS_LABELS: Record<string, { label: string; meaning: string }> = {
  supported_but_not_proven: {
    label: "Supported, not confirmed",
    meaning: "Cited evidence supports this hypothesis, but causation has not been established.",
  },
  plausible_unconfirmed: {
    label: "Plausible, unconfirmed",
    meaning: "Possible explanation; the available evidence does not confirm it.",
  },
  contradicted: {
    label: "Contradicted",
    meaning: "Available evidence conflicts with this hypothesis.",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    meaning: "There is not enough evidence to assess this hypothesis.",
  },
};

export function hypothesisStatus(status: string) {
  return STATUS_LABELS[status] ?? {
    label: "Unclassified",
    meaning: "No recognized assessment is available.",
  };
}

export function readableInvestigationDate(value: string | null | undefined, display: TimeDisplay): string {
  if (!value) return "Time unknown";
  const time = new Date(value);
  if (Number.isNaN(time.valueOf())) return "Time unknown";
  const date = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: display === "utc" ? "UTC" : undefined,
  }).format(time);
  return `${date} ${display === "utc" ? "UTC" : "local"}`;
}

function checkKey(value: string): string {
  return value.trim().replace(/[\s]+/g, " ").replace(/[.!?]+$/, "").toLocaleLowerCase("en");
}

/** De-duplicate visible checks while retaining every source-event reference. */
export function mergeSuggestedActions(actions: readonly SuggestedAction[]): SuggestedAction[] {
  const merged = new Map<string, SuggestedAction>();
  for (const item of actions) {
    const key = checkKey(item.action);
    const previous = merged.get(key);
    if (!previous) {
      merged.set(key, { ...item, rationale_event_ids: [...new Set(item.rationale_event_ids)] });
      continue;
    }
    merged.set(key, {
      ...previous,
      rationale_event_ids: [...new Set([...previous.rationale_event_ids, ...item.rationale_event_ids])],
    });
  }
  return [...merged.values()];
}

/** Hide repeated hypothesis checks already included in the main action list. */
export function distinctHypothesisChecks(checks: readonly string[], actions: readonly string[]): string[] {
  const seen = new Set(actions.map(checkKey));
  const output: string[] = [];
  for (const check of checks) {
    const key = checkKey(check);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    output.push(check);
  }
  return output;
}
