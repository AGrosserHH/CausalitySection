<template>
  <div class="app-container">
    <DatasetSidebar
      :variables="variables"
      :dataset-name="datasetName"
      :graph-id="graphId"
      :preview-rows="datasetPreviewRows"
      @file-upload="handleFileUpload"
    />

    <main class="main-content">
      <header class="page-header">
        <h1 class="title">Causal AI Graph Builder</h1>
        <p class="subtitle">Build a causal graph by dragging variables, then save and run inference.</p>
      </header>

      <div v-if="statusMessage" :class="['status-banner', statusType]">
        {{ statusMessage }}
      </div>

      <section class="workspace-layout">
        <div class="graph-panel">
          <div class="graph-toolbar">
            <span class="toolbar-title">Graph Canvas</span>
            <span class="toolbar-hint">Drag variables in, drag from a node handle or right-drag between nodes to connect, shift-drag to box-select, and use Delete, Undo, or Zoom controls as needed.</span>
          </div>
          <div class="legend-row">
            <div class="legend-group">
              <span class="legend-label">Query badge:</span>
              <span class="legend-chip legend-trust"><span aria-hidden="true">*</span> <span class="sr-only">Query badge:</span>trust</span>
              <span class="legend-chip legend-caution"><span aria-hidden="true">^</span> <span class="sr-only">Query badge:</span>caution</span>
              <span class="legend-chip legend-reject"><span aria-hidden="true">x</span> <span class="sr-only">Query badge:</span>reject</span>
            </div>
            <div class="legend-group">
              <span class="legend-label">Edge status:</span>
              <span class="legend-chip legend-supported"><span aria-hidden="true">*</span> <span class="sr-only">Edge status:</span>supported</span>
              <span class="legend-chip legend-weak"><span aria-hidden="true">^</span> <span class="sr-only">Edge status:</span>weak</span>
              <span class="legend-chip legend-conflict"><span aria-hidden="true">x</span> <span class="sr-only">Edge status:</span>conflict</span>
              <span class="legend-chip legend-manual"><span aria-hidden="true">L</span> <span class="sr-only">Edge status:</span>manual lock</span>
            </div>
          </div>
          <GraphCanvas
            ref="graphCanvasRef"
            class="graph-canvas-host"
            :variables="variables"
            :snapshot-key="graphCanvasSnapshotKey"
            @graph-change="handleGraphChange"
            @selection-change="handleGraphSelection"
          />
        </div>

        <GraphControls
          class="controls-column"
          :variables="variables"
          :selected-treatment="selectedTreatment"
          :selected-outcome="selectedOutcome"
          :selected-method="selectedMethod"
          :has-graph="graphCanvasState.nodeCount > 0"
          :can-undo="graphCanvasState.canUndo"
          :can-redo="graphCanvasState.canRedo"
          @update:selected-treatment="selectedTreatment = $event"
          @update:selected-outcome="selectedOutcome = $event"
          @update:selected-method="selectedMethod = $event"
          @save="saveGraph"
          @suggest="suggestGraphEdges"
          @relayout="relayoutGraph"
          @delete-selected="deleteSelectedGraphElements"
          @undo="undoGraphEdit"
          @redo="redoGraphEdit"
          @zoom-in="zoomInGraph"
          @zoom-out="zoomOutGraph"
          @fit="fitGraphToView"
          @center="centerGraphInView"
          @run="computeInference"
          @reset="resetAnalysisWorkspace"
        />
      </section>

      <section v-if="selectedGraphElement || graphCanvasState.nodeCount" class="selection-panel">
        <div class="assessment-header">
          <h3 class="assessment-title">Canvas Details</h3>
          <span class="legend-label">
            {{ graphCanvasState.nodeCount }} node{{ graphCanvasState.nodeCount === 1 ? "" : "s" }} | {{ graphCanvasState.edgeCount }} edge{{ graphCanvasState.edgeCount === 1 ? "" : "s" }}
          </span>
        </div>

        <template v-if="selectedGraphElement?.type === 'node'">
          <p class="assessment-line"><strong>Node:</strong> {{ selectedGraphElement.label }}</p>
          <p class="assessment-line"><strong>Variable ID:</strong> {{ selectedGraphElement.variableId ?? "n/a" }}</p>
          <p class="assessment-line"><strong>Position:</strong> {{ selectedGraphElement.position.x }}, {{ selectedGraphElement.position.y }}</p>
        </template>

        <template v-else-if="selectedGraphElement?.type === 'edge'">
          <p class="assessment-line"><strong>Edge:</strong> {{ selectedGraphElement.source }} -> {{ selectedGraphElement.target }}</p>
          <p class="assessment-line"><strong>Status:</strong> {{ selectedGraphElement.status }}</p>
          <p class="assessment-line"><strong>Manual lock:</strong> {{ selectedGraphElement.manualLock ? "yes" : "no" }}</p>
          <p class="assessment-line"><strong>Evidence count:</strong> {{ selectedGraphElement.evidenceCount }}</p>
        </template>

        <template v-else-if="selectedGraphElement?.type === 'multi'">
          <p class="assessment-line"><strong>Selection:</strong> {{ selectedGraphElement.count }} element{{ selectedGraphElement.count === 1 ? "" : "s" }}</p>
          <p class="assessment-line"><strong>Nodes:</strong> {{ selectedGraphElement.nodeCount }}</p>
          <p class="assessment-line"><strong>Edges:</strong> {{ selectedGraphElement.edgeCount }}</p>
        </template>

        <p v-else class="assessment-line">No active selection. Use click or shift-drag on the canvas to inspect nodes and edges.</p>
      </section>

      <InferenceResult
        :inference-result="inferenceResult"
        :causal-graph-image-url="causalGraphImageUrl"
        :inference-response="inferenceResponse"
      />

      <section v-if="assessmentResult" class="assessment-panel">
        <div class="assessment-header">
          <h3 class="assessment-title">Identification &amp; Admissibility</h3>
          <span :class="['assessment-badge', `assessment-badge-${assessmentResult.badge || 'caution'}`]">
            {{ assessmentResult.badge || "caution" }}
          </span>
        </div>

        <ul v-if="assessmentResult.reasons?.length" class="assessment-reasons">
          <li v-for="reason in assessmentResult.reasons" :key="reason">{{ reason }}</li>
        </ul>

        <p class="assessment-line"><strong>Estimand:</strong> {{ assessmentResult.selected_estimand || "ATE" }}</p>
        <p class="assessment-line"><strong>Suggested method:</strong> {{ assessmentResult.suggested_method || "n/a" }}</p>
        <p class="assessment-line">
          <strong>Overlap:</strong>
          {{ assessmentResult.overlap_ok ? "ok" : "check warnings" }}
        </p>

        <ul v-if="assessmentResult.overlap_warnings?.length" class="assessment-warnings">
          <li v-for="warning in assessmentResult.overlap_warnings" :key="warning">{{ warning }}</li>
        </ul>

        <div class="assessment-grid">
          <div class="assessment-card">
            <h4>Adjustment set</h4>
            <ul v-if="assessmentResult.adjustment_set?.length">
              <li v-for="item in assessmentResult.adjustment_set" :key="`adj-${item}`">{{ item }}</li>
            </ul>
            <p v-else>None</p>
          </div>

          <div class="assessment-card">
            <h4>IV candidates</h4>
            <ul v-if="assessmentResult.iv_candidates?.length">
              <li v-for="item in assessmentResult.iv_candidates" :key="`iv-${item}`">{{ item }}</li>
            </ul>
            <p v-else>None</p>
          </div>

          <div class="assessment-card">
            <h4>Frontdoor variables</h4>
            <ul v-if="assessmentResult.frontdoor_variables?.length">
              <li v-for="item in assessmentResult.frontdoor_variables" :key="`fd-${item}`">{{ item }}</li>
            </ul>
            <p v-else>None</p>
          </div>
        </div>
      </section>

      <section class="robustness-panel">
        <div class="panel-header">
          <h3 class="assessment-title">Refutation &amp; Sensitivity Dashboard</h3>
          <div class="panel-actions">
            <button class="panel-action" type="button" @click="runRobustness">Run checks</button>
            <button
              class="panel-action"
              type="button"
              :disabled="!robustnessResult"
              @click="exportRobustness('json')"
            >
              Export JSON
            </button>
            <button
              class="panel-action"
              type="button"
              :disabled="!robustnessResult"
              @click="exportRobustness('csv')"
            >
              Export CSV
            </button>
          </div>
        </div>

        <template v-if="robustnessResult">
          <p class="assessment-line"><strong>Baseline method:</strong> {{ robustnessResult.baseline_method || "n/a" }}</p>
          <div class="robust-grid">
            <div class="assessment-card">
              <h4>Estimator comparison</h4>
              <ul v-if="robustnessResult.estimator_comparison?.length">
                <li v-for="item in robustnessResult.estimator_comparison" :key="item.method_name">
                  {{ item.method_name }}: {{ item.estimated_effect ?? "n/a" }}
                  <span v-if="item.error"> ({{ item.error }})</span>
                </li>
              </ul>
              <p v-else>None</p>
            </div>

            <div class="assessment-card">
              <h4>Refuters</h4>
              <ul>
                <li v-for="(value, key) in robustnessResult.refutations" :key="key">
                  {{ key }}: {{ value.status }}
                </li>
              </ul>
            </div>

            <div class="assessment-card">
              <h4>Sensitivity</h4>
              <ul>
                <li v-for="(value, key) in robustnessResult.sensitivity" :key="key">
                  {{ key }}: {{ value.status }}
                </li>
              </ul>
            </div>
          </div>
        </template>
      </section>

      <section class="counterfactual-panel">
        <div class="panel-header">
          <h3 class="assessment-title">Counterfactual, What-if &amp; Root-cause</h3>
          <div class="panel-actions">
            <button
              class="panel-action"
              type="button"
              :disabled="!whatIfResult && !rootCauseResult"
              @click="exportCounterfactual('json')"
            >
              Export JSON
            </button>
            <button
              class="panel-action"
              type="button"
              :disabled="!whatIfResult && !rootCauseResult"
              @click="exportCounterfactual('csv')"
            >
              Export CSV
            </button>
          </div>
        </div>

        <div class="what-if-controls">
          <label class="control-label" for="what-if-treatment">Treatment intervention value</label>
          <input
            id="what-if-treatment"
            v-model="whatIfTreatmentValue"
            class="what-if-input"
            type="number"
            step="0.1"
          />
          <button class="panel-action" type="button" @click="runWhatIf">Run what-if</button>
          <button class="panel-action" type="button" @click="runRootCause">Run root-cause</button>
        </div>

        <div class="robust-grid">
          <div v-if="whatIfResult" class="assessment-card">
            <h4>What-if result</h4>
            <p>Baseline outcome mean: {{ whatIfResult.baseline_outcome_mean }}</p>
            <p>Baseline treatment mean: {{ whatIfResult.baseline_treatment_mean }}</p>
            <p>Estimated ATE: {{ whatIfResult.estimated_ate ?? "n/a" }}</p>
            <p>Counterfactual outcome mean: {{ whatIfResult.counterfactual_outcome_mean ?? "n/a" }}</p>
            <p>{{ whatIfResult.note }}</p>
          </div>

          <div v-if="rootCauseResult" class="assessment-card">
            <h4>Anomaly attribution</h4>
            <ul>
              <li v-for="item in rootCauseResult.anomaly_attribution" :key="`an-${item.variable}`">
                {{ item.variable }}: {{ item.score }}
              </li>
            </ul>
          </div>

          <div v-if="rootCauseResult" class="assessment-card">
            <h4>Distribution-change attribution</h4>
            <ul>
              <li v-for="item in rootCauseResult.distribution_change_attribution" :key="`dc-${item.variable}`">
                {{ item.variable }}: {{ item.score }}
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section v-if="edgeEvidenceList.length" class="evidence-panel">
        <h3 class="evidence-title">Edge Evidence</h3>
        <ul class="evidence-list">
          <li v-for="item in edgeEvidenceList" :key="item.key">
            <strong>{{ item.source }} -> {{ item.target }}</strong>
            <span> | {{ item.status }} | {{ item.evidenceCount }} evidence item(s)</span>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue"

