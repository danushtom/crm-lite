import { describe, expect, it } from "vitest";
import { timezoneLabel, timezoneOptions } from "@/lib/timezones";

describe("timezoneOptions", () => {
  it("offers the full IANA list, sorted, including UTC", () => {
    const zones = timezoneOptions();
    expect(zones.length).toBeGreaterThan(100);
    expect(zones).toContain("UTC");
    expect(zones).toContain("Europe/Paris");
    expect([...zones].sort()).toEqual(zones);
  });

  it("always includes the currently saved zone so a save cannot silently change it", () => {
    expect(timezoneOptions("Etc/GMT+5")).toContain("Etc/GMT+5");
  });
});

it("labels zones readably", () => {
  expect(timezoneLabel("America/Los_Angeles")).toBe("America/Los Angeles");
  expect(timezoneLabel("America/Argentina/Buenos_Aires")).toBe("America/Argentina/Buenos Aires");
});
