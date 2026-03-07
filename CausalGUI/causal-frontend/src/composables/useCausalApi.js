import axios from "axios"

function getErrorMessage(error, fallbackMessage) {
  if (error?.response?.data?.error) {
    return error.response.data.error
  }
  return fallbackMessage
}

export function useCausalApi(httpClient = axios) {
  async function uploadCsv(file) {
    const formData = new FormData()
    formData.append("file", file)

    const response = await httpClient.post("/api/upload_csv/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    return response.data
  }

  async function saveGraph(payload) {
    const response = await httpClient.post("/api/save_graph/", payload)
    return response.data
  }

  async function runInference(payload) {
    const response = await httpClient.post("/api/causal_inference/", payload)
    return response.data
  }

  async function suggestEdges(payload) {
    const response = await httpClient.post("/api/openai/suggest_edges/", payload)
    return response.data
  }

  async function draftGraph(payload) {
    const response = await httpClient.post("/api/openai/draft_graph/", payload)
    return response.data
  }

  async function assessQuery(payload) {
    const response = await httpClient.post("/api/assess_query/", payload)
    return response.data
  }

  async function fetchGraphDetails(graphId) {
    const response = await httpClient.get(`/api/graphs/${graphId}/`)
    return response.data
  }

  async function runRobustnessDashboard(payload) {
    const response = await httpClient.post("/api/robustness_dashboard/", payload)
    return response.data
  }

  async function runWhatIfAnalysis(payload) {
    const response = await httpClient.post("/api/what_if_analysis/", payload)
    return response.data
  }

  async function runRootCauseAnalysis(payload) {
    const response = await httpClient.post("/api/root_cause_analysis/", payload)
    return response.data
  }

  return {
    uploadCsv,
    saveGraph,
    runInference,
    suggestEdges,
    draftGraph,
    assessQuery,
    fetchGraphDetails,
    runRobustnessDashboard,
    runWhatIfAnalysis,
    runRootCauseAnalysis,
    getErrorMessage,
  }
}

export { getErrorMessage }
