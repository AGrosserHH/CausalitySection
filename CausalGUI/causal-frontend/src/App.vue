<template>
  <div class="app-container">
    <DatasetSidebar :variables="variables" @file-upload="handleFileUpload" @drag-start="onDragStart" />

    <main class="main-content">
      <header class="page-header">
        <h1 class="title">🧠 Causal AI Graph Builder</h1>
        <p class="subtitle">Build a causal graph by dragging variables, then save and run inference.</p>
      </header>

      <div v-if="statusMessage" :class="['status-banner', statusType]">
        {{ statusMessage }}
      </div>

      <section class="workspace-layout">
        <div class="graph-panel">
          <div class="graph-toolbar">
            <span class="toolbar-title">Graph Canvas</span>
            <span class="toolbar-hint">Drag variables from the sidebar and right-drag to connect nodes.</span>
          </div>
          <div class="legend-row">
            <div class="legend-group">
              <span class="legend-label">Query badge:</span>
              <span class="legend-chip legend-trust"><span aria-hidden="true">●</span> <span class="sr-only">Query badge:</span>trust</span>
              <span class="legend-chip legend-caution"><span aria-hidden="true">▲</span> <span class="sr-only">Query badge:</span>caution</span>
              <span class="legend-chip legend-reject"><span aria-hidden="true">✕</span> <span class="sr-only">Query badge:</span>reject</span>
            </div>
            <div class="legend-group">
              <span class="legend-label">Edge status:</span>
              <span class="legend-chip legend-supported"><span aria-hidden="true">●</span> <span class="sr-only">Edge status:</span>supported</span>
              <span class="legend-chip legend-weak"><span aria-hidden="true">▲</span> <span class="sr-only">Edge status:</span>weak</span>
              <span class="legend-chip legend-conflict"><span aria-hidden="true">✕</span> <span class="sr-only">Edge status:</span>conflict</span>
              <span class="legend-chip legend-manual"><span aria-hidden="true">🔒</span> <span class="sr-only">Edge status:</span>manual lock</span>
            </div>
          </div>
          <div ref="cyContainer" class="graph-canvas" @dragover.prevent @drop="onDrop"></div>
        </div>

        <GraphControls
          class="controls-column"
          :variables="variables"
          :selected-treatment="selectedTreatment"
          :selected-outcome="selectedOutcome"
          :selected-method="selectedMethod"
          @update:selected-treatment="selectedTreatment = $event"
          @update:selected-outcome="selectedOutcome = $event"
          @update:selected-method="selectedMethod = $event"
          @save="saveGraph"
          @suggest="suggestGraphEdges"
          @run="computeInference"
        />
      </section>

      <InferenceResult
        :inference-result="inferenceResult"
        :causal-graph-image-url="causalGraphImageUrl"
      />

      <section v-if="assessmentResult" class="assessment-panel">
        <div class="assessment-header">
          <h3 class="assessment-title">Identification &amp; Admissibility</h3>
          <span :class="['assessment-badge', `assessment-badge-${assessmentResult.badge || 'caution'}`]">
            {{ assessmentResult.badge || "caution" }}
          </span>
        </div>

        <ul class="assessment-reasons" v-if="assessmentResult.reasons?.length">
          <li v-for="reason in assessmentResult.reasons" :key="reason">{{ reason }}</li>
        </ul>

        <p class="assessment-line"><strong>Estimand:</strong> {{ assessmentResult.selected_estimand || "ATE" }}</p>
        <p class="assessment-line"><strong>Suggested method:</strong> {{ assessmentResult.suggested_method || "n/a" }}</p>
        <p class="assessment-line">
          <strong>Overlap:</strong>
          {{ assessmentResult.overlap_ok ? "ok" : "check warnings" }}
        </p>

        <ul class="assessment-warnings" v-if="assessmentResult.overlap_warnings?.length">
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
          <button class="panel-action" type="button" @click="runRobustness">Run checks</button>
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
          <div class="assessment-card" v-if="whatIfResult">
            <h4>What-if result</h4>
            <p>Baseline outcome mean: {{ whatIfResult.baseline_outcome_mean }}</p>
            <p>Baseline treatment mean: {{ whatIfResult.baseline_treatment_mean }}</p>
            <p>Estimated ATE: {{ whatIfResult.estimated_ate ?? "n/a" }}</p>
            <p>Counterfactual outcome mean: {{ whatIfResult.counterfactual_outcome_mean ?? "n/a" }}</p>
            <p>{{ whatIfResult.note }}</p>
          </div>

          <div class="assessment-card" v-if="rootCauseResult">
            <h4>Anomaly attribution</h4>
            <ul>
              <li v-for="item in rootCauseResult.anomaly_attribution" :key="`an-${item.variable}`">
                {{ item.variable }}: {{ item.score }}
              </li>
            </ul>
          </div>

          <div class="assessment-card" v-if="rootCauseResult">
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
            <strong>{{ item.source }} → {{ item.target }}</strong>
            <span> · {{ item.status }} · {{ item.evidenceCount }} evidence item(s)</span>
          </li>
        </ul>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"

