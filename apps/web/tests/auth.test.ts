import { describe, expect, it } from "vitest";
import { MIN_PASSWORD_LENGTH, safeNext, validateNewPassword } from "@/lib/auth";

describe("safeNext", () => {
  it("keeps same-origin paths, including their query", () => {
    expect(safeNext("/leads/42")).toBe("/leads/42");
    expect(safeNext("/auth/set-password?mode=invite")).toBe("/auth/set-password?mode=invite");
  });

  it.each([
    ["an absolute URL", "https://evil.test/phish"],
    ["a protocol-relative URL", "//evil.test"],
    ["a backslash trick browsers treat as protocol-relative", "/\\evil.test"],
    ["a javascript: URL", "javascript:alert(1)"],
    ["a relative path", "dashboard"],
    ["nothing", null],
    ["an empty string", ""],
  ])("falls back for %s", (_label, value) => {
    expect(safeNext(value)).toBe("/dashboard");
  });

  it("uses the caller's fallback", () => {
    expect(safeNext("//evil.test", "/login")).toBe("/login");
  });
});

describe("validateNewPassword", () => {
  const long = "x".repeat(MIN_PASSWORD_LENGTH);

  it("accepts a long enough matching pair", () => {
    expect(validateNewPassword(long, long)).toBeNull();
  });

  it("rejects a short password", () => {
    expect(validateNewPassword("short", "short")).toMatch(/at least/);
  });

  it("rejects a mismatch", () => {
    expect(validateNewPassword(long, long + "y")).toMatch(/do not match/);
  });
});
