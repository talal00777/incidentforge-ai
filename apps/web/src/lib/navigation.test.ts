import { describe, expect, it } from "vitest";
import { primaryNavigation, secondaryNavigation } from "./navigation";

describe("workspace navigation", () => {
  it("only exposes routes that exist in the foundation", () => {
    const enabled = [...primaryNavigation, ...secondaryNavigation].filter((item) => item.href);
    expect(enabled).toEqual([{ label: "Overview", icon: "overview", href: "/" }]);
  });

  it("does not duplicate navigation labels", () => {
    const labels = [...primaryNavigation, ...secondaryNavigation].map((item) => item.label);
    expect(new Set(labels).size).toBe(labels.length);
  });
});
