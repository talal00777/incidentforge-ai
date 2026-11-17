import { describe, expect, it } from "vitest";

import { availableProviders, canInvestigate, firstModel } from "./investigation-options";

describe("investigation configuration", () => {
  const options = [
    { name: "groq", models: ["model-a", "model-b"], available: true },
    { name: "openai", models: ["model-c"], available: false },
  ];

  it("shows configured providers and their approved models only", () => {
    expect(availableProviders(options).map((item) => item.name)).toEqual(["groq"]);
    expect(firstModel(options, "groq")).toBe("model-a");
    expect(firstModel(options, "openai")).toBe("");
  });

  it("requires fresh consent and a valid selection", () => {
    expect(canInvestigate("snapshot", "groq", "model-a", true, false)).toBe(true);
    expect(canInvestigate("snapshot", "groq", "model-a", false, false)).toBe(false);
    expect(canInvestigate("", "groq", "model-a", true, false)).toBe(false);
    expect(canInvestigate("snapshot", "groq", "model-a", true, true)).toBe(false);
  });
});


describe("provider configuration validation", () => {
  it("drops providers without actual models and removes duplicate identifiers", () => {
    const providers = [
      { name: "primary", models: ["", "model-x", "model-x", " ", "model-y"], available: true },
      { name: "empty", models: [" ", ""], available: true },
    ];
    expect(availableProviders(providers)).toEqual([{
      name: "primary", models: ["model-x", "model-y"], available: true,
    }]);
    expect(firstModel(providers, "empty")).toBe("");
  });
  it("does not submit blank identifiers despite a checked consent box", () => {
    expect(canInvestigate(" ", "provider", "model", true, false)).toBe(false);
    expect(canInvestigate("snap", "provider", " ", true, false)).toBe(false);
  });
});
