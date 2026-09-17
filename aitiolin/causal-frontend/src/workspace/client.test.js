// Integration contract tests for the Vue HTTP wrapper; no network requests.
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
vi.mock("axios", () => ({ default: { request: vi.fn() } }))
import axios from "axios"
import client, { workspaceState, resolveReview } from "./client.js"
import { clearSessionStorage, sessionToken } from "./storage.js"

describe("private workspace client", () => {
  beforeEach(() => {
    axios.request.mockReset()
    sessionStorage.clear()
    workspaceState.seed = 42
    workspaceState.llmEnabled = false
    resolveReview(false)
  })
  it("sends a strong session token only to the same-origin API", async () => {
    axios.request.mockResolvedValue({ data: { ok: true } })
    await client.get("/api/workspace/session/")
    const options = axios.request.mock.calls[0][0]
    expect(options.headers["X-Aitiolin-Session"]).toMatch(/^[0-9a-f]{64}$/)
    expect(options.headers["X-Aitiolin-LLM-Mode"]).toBe("off")
    expect(options.baseURL).toBe(window.location.origin)
    await expect(client.get("https://example.invalid/api/collect")).rejects.toThrow()
    await expect(client.get("/api/../collect")).rejects.toThrow()
    expect(axios.request).toHaveBeenCalledTimes(1)
  })
  it("does not retry a cancelled LLM review", async () => {
    axios.request.mockRejectedValueOnce({ response: { data: { code: "llm_review_required",
      review: { approval_token: "approval", payload: { messages: [] } } } } })
    const task = client.post("/api/openai/suggest_edges/", { variables: ["T", "Y"] })
    const rejection = expect(task).rejects.toThrow("cancelled")
    await vi.waitFor(() => expect(workspaceState.review).not.toBeNull())
    resolveReview(false)
    await rejection
    expect(axios.request).toHaveBeenCalledTimes(1)
  })
  it("retries only after explicit approval with that payload permit", async () => {
    axios.request.mockRejectedValueOnce({ response: { data: { code: "llm_review_required",
      review: { approval_token: "approved-payload", payload: { messages: [] } } } } })
      .mockResolvedValueOnce({ data: { edges: [] } })
    const task = client.post("/api/openai/suggest_edges/", { variables: ["T", "Y"] })
    await vi.waitFor(() => expect(workspaceState.review).not.toBeNull())
    resolveReview(true)
    await task
    expect(axios.request.mock.calls[1][0].headers["X-Aitiolin-LLM-Approval"]).toBe("approved-payload")
  })
  it("allows the browser to set the multipart boundary", async () => {
    axios.request.mockResolvedValue({ data: {} })
    await client.post("/api/upload_csv/", new FormData(), { headers: { "Content-Type": "multipart/form-data" } })
    expect(axios.request.mock.calls[0][0].headers["Content-Type"]).toBeUndefined()
  })
  it("clears only this application's storage", () => {
    sessionStorage.setItem("unrelated", "keep")
    sessionToken()
    clearSessionStorage()
    expect(sessionStorage.getItem("aitiolin-session")).toBeNull()
    expect(sessionStorage.getItem("unrelated")).toBe("keep")
  })
  it("updates recorded-run state", async () => {
    const before = workspaceState.runRevision
    axios.request.mockResolvedValue({ data: { run_id: "run-a" } })
    await client.post("/api/causal_inference/", {})
    expect(workspaceState.lastRun).toBe("run-a")
    expect(workspaceState.runRevision).toBe(before + 1)
  })
  it("omits a cleared seed and rejects a non-integer one before sending", async () => {
    axios.request.mockResolvedValue({ data: {} })
    workspaceState.seed = ""
    await client.get("/api/workspace/session/")
    expect(axios.request.mock.calls[0][0].headers["X-Aitiolin-Seed"]).toBeUndefined()
    workspaceState.seed = 7
    await client.get("/api/workspace/session/")
    expect(axios.request.mock.calls[1][0].headers["X-Aitiolin-Seed"]).toBe("7")
    workspaceState.seed = 1.5
    await expect(client.get("/api/workspace/session/")).rejects.toThrow("whole number")
    expect(axios.request).toHaveBeenCalledTimes(2)
  })
})
