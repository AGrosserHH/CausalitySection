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

  it("calls agent profile endpoint with graph id payload", async () => {
    const mockClient = {
      post: async (url, payload) => ({ data: { endpoint: url, payload } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.agentProfileData(7)

    expect(response.endpoint).toBe("/api/agent/profile/")
    expect(response.payload).toEqual({ graph_id: 7 })
  })

  it("calls agent suggest cleaning endpoint", async () => {
    const mockClient = {
      post: async (url, payload) => ({ data: { endpoint: url, payload } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.agentSuggestCleaning(7)

    expect(response.endpoint).toBe("/api/agent/suggest_cleaning/")
    expect(response.payload).toEqual({ graph_id: 7 })
  })

  it("calls agent apply cleaning endpoint", async () => {
    const mockClient = {
      post: async (url, payload) => ({ data: { endpoint: url, payload } }),
    }

    const api = useCausalApi(mockClient)
    const steps = [{ step_id: "drop_column:customerID", step_type: "drop_column", column: "customerID" }]
    const response = await api.agentApplyCleaning({ graph_id: 7, steps })

    expect(response.endpoint).toBe("/api/agent/apply_cleaning/")
    expect(response.payload.steps).toHaveLength(1)
  })

  it("calls agent estimate plan endpoint", async () => {
    const mockClient = {
      post: async (url, payload) => ({ data: { endpoint: url, payload } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.agentEstimatePlan({ graph_id: 7, treatment: 1, outcome: 2 })

    expect(response.endpoint).toBe("/api/agent/estimate_plan/")
    expect(response.payload).toEqual({ graph_id: 7, treatment: 1, outcome: 2 })
  })

  it("calls agent suggest model endpoint", async () => {
    const mockClient = {
      post: async (url, payload) => ({ data: { endpoint: url, payload } }),
    }

    const api = useCausalApi(mockClient)
    const response = await api.agentSuggestModel({ graph_id: 7, max_edges: 12 })

    expect(response.endpoint).toBe("/api/agent/suggest_model/")
    expect(response.payload.graph_id).toBe(7)
  })
})
