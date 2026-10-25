import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiWrite } from "./api-client";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("uses same-origin credentials and does not cache account reads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ email: "a@example.org" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await apiGet<{ email: string }>("auth/me");
    expect(result.email).toBe("a@example.org");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/me", expect.objectContaining({ credentials: "same-origin", cache: "no-store" }));
  });

  it("fetches a CSRF token before a mutation and sends it as a header", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "csrf-example" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "incident-1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiWrite("incidents", "POST", { title: "Incident title" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/auth/csrf");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/incidents");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: "POST", credentials: "same-origin", headers: expect.objectContaining({ "X-CSRFToken": "csrf-example" }),
    }));
  });

  it("produces typed failures without exposing HTML", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not found." }), { status: 404 })));
    await expect(apiGet("incidents/unknown")).rejects.toMatchObject({ name: "ApiError", status: 404, message: "Not found." });
  });
});
