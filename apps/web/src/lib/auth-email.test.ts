import { describe, expect, it } from "vitest";
import { normalizeAccountEmail } from "./auth-email";

describe("account email", () => {
  it("strips accidental spacing and normalizes case", () => {
    expect(normalizeAccountEmail("  Person@Example.ORG  ")).toBe("person@example.org");
  });
});
