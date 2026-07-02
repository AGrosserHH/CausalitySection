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
        <p class="subtitle">Build a graph, review verifier-backed suggestions, pressure-test identification, and switch into time-series diagnostics when the dataset supports it.</p>
      </header>

      <div v-if="statusMessage" :class="['status-banner', statusType]">
        {{ statusMessage }}
      </div>

      <section class="workspace-layout">
        <div class="graph-panel">
          <div class="graph-toolbar">
            <span class="toolbar-title">Graph Canvas</span>
            <span class="toolbar-hint">Drag variables in, connect nodes, then use the copilot and diagnostics panels to stress-test the graph before estimating effects.</span>
          </div>
          <div class="legend-row">
            <div class="legend-group">
              <span class="legend-label">Edge status:</span>
              <span class="legend-chip legend-supported">supported</span>
              <span class="legend-chip legend-weak">weak</span>
              <span class="legend-chip legend-conflict">conflict</span>
              <span class="legend-chip legend-manual">locked</span>
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
          <span class="legend-label">{{ graphCanvasState.nodeCount }} nodes | {{ graphCanvasState.edgeCount }} edges</span>
        </div>

        <template v-if="selectedGraphElement?.type === 'node'">
          <p class="assessment-line"><strong>Node:</strong> {{ selectedGraphElement.label }}</p>
          <p class="assessment-line"><strong>Variable ID:</strong> {{ selectedGraphElement.variableId ?? 'n/a' }}</p>
          <p class="assessment-line"><strong>Position:</strong> {{ selectedGraphElement.position.x }}, {{ selectedGraphElement.position.y }}</p>
        </template>

        <template v-else-if="selectedGraphElement?.type === 'edge'">
          <p class="assessment-line"><strong>Edge:</strong> {{ selectedGraphElement.source }} -> {{ selectedGraphElement.target }}</p>
          <p class="assessment-line"><strong>Status:</strong> {{ selectedGraphElement.status }}</p>
          <p class="assessment-line"><strong>Manual lock:</strong> {{ selectedGraphElement.manualLock ? 'yes' : 'no' }}</p>
          <p class="assessment-line"><strong>Evidence count:</strong> {{ selectedGraphElement.evidenceCount }}</p>
        </template>

        <template v-else-if="selectedGraphElement?.type === 'multi'">
          <p class="assessment-line"><strong>Selection:</strong> {{ selectedGraphElement.count }} element(s)</p>
          <p class="assessment-line"><strong>Nodes:</strong> {{ selectedGraphElement.nodeCount }}</p>
          <p class="assessment-line"><strong>Edges:</strong> {{ selectedGraphElement.edgeCount }}</p>
        </template>

        <p v-else class="assessment-line">No active selection. Click or box-select graph elements to inspect them.</p>
      </section>

      <InferenceResult
        :inference-result="inferenceResult"
        :causal-graph-image-url="causalGraphImageUrl"
        :inference-response="inferenceResponse"
      />

      <GraphCopilotPanel
        :suggestions="copilotSuggestions"
        :summary="copilotSummary"
        @accept-edge="acceptCopilotEdge"
        @accept-edge-locked="acceptCopilotEdgeLocked"
        @accept-recommended="acceptRecommendedCopilotEdges"
        @accept-all="acceptAllCopilotEdges"
        @clear="clearCopilotDraft"
      />

      <IdentificationPanel :result="assessmentResult" />

      <RobustnessDashboard
        :result="robustnessResult"
        @run="runRobustness"
        @export-json="exportRobustness('json')"
        @export-csv="exportRobustness('csv')"
      />

      <section class="counterfactual-panel">
        <div class="panel-header">
          <div>
            <h3 class="panel-title">Counterfactual, What-if & Root-cause</h3>
            <p class="panel-subtitle">Quick intervention simulation plus anomaly and shift attribution.</p>
          </div>
          <div class="panel-actions">
            <button class="panel-action" type="button" :disabled="!whatIfResult && !rootCauseResult" @click="exportCounterfactual('json')">Export JSON</button>
            <button class="panel-action" type="button" :disabled="!whatIfResult && !rootCauseResult" @click="exportCounterfactual('csv')">Export CSV</button>
          </div>
        </div>

        <div class="what-if-controls">
          <label class="control-label" for="what-if-treatment">Treatment intervention value</label>
          <input id="what-if-treatment" v-model="whatIfTreatmentValue" class="what-if-input" type="number" step="0.1" />
          <button class="panel-action primary-run" type="button" @click="runWhatIf">Run what-if</button>
          <button class="panel-action" type="button" @click="runRootCause">Run root-cause</button>
        </div>

        <div class="triple-grid">
          <article v-if="whatIfResult" class="assessment-card">
            <h4>What-if result</h4>
            <p><strong>Baseline outcome mean:</strong> {{ whatIfResult.baseline_outcome_mean }}</p>
            <p><strong>Baseline treatment mean:</strong> {{ whatIfResult.baseline_treatment_mean }}</p>
            <p><strong>Estimated ATE:</strong> {{ whatIfResult.estimated_ate ?? 'n/a' }}</p>
            <p><strong>Counterfactual outcome mean:</strong> {{ whatIfResult.counterfactual_outcome_mean ?? 'n/a' }}</p>
            <p>{{ whatIfResult.note }}</p>
          </article>

          <article v-if="rootCauseResult" class="assessment-card">
            <h4>Anomaly attribution</h4>
            <ul class="compact-list">
              <li v-for="item in rootCauseResult.anomaly_attribution || []" :key="`an-${item.variable}`">{{ item.variable }} | {{ item.score }}</li>
            </ul>
          </article>

          <article v-if="rootCauseResult" class="assessment-card">
            <h4>Distribution-change attribution</h4>
            <ul class="compact-list">
              <li v-for="item in rootCauseResult.distribution_change_attribution || []" :key="`dc-${item.variable}`">{{ item.variable }} | {{ item.score }}</li>
            </ul>
          </article>
        </div>
      </section>

      <TimeSeriesPanel
        :result="timeSeriesResult"
        :time-column="timeSeriesConfig.timeColumn"
        :entity-column="timeSeriesConfig.entityColumn"
        :window-count="timeSeriesConfig.windowCount"
        :max-lag="timeSeriesConfig.maxLag"
        :has-preview="Boolean(timeSeriesPreviewSnapshot)"
        @run="runTimeSeries"
        @preview-window="previewTimeSeriesWindow"
        @restore-preview="restoreTimeSeriesPreview"
        @update:time-column="timeSeriesConfig.timeColumn = $event"
        @update:entity-column="timeSeriesConfig.entityColumn = $event"
        @update:window-count="timeSeriesConfig.windowCount = normalizePositiveInteger($event, 4)"
        @update:max-lag="timeSeriesConfig.maxLag = normalizePositiveInteger($event, 3)"
      />

      <section v-if="edgeEvidenceList.length" class="evidence-panel">
        <h3 class="panel-title">Edge Evidence</h3>
        <ul class="compact-list">
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
import GraphCopilotPanel from "./components/GraphCopilotPanel.vue"
import IdentificationPanel from "./components/IdentificationPanel.vue"
import InferenceResult from "./components/InferenceResult.vue"
import RobustnessDashboard from "./components/RobustnessDashboard.vue"
import TimeSeriesPanel from "./components/TimeSeriesPanel.vue"
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
  runTimeSeriesAnalysis,
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
const copilotDraft = ref(null)
const timeSeriesResult = ref(null)
const timeSeriesPreviewSnapshot = ref(null)
const timeSeriesConfig = ref({
  timeColumn: "",
  entityColumn: "",
  windowCount: 4,
  maxLag: 3,
})
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