import DatasetSidebar from "./components/DatasetSidebar.vue"
import GraphCanvas from "./components/GraphCanvas.vue"
import GraphControls from "./components/GraphControls.vue"
import InferenceResult from "./components/InferenceResult.vue"
import { createGraphStateSignature } from "./composables/useGraphCanvas"
import { useCausalApi } from "./composables/useCausalApi"

const {
  uploadCsv,
  saveGraph: saveGraphApi,
  runInference,
  suggestEdges,
  draftGraph,
  assessQuery,
  fetchGraphDetails,
  runRobustnessDashboard,
  runWhatIfAnalysis,
  runRootCauseAnalysis,
  getErrorMessage,
} = useCausalApi()

const variables = ref([])
const graphId = ref(null)
const datasetName = ref("")
const datasetPreviewRows = ref([])
const inferenceResult = ref(null)
const inferenceResponse = ref(null)
const causalGraphImageUrl = ref("")
const selectedTreatment = ref("")
const selectedOutcome = ref("")
const selectedMethod = ref("")

const statusMessage = ref("")
const statusType = ref("success")
const edgeEvidenceList = ref([])
const assessmentResult = ref(null)
const robustnessResult = ref(null)
const whatIfTreatmentValue = ref(0)
const whatIfResult = ref(null)
const rootCauseResult = ref(null)
const ENABLE_INFERENCE_DEBUG = import.meta.env.DEV