import DatasetSidebar from "./components/DatasetSidebar.vue"
import GraphControls from "./components/GraphControls.vue"
import InferenceResult from "./components/InferenceResult.vue"
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
const inferenceResult = ref(null)
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

const cyContainer = ref(null)
const cy = ref(null)
const startNode = ref(null)
const endNode = ref(null)

function setStatus(message, type = "success") {
  statusMessage.value = message
  statusType.value = type
}

function clearStatus() {
  statusMessage.value = ""
}

async function initializeGraph() {
  if (!cyContainer.value) {
    return
  }

  const cytoscape = (await import("cytoscape")).default

  cy.value = cytoscape({
    container: cyContainer.value,
    elements: [],
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "background-color": "#66B",
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#888",
          "target-arrow-color": "#888",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
        },
      },
      {
        selector: "edge.status-supported",
        style: {
          "line-color": "#10b981",
          "target-arrow-color": "#10b981",
        },
      },
      {
        selector: "edge.status-weak",
        style: {
          "line-color": "#f59e0b",
          "target-arrow-color": "#f59e0b",
        },
      },
      {
        selector: "edge.status-conflict",
        style: {
          "line-color": "#ef4444",
          "target-arrow-color": "#ef4444",
        },
      },
      {
        selector: "edge.manual-lock",
        style: {
          width: 4,
        },
      },
    ],
    layout: { name: "grid" },
  })

  cy.value.on("cxttapstart", "node", (event) => {
    startNode.value = event.target
    endNode.value = null
    event.originalEvent.preventDefault()
  })

  cy.value.on("cxtdragover", "node", (event) => {
    if (startNode.value) {
      endNode.value = event.target
    }
  })

  cy.value.on("cxttapend", () => {
    if (startNode.value && endNode.value && startNode.value !== endNode.value) {
      cy.value.add({
        group: "edges",
        data: {
          source: startNode.value.id(),
          target: endNode.value.id(),
        },
      })
    }
    startNode.value = null
    endNode.value = null
  })

  cy.value.on("tap", "edge", (event) => event.target.remove())
  cy.value.on("tap", "node", (event) => event.target.remove())
}

function onDragStart(variableName, event) {
  event.dataTransfer.setData("text/plain", variableName)
  event.dataTransfer.dropEffect = "copy"
}

function onDrop(event) {
  const variableName = event.dataTransfer.getData("text/plain")
  if (!variableName || !cy.value) {
    return
  }

  const rect = cyContainer.value.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top

  if (cy.value.getElementById(variableName).length === 0) {
    cy.value.add({
      group: "nodes",
      data: {
        id: variableName,
        label: variableName,
      },
      position: { x, y },
    })
  }
}

function ensureNodeOnCanvas(variableName, index, total) {
  if (!cy.value || !cyContainer.value || cy.value.getElementById(variableName).length > 0) {
    return
  }

  const width = cyContainer.value.clientWidth || 600
  const height = cyContainer.value.clientHeight || 420
  const radius = Math.max(120, Math.min(width, height) * 0.35)
  const angle = (2 * Math.PI * index) / Math.max(total, 1)

  cy.value.add({
    group: "nodes",
    data: {
      id: variableName,
      label: variableName,
    },
    position: {
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
    },
  })
}

function addSuggestedEdgesToGraph(edges) {
  if (!cy.value || !Array.isArray(edges)) {
    return 0
  }

  let addedCount = 0

  edges.forEach((edge, index) => {
    const source = edge?.source
    const target = edge?.target

    if (!source || !target || source === target) {
      return
    }

    ensureNodeOnCanvas(source, index * 2, edges.length * 2)
    ensureNodeOnCanvas(target, index * 2 + 1, edges.length * 2)

    const status = edge?.verification_status || edge?.status || ""
    const manualLock = Boolean(edge?.manual_lock)
    const evidence = Array.isArray(edge?.evidence) ? edge.evidence : []

    const existing = cy.value
      .edges()
      .toArray()
      .find((existingEdge) => {
        return existingEdge.data("source") === source && existingEdge.data("target") === target
      })

    if (existing) {
      existing.data("status", status)
      existing.data("manual_lock", manualLock)
      existing.data("evidence", evidence)
      applyEdgeClass(existing)
      return
    }

    const created = cy.value.add({
      group: "edges",
      data: {
        source,
        target,
        status,
        manual_lock: manualLock,
        evidence,
      },
    })
    applyEdgeClass(created)
    addedCount += 1
  })

  return addedCount
}