const copilotSuggestions = computed(() => (Array.isArray(copilotDraft.value?.edges) ? copilotDraft.value.edges : []))
const copilotSummary = computed(() => copilotDraft.value?.summary || null)

function setStatus(message, type = "success") {
  statusMessage.value = message
  statusType.value = type
}

function clearStatus() {
  statusMessage.value = ""
}

function normalizePositiveInteger(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : fallback
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

function restoreTimeSeriesPreview(showStatus = true) {
  if (!timeSeriesPreviewSnapshot.value || !graphCanvasRef.value) {
    return
  }

  graphCanvasRef.value.syncGraph(timeSeriesPreviewSnapshot.value)
  timeSeriesPreviewSnapshot.value = null
  if (showStatus) {
    setStatus("Restored the persisted graph after time-series preview.")
  }
}

async function persistGraphEdges(showSuccessStatus = false) {
  if (timeSeriesPreviewSnapshot.value) {
    restoreTimeSeriesPreview(false)
  }

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
    selectedMethod.value = ""
    inferenceResult.value = null
    inferenceResponse.value = null
    causalGraphImageUrl.value = ""
    assessmentResult.value = null
    robustnessResult.value = null
    whatIfResult.value = null
    rootCauseResult.value = null
    copilotDraft.value = null
    timeSeriesResult.value = null
    timeSeriesPreviewSnapshot.value = null
    await resetGraphCanvas()
    graphRevision.value += 1
    graphCanvasState.value = { nodeCount: 0, edgeCount: 0, canUndo: false, canRedo: false }
    setStatus(`Dataset connected: ${datasetName.value}. ${variables.value.length} columns loaded.`)
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
  copilotDraft.value = null
  timeSeriesResult.value = null
  timeSeriesPreviewSnapshot.value = null
  edgeEvidenceList.value = []
  clearStatus()
  setStatus("Workspace reset. Dataset remains loaded; rebuild the graph to continue.")
}

function buildFallbackCopilotSummary(edges) {
  return {
    edge_count: edges.length,
    accept_count: edges.length,
    review_count: 0,
    mean_confidence: 0.6,
    status_counts: {
      supported: edges.length,
      weak: 0,
      conflict: 0,
      rejected: 0,
    },
  }
}

async function suggestGraphEdges() {
  if (variables.value.length < 2) {
    setStatus("Upload a dataset with at least two variables before using the copilot.", "error")
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
      const suggested = await suggestEdges({
        variables: variables.value.map((item) => item.name),
        max_edges: 10,
        context: "Suggest plausible causal relationships for the current dataset variables.",
      })
      responseData = {
        edges: (suggested.edges || []).map((edge) => ({
          ...edge,
          verification_status: "weak",
          confidence: 0.6,
          recommended_action: "review",
          verifier_breakdown: [],
          evidence: [],
        })),
        summary: buildFallbackCopilotSummary(suggested.edges || []),
      }
    }

    copilotDraft.value = responseData
    setStatus(`Graph copilot returned ${responseData.edges?.length || 0} edge suggestion(s). Review them before applying.`)
  } catch (error) {
    setStatus(getErrorMessage(error, "AI edge suggestion failed."), "error")
  }
}