const graphCanvasRef = ref(null)
const graphRevision = ref(0)
const lastPersistedGraph = ref({ graphId: null, signature: "" })
const graphCanvasState = ref({ nodeCount: 0, edgeCount: 0, canUndo: false, canRedo: false })
const selectedGraphElement = ref(null)

let assessmentTimerId = null
let assessmentRequestToken = 0

const graphCanvasSnapshotKey = computed(() => {
  if (graphId.value) {
    return `graph-${graphId.value}`
  }
  if (datasetName.value) {
    return `dataset-${datasetName.value}`
  }
  return "graph-editor"
})

function setStatus(message, type = "success") {
  statusMessage.value = message
  statusType.value = type
}

function clearStatus() {
  statusMessage.value = ""
}

function handleGraphChange(payload = {}) {
  graphCanvasState.value = {
    nodeCount: payload.nodeCount || 0,
    edgeCount: payload.edgeCount || 0,
    canUndo: Boolean(payload.canUndo),
    canRedo: Boolean(payload.canRedo),
  }
  graphRevision.value += 1
}

function handleGraphSelection(payload) {
  selectedGraphElement.value = payload
}

async function refreshGraphDetails() {
  if (!graphId.value || !graphCanvasRef.value) {
    return
  }

  const details = await fetchGraphDetails(graphId.value)
  const detailNodes = Array.isArray(details?.nodes) ? details.nodes : []
  const detailEdges = Array.isArray(details?.edges) ? details.edges : []
  graphCanvasRef.value.syncGraph({ nodes: detailNodes, edges: detailEdges })

  edgeEvidenceList.value = detailEdges.map((edge) => ({
    key: `${edge.source}:${edge.target}`,
    source: edge.source,
    target: edge.target,
    status: edge.status || "unknown",
    evidenceCount: Array.isArray(edge.evidence) ? edge.evidence.length : 0,
  }))
}

