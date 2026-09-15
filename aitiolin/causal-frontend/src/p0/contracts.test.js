import { describe, expect, it } from "vitest"
import { evidenceStatus, finite, metric, sweepGeometry } from "./contracts.mjs"

describe("evidence presentation", () => {
  it("does not turn unavailable effects into zero", () => {
    for (const value of [null, undefined, "", " ", Infinity, NaN]) expect(finite(value)).toBe(null)
    expect(metric(0)).toBe("0.0000")
  })
  it("separates absent, failed and successful checks", () => {
    expect(evidenceStatus({})).toContain("Not run")
    expect(evidenceStatus({ status: "failed" })).toContain("contradiction")
    expect(evidenceStatus({ status: "passed" })).toContain("No contradiction")
  })
  it("does not fabricate a sensitivity curve", () => {
    expect(sweepGeometry([])).toBe(null)
    expect(sweepGeometry([{ confounder_strength: .1, adjusted_effect: null }])).toBe(null)
  })
})