function applyCopilotEdges(edges, lockAccepted = false) {
  if (!Array.isArray(edges) || !edges.length) {
    return
  }

  const shouldRelayout = getCanvasNodeCount() === 0
  const preparedEdges = edges.map((edge) => ({
    ...edge,
    manual_lock: lockAccepted || Boolean(edge.manual_lock),
    status: edge.verification_status || edge.status || "",
  }))
  const { addedCount, nodeAddedCount } = graphCanvasRef.value?.addSuggestedEdges(preparedEdges) || {
    addedCount: 0,
    nodeAddedCount: 0,
  }

  if (shouldRelayout && nodeAddedCount > 1) {
    relayoutGraph()
  }
  lastPersistedGraph.value = { graphId: graphId.value, signature: "" }
  setStatus(`Applied ${preparedEdges.length} copilot edge suggestion(s).`)
  if (addedCount === 0) {
    setStatus("Copilot suggestions were applied as status updates to existing edges.")
  }
}

function removeCopilotIndexes(indexes) {
  const removalSet = new Set(indexes)
  const nextEdges = copilotSuggestions.value.filter((_, index) => !removalSet.has(index))
  copilotDraft.value = nextEdges.length
    ? {
        ...copilotDraft.value,
        edges: nextEdges,
        summary: buildFallbackCopilotSummary(nextEdges),
      }
    : null
}

function acceptCopilotEdge(index) {
  const edge = copilotSuggestions.value[index]
  if (!edge) {
    return
  }
  applyCopilotEdges([edge], false)
  removeCopilotIndexes([index])
}

function acceptCopilotEdgeLocked(index) {
  const edge = copilotSuggestions.value[index]
  if (!edge) {
    return
  }
  applyCopilotEdges([edge], true)
  removeCopilotIndexes([index])
}