function relayoutGraph() {
  graphCanvasRef.value?.relayoutGraph()
}

function getCanvasEdges() {
  return graphCanvasRef.value?.serializeGraph().edges || []
}

function getCanvasNodes() {
  return graphCanvasRef.value?.serializeGraph().nodes || []
}

function hasCanvasEdges() {
  return graphCanvasRef.value?.hasEdges() || false
}

function getCanvasNodeCount() {
  return graphCanvasRef.value?.getNodeCount() || 0
}

async function persistGraphEdges(showSuccessStatus = false) {
  if (!graphId.value) {
    setStatus("Upload a dataset before saving graph edges.", "error")
    return false
  }

  const edges = getCanvasEdges()
  const nodes = getCanvasNodes()
  if (!edges.length) {
    setStatus("Add at least one edge before running analysis.", "error")
    return false
  }

  const signature = createGraphStateSignature({ nodes, edges })
  if (lastPersistedGraph.value.graphId === graphId.value && lastPersistedGraph.value.signature === signature) {
    if (showSuccessStatus) {
      setStatus(`Graph ${graphId.value} is already up to date.`)
    }
    return true
  }

  try {
    const responseData = await saveGraphApi({
      graph_id: graphId.value,
      name: "UserGraph",
      nodes: nodes.map((node) => ({
        id: node.variableId,
        name: node.variableName,
        position: node.position,
      })),
      edges,
    })
    graphId.value = responseData.graph_id
    lastPersistedGraph.value = {
      graphId: responseData.graph_id,
      signature,
    }
    await refreshGraphDetails()
    if (showSuccessStatus) {
      setStatus(`Graph saved with ID ${graphId.value}.`)
    }
    return true
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to save graph."), "error")
    return false
  }
}

