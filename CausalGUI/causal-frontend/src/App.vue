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
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue"

import DatasetSidebar from "./components/DatasetSidebar.vue"
import GraphControls from "./components/GraphControls.vue"
import InferenceResult from "./components/InferenceResult.vue"
import { useCausalApi } from "./composables/useCausalApi"

const { uploadCsv, saveGraph: saveGraphApi, runInference, suggestEdges, getErrorMessage } = useCausalApi()

const variables = ref([])
const graphId = ref(null)
const inferenceResult = ref(null)
const causalGraphImageUrl = ref("")
const selectedTreatment = ref("")
const selectedOutcome = ref("")
const selectedMethod = ref("")

const statusMessage = ref("")
const statusType = ref("success")

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

    const alreadyExists = cy.value
      .edges()
      .toArray()
      .some((existingEdge) => {
        return (
          existingEdge.data("source") === source && existingEdge.data("target") === target
        )
      })

    if (alreadyExists) {
      return
    }

    cy.value.add({
      group: "edges",
      data: {
        source,
        target,
      },
    })
    addedCount += 1
  })

  return addedCount
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
    }))
    .toArray()

  try {
    const responseData = await saveGraphApi({
      graph_id: graphId.value,
      name: "UserGraph",
      edges,
    })
    graphId.value = responseData.graph_id
    setStatus(`Graph saved with ID ${graphId.value}.`)
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to save graph."), "error")
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

async function suggestGraphEdges() {
  if (!variables.value.length || variables.value.length < 2) {
    setStatus("Upload a dataset with at least two variables before AI suggestions.", "error")
    return
  }

  try {
    const responseData = await suggestEdges({
      variables: variables.value.map((item) => item.name),
      max_edges: 10,
      context: "Suggest plausible causal relationships for the current dataset variables.",
    })

    const addedCount = addSuggestedEdgesToGraph(responseData.edges)
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

onMounted(async () => {
  try {
    await initializeGraph()
  } catch {
    setStatus("Failed to initialize graph editor.", "error")
  }
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
}
</style>
