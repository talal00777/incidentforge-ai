export type ProviderOption = { name: string; models: string[]; available: boolean };

export function availableProviders(options: ProviderOption[]): ProviderOption[] {
  return options
    .filter((item) => item.available && item.name.trim().length > 0)
    .map((item) => ({ ...item, models: [...new Set(item.models.filter((model) => model.trim()))] }))
    .filter((item) => item.models.length > 0);
}

export function firstModel(options: ProviderOption[], provider: string): string {
  return availableProviders(options).find((item) => item.name === provider)?.models[0] ?? "";
}

export function canInvestigate(snapshotId: string, provider: string, model: string, consented: boolean, working: boolean): boolean {
  return Boolean(snapshotId.trim() && provider.trim() && model.trim() && consented && !working);
}