function acceptRecommendedCopilotEdges() {
  const indexes = []
  const edges = []
  copilotSuggestions.value.forEach((edge, index) => {
    if ((edge.recommended_action || "review") === "accept") {
      indexes.push(index)
      edges.push(edge)
    }
  })
  if (!edges.length) {
    setStatus("No copilot edges are currently marked as accept.", "error")
    return
  }
  applyCopilotEdges(edges, false)
  removeCopilotIndexes(indexes)
}

function acceptAllCopilotEdges() {
  if (!copilotSuggestions.value.length) {
    return
  }
  applyCopilotEdges(copilotSuggestions.value, false)
  copilotDraft.value = null
}

function clearCopilotDraft() {
  copilotDraft.value = null
}

function canRunAssessment() {
  return Boolean(graphId.value) && Boolean(selectedTreatment.value) && Boolean(selectedOutcome.value) && getCanvasNodeCount() >= 2 && hasCanvasEdges()
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
    setStatus(`Removed ${removedCount} selected element(s).`)
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
    robustnessResult.value = await runRobustnessDashboard({
      graph_id: graphId.value,
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
    })
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
    whatIfResult.value = await runWhatIfAnalysis({
      graph_id: graphId.value,
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
      treatment_value: Number(whatIfTreatmentValue.value),
    })
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
    rootCauseResult.value = await runRootCauseAnalysis({
      graph_id: graphId.value,
      outcome: selectedOutcome.value,
    })
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to run root-cause analysis."), "error")
  }
}

async function runTimeSeries() {
  if (!graphId.value) {
    setStatus("Upload a dataset before running time-series mode.", "error")
    return
  }
  if (!timeSeriesConfig.value.timeColumn.trim()) {
    setStatus("Enter a time column before running time-series mode.", "error")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    return
  }

  try {
    timeSeriesResult.value = await runTimeSeriesAnalysis({
      graph_id: graphId.value,
      time_column: timeSeriesConfig.value.timeColumn.trim(),
      entity_column: timeSeriesConfig.value.entityColumn.trim(),
      window_count: normalizePositiveInteger(timeSeriesConfig.value.windowCount, 4),
      max_lag: normalizePositiveInteger(timeSeriesConfig.value.maxLag, 3),
    })
    setStatus("Time-series diagnostics completed. Preview a rolling window to inspect the dynamic graph.")
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to run time-series analysis."), "error")
  }
}

function previewTimeSeriesWindow(index) {
  const windowData = timeSeriesResult.value?.dynamic_graphs?.[index]
  if (!windowData || !graphCanvasRef.value) {
    return
  }

  if (!timeSeriesPreviewSnapshot.value) {
    timeSeriesPreviewSnapshot.value = graphCanvasRef.value.serializeGraph()
  }

  const previewNodes = (timeSeriesPreviewSnapshot.value?.nodes || getCanvasNodes()).map((node) => ({
    id: node.variableId,
    name: node.variableName,
    position: node.position,
  }))
  const previewEdges = (windowData.edges || []).map((edge) => ({
    source: edge.source,
    target: edge.target,
    directed: true,
    manual_lock: false,
    status: edge.status,
    evidence: [
      {
        evidence_type: "temporal_prior",
        status: edge.status === "rejected" ? "rejected" : edge.status,
        score: edge.strength,
        details: {
          lag: edge.best_lag,
          window: windowData.label,
        },
      },
    ],
  }))

  graphCanvasRef.value.syncGraph({ nodes: previewNodes, edges: previewEdges })
  setStatus(`Previewing ${windowData.label} on the graph canvas.`)
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
    downloadTextFile(JSON.stringify(robustnessResult.value, null, 2), `robustness-dashboard-${stamp}.json`, "application/json")
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
      value: value?.delta ?? "",
      details: value?.summary || "",
    })
  }
  for (const [key, value] of Object.entries(robustnessResult.value.sensitivity || {})) {
    rows.push({
      section: "sensitivity",
      key,
      status: value?.status || "",
      value: value?.delta ?? "",
      details: value?.summary || "",
    })
  }
  for (const point of robustnessResult.value.sensitivity_points || []) {
    rows.push({
      section: "sensitivity_points",
      key: point.confounder_strength,
      status: "curve",
      value: point.adjusted_effect ?? "",
      details: "confounder strength sweep",
    })
  }
  downloadTextFile(toCsv(rows), `robustness-dashboard-${stamp}.csv`, "text/csv;charset=utf-8")
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
    downloadTextFile(JSON.stringify(payload, null, 2), `counterfactual-root-cause-${stamp}.json`, "application/json")
    return
  }

  const rows = []
  if (payload.what_if) {
    rows.push(
      { section: "what_if", key: "baseline_outcome_mean", value: payload.what_if.baseline_outcome_mean, details: "" },
      { section: "what_if", key: "baseline_treatment_mean", value: payload.what_if.baseline_treatment_mean, details: "" },
      { section: "what_if", key: "estimated_ate", value: payload.what_if.estimated_ate ?? "", details: payload.what_if.note || "" },
      { section: "what_if", key: "counterfactual_outcome_mean", value: payload.what_if.counterfactual_outcome_mean ?? "", details: "" },
    )
  }
  for (const item of payload.root_cause?.anomaly_attribution || []) {
    rows.push({ section: "anomaly_attribution", key: item.variable, value: item.score, details: item.details || "" })
  }
  for (const item of payload.root_cause?.distribution_change_attribution || []) {
    rows.push({ section: "distribution_change_attribution", key: item.variable, value: item.score, details: item.details || "" })
  }

  downloadTextFile(toCsv(rows), `counterfactual-root-cause-${stamp}.csv`, "text/csv;charset=utf-8")
}