async function resetGraphCanvas() {
  graphCanvasRef.value?.resetGraph()
  lastPersistedGraph.value = { graphId: graphId.value, signature: "" }
  selectedGraphElement.value = null
}

async function handleFileUpload(file) {
  if (!file) {
    return
  }

  if (!file.name.toLowerCase().endsWith(".csv")) {
    setStatus("Please upload a valid CSV file.", "error")
    return
  }

  try {
    const responseData = await uploadCsv(file)
    graphId.value = responseData.graph_id
    variables.value = responseData.variables
    datasetName.value = responseData.graph_name || file.name
    datasetPreviewRows.value = Array.isArray(responseData.preview) ? responseData.preview : []
    selectedTreatment.value = ""
    selectedOutcome.value = ""
    inferenceResult.value = null
    inferenceResponse.value = null
    causalGraphImageUrl.value = ""
    assessmentResult.value = null
    robustnessResult.value = null
    whatIfResult.value = null
    rootCauseResult.value = null
    await resetGraphCanvas()
    graphRevision.value += 1
    graphCanvasState.value = { nodeCount: 0, edgeCount: 0, canUndo: false, canRedo: false }
    setStatus(
      `Dataset connected: ${datasetName.value}. ${variables.value.length} column${variables.value.length === 1 ? "" : "s"} loaded; drag variables to add nodes to the graph.`,
    )
  } catch (error) {
    datasetPreviewRows.value = []
    setStatus(getErrorMessage(error, "CSV upload failed."), "error")
  }
}

async function saveGraph() {
  await persistGraphEdges(true)
}

async function resetAnalysisWorkspace() {
  await resetGraphCanvas()
  selectedTreatment.value = ""
  selectedOutcome.value = ""
  selectedMethod.value = ""
  inferenceResult.value = null
  inferenceResponse.value = null
  causalGraphImageUrl.value = ""
  assessmentResult.value = null
  robustnessResult.value = null
  whatIfResult.value = null
  rootCauseResult.value = null
  edgeEvidenceList.value = []
  clearStatus()
  setStatus("Workspace reset. Dataset remains loaded; drag variables to rebuild the graph.")
}

async function suggestGraphEdges() {
  if (!variables.value.length || variables.value.length < 2) {
    setStatus("Upload a dataset with at least two variables before AI suggestions.", "error")
    return
  }

  try {
    let responseData
    if (graphId.value) {
      responseData = await draftGraph({
        graph_id: graphId.value,
        max_edges: 10,
        context: "Draft and verify plausible causal relationships for the current graph.",
      })
    } else {
      responseData = await suggestEdges({
        variables: variables.value.map((item) => item.name),
        max_edges: 10,
        context: "Suggest plausible causal relationships for the current dataset variables.",
      })
    }

    const shouldRelayout = getCanvasNodeCount() === 0
    const { addedCount, nodeAddedCount } = graphCanvasRef.value?.addSuggestedEdges(responseData.edges) || {
      addedCount: 0,
      nodeAddedCount: 0,
    }
    edgeEvidenceList.value = (responseData.edges || []).map((edge) => ({
      key: `${edge.source}:${edge.target}`,
      source: edge.source,
      target: edge.target,
      status: edge.verification_status || edge.status || "unknown",
      evidenceCount: Array.isArray(edge.evidence) ? edge.evidence.length : 0,
    }))
    if (addedCount > 0) {
      if (shouldRelayout && nodeAddedCount > 1) {
        relayoutGraph()
      }
      setStatus(`Added ${addedCount} AI-suggested edge${addedCount === 1 ? "" : "s"}.`)
      return
    }

    setStatus("AI returned suggestions, but all edges were already present.")
  } catch (error) {
    setStatus(getErrorMessage(error, "AI edge suggestion failed."), "error")
  }
}

function canRunAssessment() {
  return (
    Boolean(graphId.value) &&
    Boolean(selectedTreatment.value) &&
    Boolean(selectedOutcome.value) &&
    getCanvasNodeCount() >= 2 &&
    hasCanvasEdges()
  )
}

