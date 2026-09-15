// Integration contract tests for the Vue HTTP wrapper; no network requests.
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
vi.mock("axios", () => ({ default: { request: vi.fn() } }))
import axios from "axios"
import client, { p0State, resolveReview } from "./client.js"
import { clearSessionStorage, sessionToken } from "./storage.js"

describe("P0 private client", () => {
  beforeEach(() => {
    axios.request.mockReset()
    sessionStorage.clear()
    p0State.seed = 42
    p0State.llmEnabled = false
    resolveReview(false)
  })
  it("sends a strong session token only to the same-origin API", async () => {
    axios.request.mockResolvedValue({ data: { ok: true } })
    await client.get("/api/p0/session/")
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
    await vi.waitFor(() => expect(p0State.review).not.toBeNull())
    resolveReview(false)
    await rejection
    expect(axios.request).toHaveBeenCalledTimes(1)
  })
  it("retries only after explicit approval with that payload permit", async () => {
    axios.request.mockRejectedValueOnce({ response: { data: { code: "llm_review_required",
      review: { approval_token: "approved-payload", payload: { messages: [] } } } } })
      .mockResolvedValueOnce({ data: { edges: [] } })
    const task = client.post("/api/openai/suggest_edges/", { variables: ["T", "Y"] })
    await vi.waitFor(() => expect(p0State.review).not.toBeNull())
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
    expect(sessionStorage.getItem("aitiolin-p0-session")).toBeNull()
    expect(sessionStorage.getItem("unrelated")).toBe("keep")
  })
  it("updates recorded-run state", async () => {
    const before = p0State.runRevision
    axios.request.mockResolvedValue({ data: { p0_run_id: "run-a" } })
    await client.post("/api/causal_inference/", {})
    expect(p0State.lastRun).toBe("run-a")
    expect(p0State.runRevision).toBe(before + 1)
  })
})
