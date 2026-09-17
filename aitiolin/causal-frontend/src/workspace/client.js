import axios from "axios"
import { reactive } from "vue"
import { sessionToken } from "./storage.js"

export const DEFAULT_SEED = 42
export const MAX_SEED = 4294967295
export const workspaceState = reactive({ pending: 0, seed: DEFAULT_SEED, llmEnabled: false, review: null,
  lastRun: null, runRevision: 0 })

// A cleared <input type=number> reads as "": omit the header so the server default applies,
// instead of sending a value the guard has to reject. Anything else non-integer is a caller error.
export function seedHeader(value) {
  if (value === "" || value === null || value === undefined) return null
  if (!Number.isInteger(value) || value < 0 || value > MAX_SEED) {
    throw new Error(`Analysis seed must be a whole number between 0 and ${MAX_SEED}.`)
  }
  return String(value)
}
let reviewResolver = null
let queue = Promise.resolve()

export function resolveReview(approved) {
  const resolve = reviewResolver
  reviewResolver = null
  workspaceState.review = null
  resolve?.(Boolean(approved))
}

async function requestReview(review) {
  if (reviewResolver) throw new Error("Another privacy review is already open.")
  workspaceState.review = review
  return new Promise(resolve => { reviewResolver = resolve })
}

function enqueue(work) {
  workspaceState.pending += 1
  const task = queue.then(work)
  queue = task.catch(() => {})
  return task.finally(() => { workspaceState.pending -= 1 })
}

async function execute(method, url, data, config = {}) {
  // Only same-origin API paths receive the secret. Never attach it to external URLs.
  if (typeof url !== "string" || !url.startsWith("/api/") || url.includes("..")) {
    throw new Error("Only same-origin API routes are permitted.")
  }
  const headers = { ...config.headers,
    "X-Aitiolin-Session": sessionToken(),
    "X-Aitiolin-LLM-Mode": workspaceState.llmEnabled ? "review" : "off" }
  const seed = seedHeader(workspaceState.seed)
  if (seed !== null) headers["X-Aitiolin-Seed"] = seed
  // Let the browser supply a multipart boundary.
  if (data instanceof FormData) delete headers["Content-Type"]
  const options = { ...config, baseURL: window.location.origin, method, url, data, headers, withCredentials: false }
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const response = await axios.request(options)
      if (response.data?.run_id) {
        workspaceState.lastRun = response.data.run_id
        workspaceState.runRevision += 1
      }
      return response
    } catch (error) {
      let body = error.response?.data
      if (body instanceof Blob) {
        try { body = JSON.parse(await body.text()) } catch { body = null }
      }
      if (body?.code === "llm_review_required") {
        const approved = await requestReview(body.review)
        if (!approved) {
          const cancelled = new Error("LLM request cancelled. Nothing was sent by this action.")
          cancelled.response = { data: { error: cancelled.message } }
          throw cancelled
        }
        options.headers["X-Aitiolin-LLM-Approval"] = body.review.approval_token
        continue
      }
      if (body?.code === "session_busy" && attempt < 3) {
        await new Promise(resolve => setTimeout(resolve, 400 * (attempt + 1)))
        continue
      }
      throw error
    }
  }
  throw new Error("The request changed or the session stayed busy. Review the state and retry.")
}

const client = {
  get: (url, config) => enqueue(() => execute("get", url, undefined, config)),
  post: (url, data, config) => enqueue(() => execute("post", url, data, config)),
  patch: (url, data, config) => enqueue(() => execute("patch", url, data, config)),
  delete: (url, config) => enqueue(() => execute("delete", url, undefined, config)),
}
export default client