async function refreshAssessment(showErrors = false) {
  const requestToken = ++assessmentRequestToken
  if (!canRunAssessment()) {
    assessmentResult.value = null
    return null
  }

  const saved = await persistGraphEdges(false)
  if (!saved || requestToken !== assessmentRequestToken) {
    assessmentResult.value = null
    return null
  }

  try {
    const assessment = await assessQuery({
      graph_id: graphId.value,
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
      estimand: "ATE",
    })
    if (requestToken !== assessmentRequestToken) {
      return null
    }
    assessmentResult.value = assessment
    return assessment
  } catch (error) {
    if (requestToken !== assessmentRequestToken) {
      return null
    }
    assessmentResult.value = null
    if (showErrors) {
      setStatus(getErrorMessage(error, "Assessment failed."), "error")
    }
    return null
  }
}

function scheduleAssessmentRefresh() {
  if (assessmentTimerId) {
    window.clearTimeout(assessmentTimerId)
  }

  assessmentTimerId = window.setTimeout(() => {
    void refreshAssessment(false)
  }, 300)
}

function deleteSelectedGraphElements() {
  const removedCount = graphCanvasRef.value?.removeSelectedElements() || 0
  if (removedCount > 0) {
    setStatus(`Removed ${removedCount} selected element${removedCount === 1 ? "" : "s"}.`)
    lastPersistedGraph.value = { graphId: graphId.value, signature: "" }
  }
}

function undoGraphEdit() {
  if (graphCanvasRef.value?.undo()) {
    lastPersistedGraph.value = { graphId: graphId.value, signature: "" }
  }
}

function redoGraphEdit() {
  if (graphCanvasRef.value?.redo()) {
    lastPersistedGraph.value = { graphId: graphId.value, signature: "" }
  }
}

function zoomInGraph() {
  graphCanvasRef.value?.zoomIn()
}

function zoomOutGraph() {
  graphCanvasRef.value?.zoomOut()
}

function fitGraphToView() {
  graphCanvasRef.value?.fitGraph()
}

function centerGraphInView() {
  graphCanvasRef.value?.centerGraph()
}

async function runRobustness() {
  if (!canRunAssessment()) {
    setStatus("Select treatment/outcome and ensure graph has at least two nodes.", "error")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    return
  }

  try {
    const responseData = await runRobustnessDashboard({
      graph_id: graphId.value,
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
    })
    robustnessResult.value = responseData
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to run robustness checks."), "error")
  }
}

async function runWhatIf() {
  if (!canRunAssessment()) {
    setStatus("Select treatment/outcome and ensure graph has at least two nodes.", "error")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    return
  }

  try {
    const responseData = await runWhatIfAnalysis({
      graph_id: graphId.value,
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
      treatment_value: Number(whatIfTreatmentValue.value),
    })
    whatIfResult.value = responseData
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to run what-if analysis."), "error")
  }
}

async function runRootCause() {
  if (!graphId.value || !selectedOutcome.value) {
    setStatus("Select an outcome variable before root-cause analysis.", "error")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    return
  }

  try {
    const responseData = await runRootCauseAnalysis({
      graph_id: graphId.value,
      outcome: selectedOutcome.value,
    })
    rootCauseResult.value = responseData
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to run root-cause analysis."), "error")
  }
}

