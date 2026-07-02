import { describe, expect, it } from "vitest"

import { getErrorMessage, useCausalApi } from "./useCausalApi"

describe("getErrorMessage", () => {
  it("returns API error if present", () => {
    const error = { response: { data: { error: "Bad request" } } }
    expect(getErrorMessage(error, "Fallback")).toBe("Bad request")
  })

  it("returns fallback when API error is missing", () => {
    expect(getErrorMessage({}, "Fallback")).toBe("Fallback")
  })
})

describe("useCausalApi", () => {
  it("calls save_graph endpoint", async () => {
    const mockClient = {
      post: async (url) => ({ data: { endpoint: url } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.saveGraph({ graph_id: 1 })

    expect(response.endpoint).toBe("/api/save_graph/")
  })

  it("calls openai suggest edges endpoint", async () => {
    const mockClient = {
      post: async (url) => ({ data: { endpoint: url } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.suggestEdges({ variables: ["A", "B"] })

    expect(response.endpoint).toBe("/api/openai/suggest_edges/")
  })

  it("calls time-series analysis endpoint", async () => {
    const mockClient = {
      post: async (url) => ({ data: { endpoint: url } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.runTimeSeriesAnalysis({ graph_id: 1, time_column: "timestamp" })

    expect(response.endpoint).toBe("/api/time_series_analysis/")
  })
})