function applyEdgeClass(edgeElement) {
  edgeElement.removeClass("status-supported status-weak status-conflict manual-lock")
  const status = edgeElement.data("status")
  if (status === "supported") {
    edgeElement.addClass("status-supported")
  } else if (status === "weak") {
    edgeElement.addClass("status-weak")
  } else if (status === "conflict" || status === "rejected") {
    edgeElement.addClass("status-conflict")
  }
  if (edgeElement.data("manual_lock")) {
    edgeElement.addClass("manual-lock")
  }
}

async function refreshGraphDetails() {
  if (!graphId.value) {
    return
  }

  const details = await fetchGraphDetails(graphId.value)
  const detailEdges = Array.isArray(details?.edges) ? details.edges : []
  addSuggestedEdgesToGraph(detailEdges)

  edgeEvidenceList.value = detailEdges.map((edge) => ({
    key: `${edge.source}:${edge.target}`,
    source: edge.source,
    target: edge.target,
    status: edge.status || "unknown",
    evidenceCount: Array.isArray(edge.evidence) ? edge.evidence.length : 0,
  }))
}

function relayoutGraph() {
  if (!cy.value) {
    return
  }

  cy.value
    .layout({
      name: "cose",
      animate: false,
      fit: true,
      padding: 30,
    })
    .run()
}

async function handleFileUpload(event) {
  const file = event.target.files?.[0]
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
    selectedTreatment.value = ""
    selectedOutcome.value = ""
    inferenceResult.value = null
    causalGraphImageUrl.value = ""
    assessmentResult.value = null
    robustnessResult.value = null
    whatIfResult.value = null
    rootCauseResult.value = null
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "CSV upload failed."), "error")
  }
}

async function saveGraph() {
  if (!graphId.value) {
    setStatus("Upload a dataset before saving graph edges.", "error")
    return
  }

  const edges = cy.value
    .edges()
    .map((edge) => ({
      source: edge.data("source"),
      target: edge.data("target"),
      directed: true,
      manual_lock: Boolean(edge.data("manual_lock")),
      evidence: Array.isArray(edge.data("evidence")) ? edge.data("evidence") : [],
    }))
    .toArray()

  try {
    const responseData = await saveGraphApi({
      graph_id: graphId.value,
      name: "UserGraph",
      edges,
    })
    graphId.value = responseData.graph_id
    await refreshGraphDetails()
    setStatus(`Graph saved with ID ${graphId.value}.`)
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to save graph."), "error")
  }
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

    const addedCount = addSuggestedEdgesToGraph(responseData.edges)
    edgeEvidenceList.value = (responseData.edges || []).map((edge) => ({
      key: `${edge.source}:${edge.target}`,
      source: edge.source,
      target: edge.target,
      status: edge.verification_status || edge.status || "unknown",
      evidenceCount: Array.isArray(edge.evidence) ? edge.evidence.length : 0,
    }))
    if (addedCount > 0) {
      relayoutGraph()
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
    Boolean(cy.value) &&
    cy.value.nodes().length >= 2
  )
}

async function refreshAssessment(showErrors = false) {
  if (!canRunAssessment()) {
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
    assessmentResult.value = assessment
    return assessment
  } catch (error) {
    assessmentResult.value = null
    if (showErrors) {
      setStatus(getErrorMessage(error, "Assessment failed."), "error")
    }
    return null
  }
}

async function runRobustness() {
  if (!canRunAssessment()) {
    setStatus("Select treatment/outcome and ensure graph has at least two nodes.", "error")
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

async function computeInference() {
  if (!graphId.value) {
    setStatus("Upload a dataset before running inference.", "error")
    return
  }

  if (!selectedTreatment.value || !selectedOutcome.value) {
    setStatus("Select treatment and outcome variables.", "error")
    return
  }

  if (cy.value.nodes().length < 2) {
    setStatus("At least two nodes are required.", "error")
    return
  }

  try {
    const assessment = await refreshAssessment(true)
    if (!assessment) {
      return
    }

    if (assessment?.badge === "reject") {
      setStatus(
        assessment?.reasons?.[0] || "Identification failed for this query. Update the graph.",
        "error",
      )
      return
    }

    const responseData = await runInference({
      treatment: selectedTreatment.value,
      outcome: selectedOutcome.value,
      graph_id: graphId.value,
      method_name: selectedMethod.value,
    })

    inferenceResult.value = responseData.estimated_effect ?? "N/A"
    causalGraphImageUrl.value = responseData.graph_image ?? ""
    clearStatus()
  } catch (error) {
    setStatus(getErrorMessage(error, "Causal inference failed."), "error")
  }
}

onMounted(async () => {
  try {
    await initializeGraph()
  } catch {
    setStatus("Failed to initialize graph editor.", "error")
  }
})

watch([graphId, selectedTreatment, selectedOutcome], () => {
  void refreshAssessment(false)
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

.graph-canvas {
  flex: 1;
  min-height: 420px;
  border: 2px dashed #d1d5db;
  border-radius: 6px;
  background: var(--color-background);
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

.panel-action {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-background);
  color: var(--color-text);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 0.84rem;
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

  .graph-canvas {
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
