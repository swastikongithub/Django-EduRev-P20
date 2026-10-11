import { describe, expect, it } from "vitest";

import { formatRupees, formatTime, formatWindow, fromIstInput, relativeTime, rupeesToPaise, toIstInput } from "./format";

describe("money", () => {
  it("shows whole rupees without decimals and keeps paise when needed", () => {
    expect(formatRupees(4000)).toBe("₹40");
    expect(formatRupees(123450)).toBe("₹1,234.50");
  });
  it("converts typed rupees to paise without floating point drift", () => {
    expect(rupeesToPaise("19.99")).toBe(1999);
    expect(rupeesToPaise("40")).toBe(4000);
  });
});

describe("time in IST", () => {
  it("formats in India time regardless of the machine's time zone", () => {
    expect(formatTime("2026-10-11T09:45:00Z")).toBe("3:15 pm");
  });
  it("round-trips datetime-local values as IST", () => {
    expect(toIstInput("2026-10-11T09:45:00Z")).toBe("2026-10-11T15:15");
    expect(fromIstInput("2026-10-11T15:15")).toBe("2026-10-11T09:45:00.000Z");
  });
  it("labels today and describes relative times", () => {
    const now = new Date("2026-10-11T08:00:00Z");
    expect(formatWindow("2026-10-11T09:30:00Z", "2026-10-11T10:15:00Z", now)).toBe("Today, 3:00 pm – 3:45 pm");
    expect(relativeTime("2026-10-11T08:42:00Z", now)).toBe("in 42 min");
    expect(relativeTime("2026-10-11T09:05:00Z", now)).toBe("in 1 h 5 min");
    expect(relativeTime("2026-10-11T07:55:00Z", now)).toBe("5 min ago");
  });
});