async function computeInference() {
  if (!graphId.value) {
    setStatus("Upload a dataset before running inference.", "error")
    return
  }
  if (!selectedTreatment.value || !selectedOutcome.value) {
    setStatus("Select treatment and outcome variables.", "error")
    return
  }
  if (getCanvasNodeCount() < 2) {
    setStatus("At least two nodes are required.", "error")
    return
  }

  const saved = await persistGraphEdges(false)
  if (!saved) {
    return
  }

  try {
    const assessment = await refreshAssessment(true)
    if (!assessment) {
      return
    }

    if (assessment.badge === "reject") {
      setStatus(`${assessment.reasons?.[0] || "Identification checks rejected this query."} Running inference anyway.`, "error")
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

    const responseData = await runInference(payload)
    inferenceResponse.value = responseData
    inferenceResult.value = responseData.estimated_effect ?? "N/A"
    causalGraphImageUrl.value = responseData.graph_image ?? ""
    if (assessment.badge !== "reject") {
      setStatus("Analysis completed. Review the inference and robustness panels.")
    }
  } catch (error) {
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

.graph-panel,
.selection-panel,
.counterfactual-panel,
.evidence-panel {
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-background);
  padding: 12px;
}

.graph-panel {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
}

.graph-toolbar,
.panel-header,
.assessment-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-title,
.panel-title,
.assessment-title {
  color: var(--color-heading);
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.panel-subtitle {
  margin: 4px 0 0;
  color: var(--vt-c-text-light-2);
  font-size: 0.9rem;
}

.toolbar-hint,
.legend-label {
  color: var(--vt-c-text-light-2);
  font-size: 0.82rem;
}

.legend-row,
.legend-group,
.panel-actions,
.what-if-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.legend-chip,
.panel-action {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 6px 12px;
  background: white;
}

.legend-supported {
  color: #059669;
  border-color: #059669;
}

.legend-weak {
  color: #d97706;
  border-color: #d97706;
}

.legend-conflict {
  color: #dc2626;
  border-color: #dc2626;
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

.assessment-line,
.assessment-card p {
  margin: 0 0 6px;
}

.assessment-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.assessment-card h4 {
  margin: 0 0 8px;
  color: var(--color-heading);
}

.compact-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}

.triple-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.control-label {
  color: var(--color-heading);
  font-size: 0.9rem;
}

.what-if-input {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 8px;
  min-width: 120px;
}

.panel-action {
  cursor: pointer;
}

.primary-run {
  background: #0f766e;
  border-color: #0f766e;
  color: white;
}

@media (max-width: 1024px) {
  .workspace-layout,
  .triple-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .controls-column {
    flex: 1 1 auto;
  }
}
</style>
