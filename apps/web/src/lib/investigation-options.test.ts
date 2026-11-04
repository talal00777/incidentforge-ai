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
