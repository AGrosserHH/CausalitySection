// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import RobustnessDashboard from "../components/RobustnessDashboard.vue"

describe("Evidence-first robustness dashboard", () => {
  it("places the heuristic score inside a closed disclosure", () => {
    const wrapper = mount(RobustnessDashboard, { props: { result: {
      baseline_estimate: 0, robustness_score: .82, refutations: {}, sensitivity_points: [] } } })
    const score = wrapper.get("details.secondary-score")
    expect(score.attributes("open")).toBeUndefined()
    expect(score.text()).toContain("82 / 100")
    expect(score.text()).toContain("not a confidence level")
  })
  it("does not present missing evidence as a zero estimate or passed test", () => {
    const wrapper = mount(RobustnessDashboard, { props: { result: {
      baseline_estimate: null, refutations: { placebo: { status: "unsupported" } } } } })
    expect(wrapper.text()).toContain("Not available")
    expect(wrapper.text()).toContain("Not run / unsupported")
    expect(wrapper.text()).toContain("No usable sensitivity curve")
  })
  it("renders a labelled sensitivity curve and exact values", () => {
    const wrapper = mount(RobustnessDashboard, { props: { result: { sensitivity_points: [
      { confounder_strength: 0, adjusted_effect: -.2 }, { confounder_strength: .5, adjusted_effect: .1 } ] } } })
    expect(wrapper.find("svg[role=img]").exists()).toBe(true)
    expect(wrapper.find("table caption").text()).toContain("strength")
    expect(wrapper.findAll("tbody tr")).toHaveLength(2)
  })
})
