export type ProviderOption = { name: string; models: string[]; available: boolean };

export function availableProviders(options: ProviderOption[]): ProviderOption[] {
  return options.filter((item) => item.available && item.models.length > 0);
}

export function firstModel(options: ProviderOption[], provider: string): string {
  return options.find((item) => item.name === provider && item.available)?.models[0] ?? "";
}

export function canInvestigate(snapshotId: string, provider: string, model: string, consented: boolean, working: boolean): boolean {
  return Boolean(snapshotId && provider && model && consented && !working);
}