function downloadTextFile(content, fileName, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

function toCsv(rows) {
  if (!rows.length) {
    return ""
  }

  const headers = Object.keys(rows[0])
  const headerLine = headers.join(",")
  const bodyLines = rows.map((row) =>
    headers
      .map((header) => {
        const value = row[header]
        const text = value === null || value === undefined ? "" : String(value)
        const escaped = text.replace(/"/g, '""')
        return `"${escaped}"`
      })
      .join(","),
  )

  return [headerLine, ...bodyLines].join("\n")
}

function exportRobustness(format) {
  if (!robustnessResult.value) {
    return
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-")
  if (format === "json") {
    const content = JSON.stringify(robustnessResult.value, null, 2)
    downloadTextFile(content, `robustness-dashboard-${stamp}.json`, "application/json")
    return
  }

  const rows = []
  for (const item of robustnessResult.value.estimator_comparison || []) {
    rows.push({
      section: "estimator_comparison",
      key: item.method_name,
      status: item.error ? "error" : "ok",
      value: item.estimated_effect ?? "",
      details: item.error || "",
    })
  }
  for (const [key, value] of Object.entries(robustnessResult.value.refutations || {})) {
    rows.push({
      section: "refutation",
      key,
      status: value?.status || "",
      value: value?.p_value ?? "",
      details: value?.summary || "",
    })
  }
  for (const [key, value] of Object.entries(robustnessResult.value.sensitivity || {})) {
    rows.push({
      section: "sensitivity",
      key,
      status: value?.status || "",
      value: value?.p_value ?? "",
      details: value?.summary || "",
    })
  }
  const content = toCsv(rows)
  downloadTextFile(content, `robustness-dashboard-${stamp}.csv`, "text/csv;charset=utf-8")
}

function exportCounterfactual(format) {
  const payload = {
    what_if: whatIfResult.value,
    root_cause: rootCauseResult.value,
  }
  if (!payload.what_if && !payload.root_cause) {
    return
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-")
  if (format === "json") {
    const content = JSON.stringify(payload, null, 2)
    downloadTextFile(content, `counterfactual-root-cause-${stamp}.json`, "application/json")
    return
  }

  const rows = []
  if (payload.what_if) {
    rows.push(
      {
        section: "what_if",
        key: "baseline_outcome_mean",
        value: payload.what_if.baseline_outcome_mean,
        details: "",
      },
      {
        section: "what_if",
        key: "baseline_treatment_mean",
        value: payload.what_if.baseline_treatment_mean,
        details: "",
      },
      {
        section: "what_if",
        key: "estimated_ate",
        value: payload.what_if.estimated_ate ?? "",
        details: payload.what_if.note || "",
      },
      {
        section: "what_if",
        key: "counterfactual_outcome_mean",
        value: payload.what_if.counterfactual_outcome_mean ?? "",
        details: "",
      },
    )
  }
  for (const item of payload.root_cause?.anomaly_attribution || []) {
    rows.push({
      section: "anomaly_attribution",
      key: item.variable,
      value: item.score,
      details: item.details || "",
    })
  }
  for (const item of payload.root_cause?.distribution_change_attribution || []) {
    rows.push({
      section: "distribution_change_attribution",
      key: item.variable,
      value: item.score,
      details: item.details || "",
    })
  }

  const content = toCsv(rows)
  downloadTextFile(content, `counterfactual-root-cause-${stamp}.csv`, "text/csv;charset=utf-8")
}

async function computeInference() {
  console.info("[analysis] Run inference requested")

  if (!graphId.value) {
    setStatus("Upload a dataset before running inference.", "error")
    console.warn("[analysis] Inference blocked: missing graph_id")
    return
  }

  if (!selectedTreatment.value || !selectedOutcome.value) {
    setStatus("Select treatment and outcome variables.", "error")
    console.warn("[analysis] Inference blocked: treatment/outcome not selected")
    return
  }

  if (getCanvasNodeCount() < 2) {
    setStatus("At least two nodes are required.", "error")
    console.warn("[analysis] Inference blocked: fewer than 2 nodes on canvas")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    console.warn("[analysis] Inference blocked: could not persist graph edges")
    return
  }

  try {
    const assessment = await refreshAssessment(true)
    if (!assessment) {
      console.warn("[analysis] Inference blocked: assessment did not return a result")
      return
    }

    const rejectedAssessment = assessment?.badge === "reject"
    if (rejectedAssessment) {
      setStatus(
        `${assessment?.reasons?.[0] || "Identification checks rejected this query."} Running inference anyway.`,
        "error",
      )
    }

    const payload = {
      graph_id: Number(graphId.value),
      treatment: Number(selectedTreatment.value),
      outcome: Number(selectedOutcome.value),
    }

    if (selectedMethod.value) {
      payload.method_name = selectedMethod.value
    }

    if (ENABLE_INFERENCE_DEBUG) {
      console.debug("[inference payload]", payload)
    }

    console.info("[analysis] Inference started", payload)

    const responseData = await runInference(payload)

    inferenceResponse.value = responseData
    inferenceResult.value = responseData.estimated_effect ?? "N/A"
    causalGraphImageUrl.value = responseData.graph_image ?? ""
    console.info("[analysis] Inference completed", responseData)
    if (!rejectedAssessment) {
      setStatus("Analysis completed. Check Inference Result panel and console output.")
    }
  } catch (error) {
    console.error("[analysis] Inference failed", error)
    setStatus(getErrorMessage(error, "Causal inference failed."), "error")
  }
}
onUnmounted(() => {
  if (assessmentTimerId) {
    window.clearTimeout(assessmentTimerId)
  }
})

watch([graphId, selectedTreatment, selectedOutcome, graphRevision], () => {
  scheduleAssessmentRefresh()
})
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: var(--color-background-mute);
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px 24px;
  box-sizing: border-box;
  overflow: auto;
  min-width: 0;
}

.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.title {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--color-heading);
}

.subtitle {
  margin: 0;
  color: var(--vt-c-text-light-2);
}

.status-banner {
  border-radius: 6px;
  border: 1px solid transparent;
  padding: 10px 12px;
  font-size: 0.95rem;
}

.status-banner.success {
  background: #ecfdf5;
  color: #065f46;
  border-color: #a7f3d0;
}

.status-banner.error {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}

.workspace-layout {
  display: flex;
  gap: 16px;
  min-height: 520px;
}

.graph-panel {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-background);
  padding: 12px;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-title {
  color: var(--color-heading);
  font-size: 0.95rem;
  font-weight: 600;
}

.toolbar-hint {
  color: var(--vt-c-text-light-2);
  font-size: 0.86rem;
}

.legend-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.legend-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.legend-label {
  color: var(--vt-c-text-light-2);
  font-size: 0.82rem;
}

.legend-chip {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 0.78rem;
  color: var(--color-text);
  background: var(--color-background);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.legend-trust,
.legend-supported {
  color: #10b981;
  border-color: #10b981;
}

.legend-caution,
.legend-weak {
  color: #f59e0b;
  border-color: #f59e0b;
}

.legend-reject,
.legend-conflict {
  color: #ef4444;
  border-color: #ef4444;
}

.legend-manual {
  border-width: 2px;
}

.graph-canvas-host {
  flex: 1;
  min-height: 420px;
  min-width: 0;
}

.controls-column {
  flex: 0 0 300px;
}

.assessment-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.selection-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.assessment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.assessment-title {
  margin: 0;
  font-size: 0.95rem;
  color: var(--color-heading);
}

.assessment-badge {
  border-radius: 999px;
  border: 1px solid var(--color-border);
  padding: 2px 8px;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.assessment-badge-trust {
  color: #10b981;
  border-color: #10b981;
}

.assessment-badge-caution {
  color: #f59e0b;
  border-color: #f59e0b;
}

.assessment-badge-reject {
  color: #ef4444;
  border-color: #ef4444;
}

.assessment-line {
  margin: 0;
  color: var(--color-text);
  font-size: 0.88rem;
}

.assessment-reasons,
.assessment-warnings {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text);
  font-size: 0.88rem;
}

.assessment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.assessment-card {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 8px;
  background: var(--color-background);
}

.assessment-card h4 {
  margin: 0 0 6px;
  font-size: 0.85rem;
  color: var(--color-heading);
}

.assessment-card p,
.assessment-card ul {
  margin: 0;
  color: var(--color-text);
  font-size: 0.84rem;
  padding-left: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.panel-action {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-background);
  color: var(--color-text);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 0.84rem;
}

.panel-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.robustness-panel,
.counterfactual-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.robust-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.what-if-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.what-if-input {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 6px 8px;
  background: var(--color-background);
  color: var(--color-text);
}

.evidence-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 10px 12px;
}

.evidence-title {
  margin: 0 0 8px;
  font-size: 0.95rem;
  color: var(--color-heading);
}

.evidence-list {
  margin: 0;
  padding-left: 18px;
}

.evidence-list li {
  margin: 4px 0;
  color: var(--color-text);
}

@media (max-width: 768px) {
  .main-content {
    padding: 16px;
  }

  .workspace-layout {
    flex-direction: column;
    min-height: auto;
  }

  .controls-column {
    flex: 1 1 auto;
  }

  .graph-canvas-host {
    min-height: 360px;
  }

  .assessment-grid {
    grid-template-columns: 1fr;
  }

  .robust-grid {
    grid-template-columns: 1fr;
  }
}
</style>
