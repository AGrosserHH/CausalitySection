<template>
  <div
    ref="canvasShell"
    class="graph-canvas-shell"
    tabindex="0"
    @dragover.prevent
    @drop="onDrop"
    @contextmenu.prevent
    @keydown="onCanvasKeydown"
  >
    <div ref="cyContainer" class="graph-canvas"></div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue"

import {
  buildVariableLookups,
  createEdgeSignature,
  createGraphStateSignature,
  createNodeId,
  serializeGraphSnapshot,
} from "../composables/useGraphCanvas"

const graphSnapshotCache = new Map()
const graphHistoryCache = new Map()
const MAX_HISTORY_ENTRIES = 40

const props = defineProps({
  variables: {
    type: Array,
    default: () => [],
  },
  snapshotKey: {
    type: String,
    default: "graph-editor",
  },
})

const emit = defineEmits(["graph-change", "selection-change"])

const canvasShell = ref(null)
const cyContainer = ref(null)
const cy = shallowRef(null)
const edgeHandles = shallowRef(null)
const resizeObserver = shallowRef(null)
const suppressHistory = ref(false)
const fallbackEdgeSource = shallowRef(null)
const fallbackEdgeTarget = shallowRef(null)

const variableLookups = computed(() => buildVariableLookups(props.variables))

function getActiveSnapshotKey() {
  return props.snapshotKey || "graph-editor"
}

function cloneSnapshot(snapshot) {
  return JSON.parse(JSON.stringify(snapshot || { nodes: [], edges: [] }))
}

function getHistoryState() {
  const key = getActiveSnapshotKey()
  if (!graphHistoryCache.has(key)) {
    graphHistoryCache.set(key, { entries: [], index: -1 })
  }

  return graphHistoryCache.get(key)
}

function canUndo() {
  return getHistoryState().index > 0
}

function canRedo() {
  const history = getHistoryState()
  return history.index >= 0 && history.index < history.entries.length - 1
}

function emitSelectionChange(payload = null) {
  emit("selection-change", payload)
}

function recordHistory(snapshot) {
  const history = getHistoryState()
  const signature = createGraphStateSignature(snapshot)
  const currentSnapshot = history.entries[history.index]

  if (currentSnapshot && createGraphStateSignature(currentSnapshot) === signature) {
    return
  }

  history.entries = history.entries.slice(0, history.index + 1)
  history.entries.push(cloneSnapshot(snapshot))
  if (history.entries.length > MAX_HISTORY_ENTRIES) {
    history.entries.shift()
  }
  history.index = history.entries.length - 1
}

function emitGraphChange(options = {}) {
  const { record = true } = options
  const snapshot = serializeGraphSnapshot(cy.value)
  graphSnapshotCache.set(getActiveSnapshotKey(), snapshot)
  if (record && !suppressHistory.value) {
    recordHistory(snapshot)
  }
  emit("graph-change", {
    nodeCount: snapshot.nodes.length,
    edgeCount: snapshot.edges.length,
    edgeSignature: createEdgeSignature(snapshot.edges),
    graphSignature: createGraphStateSignature(snapshot),
    canUndo: canUndo(),
    canRedo: canRedo(),
  })
}

function buildEdgeLabel(status, manualLock) {
  const parts = []
  if (status) {
    parts.push(status)
  }
  if (manualLock) {
    parts.push("locked")
  }
  return parts.join(" · ")
}

function applyEdgeClass(edgeElement) {
  const status = edgeElement.data("status")
  const manualLock = Boolean(edgeElement.data("manual_lock"))
  edgeElement.data("statusLabel", buildEdgeLabel(status, manualLock))
  edgeElement.removeClass("status-supported status-weak status-conflict manual-lock")
  if (status === "supported") {
    edgeElement.addClass("status-supported")
  } else if (status === "weak") {
    edgeElement.addClass("status-weak")
  } else if (status === "conflict" || status === "rejected") {
    edgeElement.addClass("status-conflict")
  }
  if (manualLock) {
    edgeElement.addClass("manual-lock")
  }
}

function addEdgeBetweenNodes(sourceNode, targetNode, edgeData = {}) {
  if (!cy.value || !sourceNode || !targetNode || sourceNode.id() === targetNode.id()) {
    return false
  }

  const existing = findEdge(sourceNode.id(), targetNode.id())
  if (existing) {
    return false
  }

  const created = cy.value.add({
    group: "edges",
    data: {
      source: sourceNode.id(),
      target: targetNode.id(),
      status: edgeData.status || "",
      manual_lock: Boolean(edgeData.manual_lock),
      evidence: Array.isArray(edgeData.evidence) ? edgeData.evidence : createManualEvidence(),
    },
  })
  applyEdgeClass(created)
  return true
}

function getSelectionPayload() {
  if (!cy.value) {
    return null
  }

  const selected = cy.value.$(":selected")
  if (!selected.length) {
    return null
  }

  if (selected.length > 1) {
    return {
      type: "multi",
      count: selected.length,
      nodeCount: selected.nodes().length,
      edgeCount: selected.edges().length,
    }
  }

  const element = selected.first()
  if (element.isNode()) {
    return {
      type: "node",
      label: element.data("label"),
      variableId: element.data("variableId") ?? null,
      position: {
        x: Math.round(element.position("x")),
        y: Math.round(element.position("y")),
      },
    }
  }

  return {
    type: "edge",
    source: element.source().data("label") || element.source().id(),
    target: element.target().data("label") || element.target().id(),
    status: element.data("status") || "manual",
    manualLock: Boolean(element.data("manual_lock")),
    evidenceCount: Array.isArray(element.data("evidence")) ? element.data("evidence").length : 0,
  }
}

function findEdge(sourceId, targetId, excludeId = "") {
  if (!cy.value) {
    return null
  }

  return (
    cy.value
      .edges()
      .toArray()
      .find((edge) => {
        return edge.id() !== excludeId && edge.data("source") === sourceId && edge.data("target") === targetId
      }) || null
  )
}

function getViewportPosition(clientX, clientY) {
  const rect = cyContainer.value?.getBoundingClientRect()
  const pan = cy.value?.pan() || { x: 0, y: 0 }
  const zoom = cy.value?.zoom() || 1

  if (!rect) {
    return { x: 0, y: 0 }
  }

  return {
    x: (clientX - rect.left - pan.x) / zoom,
    y: (clientY - rect.top - pan.y) / zoom,
  }
}

function getDefaultPosition(index = 0, total = 1) {
  const width = cyContainer.value?.clientWidth || 600
  const height = cyContainer.value?.clientHeight || 420
  const radius = Math.max(120, Math.min(width, height) * 0.35)
  const angle = (2 * Math.PI * index) / Math.max(total, 1)

  return {
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius,
  }
}

function resolveVariable(input) {
  if (!input) {
    return null
  }

  if (input.id !== null && input.id !== undefined && variableLookups.value.byId.has(input.id)) {
    return variableLookups.value.byId.get(input.id)
  }

  if (input.name && variableLookups.value.byName.has(input.name)) {
    return variableLookups.value.byName.get(input.name)
  }

  return {
    id: input.id ?? null,
    name: input.name || "Unknown",
  }
}

function ensureNode(variableInput, position = null, index = 0, total = 1) {
  if (!cy.value) {
    return null
  }

  const variable = resolveVariable(variableInput)
  if (!variable?.name) {
    return null
  }

  const nodeId = createNodeId(variable.id, variable.name)
  const existing = cy.value.getElementById(nodeId)
  if (existing.length > 0) {
    return existing
  }

  return cy.value.add({
    group: "nodes",
    data: {
      id: nodeId,
      variableId: variable.id,
      variableName: variable.name,
      label: variable.name,
    },
    position: position || getDefaultPosition(index, total),
  })
}

function createManualEvidence() {
  return [
    {
      evidence_type: "manual",
      status: "supported",
      details: { reason: "User-authored edge" },
    },
  ]
}

function restoreSnapshot(snapshot, options = {}) {
  const { recordHistory: shouldRecordHistory = false } = options
  if (!cy.value) {
    return
  }

  suppressHistory.value = !shouldRecordHistory
  cy.value.elements().remove()
  if (!snapshot) {
    emitGraphChange({ record: shouldRecordHistory })
    emitSelectionChange(null)
    suppressHistory.value = false
    return
  }

  cy.value.batch(() => {
    for (const node of snapshot.nodes || []) {
      const variable = resolveVariable({ id: node.variableId, name: node.variableName || node.label })
      const nodeId = createNodeId(variable?.id ?? node.variableId, variable?.name || node.variableName || node.label)
      cy.value.add({
        group: "nodes",
        data: {
          id: nodeId,
          variableId: variable?.id ?? node.variableId ?? null,
          variableName: variable?.name || node.variableName || node.label,
          label: variable?.name || node.label || node.variableName,
        },
        position: node.position,
      })
    }

    for (const edge of snapshot.edges || []) {
      const sourceNode = ensureNode({ id: null, name: edge.source }, null, 0, 1)
      const targetNode = ensureNode({ id: null, name: edge.target }, null, 0, 1)
      if (!sourceNode || !targetNode) {
        continue
      }

      if (findEdge(sourceNode.id(), targetNode.id())) {
        continue
      }

      const created = cy.value.add({
        group: "edges",
        data: {
          source: sourceNode.id(),
          target: targetNode.id(),
          status: edge.status || "",
          manual_lock: Boolean(edge.manual_lock),
          evidence: Array.isArray(edge.evidence) ? edge.evidence : [],
        },
      })
      applyEdgeClass(created)
    }
  })

  emitGraphChange({ record: shouldRecordHistory })
  emitSelectionChange(null)
  suppressHistory.value = false
}

function buildSnapshotFromGraphData(graphData = {}) {
  const nodeMap = new Map()
  const edges = Array.isArray(graphData.edges) ? graphData.edges : []
  const sourceNodes = Array.isArray(graphData.nodes) ? graphData.nodes : []

  function registerNode(nodeLike = {}) {
    const variable = resolveVariable({ id: nodeLike.id ?? null, name: nodeLike.name || nodeLike.variableName })
    if (!variable?.name) {
      return null
    }

    const nodeId = createNodeId(variable.id, variable.name)
    if (!nodeMap.has(nodeId)) {
      nodeMap.set(nodeId, {
        id: nodeId,
        variableId: variable.id ?? null,
        variableName: variable.name,
        label: variable.name,
        position: nodeLike.position || null,
      })
    }

    return nodeMap.get(nodeId)
  }

  for (const node of sourceNodes) {
    registerNode(node)
  }

  for (const edge of edges) {
    registerNode({ name: edge?.source })
    registerNode({ name: edge?.target })
  }

  const nodes = [...nodeMap.values()]
  nodes.forEach((node, index) => {
    if (!node.position) {
      node.position = getDefaultPosition(index, nodes.length)
    }
  })

  return {
    nodes,
    edges: edges.map((edge) => ({
      source: edge?.source,
      target: edge?.target,
      directed: edge?.directed ?? true,
      manual_lock: Boolean(edge?.manual_lock),
      evidence: Array.isArray(edge?.evidence) ? edge.evidence : [],
      status: edge?.verification_status || edge?.status || "",
    })),
  }
}

async function initializeGraph() {
  if (!cyContainer.value || cy.value) {
    return
  }

  const [{ default: cytoscape }, edgehandlesModule] = await Promise.all([
    import("cytoscape"),
    import("cytoscape-edgehandles"),
  ])

  const registerEdgeHandles = edgehandlesModule.default || edgehandlesModule
  registerEdgeHandles(cytoscape)

  cy.value = cytoscape({
    container: cyContainer.value,
    elements: [],
    boxSelectionEnabled: true,
    selectionType: "additive",
    style: [
      {
        selector: "node",
        style: {
          label: "data(label)",
          color: "#f8fafc",
          "text-valign": "center",
          "text-halign": "center",
          "text-wrap": "wrap",
          "text-max-width": 100,
          "background-color": "#2563eb",
          "border-width": 2,
          "border-color": "#dbeafe",
          width: 54,
          height: 54,
          "font-size": 11,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#f59e0b",
          "border-width": 4,
        },
      },
      {
        selector: "edge",
        style: {
          label: "data(statusLabel)",
          color: "#334155",
          "font-size": 9,
          "text-background-color": "#ffffff",
          "text-background-opacity": 0.85,
          "text-background-padding": 2,
          "text-rotation": "autorotate",
          width: 2,
          "line-color": "#94a3b8",
          "target-arrow-color": "#94a3b8",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
        },
      },
      {
        selector: "edge:selected",
        style: {
          width: 4,
          "line-color": "#f59e0b",
          "target-arrow-color": "#f59e0b",
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
    layout: { name: "preset" },
  })

  edgeHandles.value = cy.value.edgehandles({
    preview: false,
    hoverDelay: 0,
    handleNodes: "node",
    edgeParams: () => ({
      data: {
        status: "",
        manual_lock: false,
        evidence: createManualEvidence(),
      },
    }),
    complete: (sourceNode, targetNode, addedElements) => {
      const createdEdge = addedElements?.edges()?.first()
      if (!createdEdge || createdEdge.empty()) {
        return
      }

      const existing = findEdge(sourceNode.id(), targetNode.id(), createdEdge.id())
      if (existing) {
        createdEdge.remove()
        return
      }

      createdEdge.data({
        status: createdEdge.data("status") || "",
        manual_lock: Boolean(createdEdge.data("manual_lock")),
        evidence: Array.isArray(createdEdge.data("evidence")) ? createdEdge.data("evidence") : createManualEvidence(),
      })
      applyEdgeClass(createdEdge)
      emitGraphChange()
    },
  })

  cy.value.on("cxttapstart", "node", (event) => {
    fallbackEdgeSource.value = event.target
    fallbackEdgeTarget.value = null
    event.originalEvent?.preventDefault?.()
  })

  cy.value.on("cxtdragover", "node", (event) => {
    if (!fallbackEdgeSource.value) {
      return
    }

    fallbackEdgeTarget.value = event.target
    event.originalEvent?.preventDefault?.()
  })

  cy.value.on("cxttapend", () => {
    const didCreateEdge = addEdgeBetweenNodes(fallbackEdgeSource.value, fallbackEdgeTarget.value)
    fallbackEdgeSource.value = null
    fallbackEdgeTarget.value = null

    if (didCreateEdge) {
      emitGraphChange()
    }
  })

  cy.value.on("select unselect", () => {
    emitSelectionChange(getSelectionPayload())
  })

  cy.value.on("dragfreeon", "node", () => {
    emitGraphChange()
    emitSelectionChange(getSelectionPayload())
  })

  cy.value.on("tap", () => {
    canvasShell.value?.focus()
  })

  restoreSnapshot(graphSnapshotCache.get(getActiveSnapshotKey()), {
    recordHistory: !graphHistoryCache.has(getActiveSnapshotKey()),
  })
}

function onDrop(event) {
  if (!cy.value) {
    return
  }

  const rawPayload = event.dataTransfer.getData("application/json") || event.dataTransfer.getData("text/plain")
  if (!rawPayload) {
    return
  }

  let payload = null
  try {
    payload = JSON.parse(rawPayload)
  } catch {
    payload = { name: rawPayload }
  }

  const position = getViewportPosition(event.clientX, event.clientY)
  const node = ensureNode(payload, position)
  if (node) {
    node.position(position)
    emitGraphChange()
    emitSelectionChange(getSelectionPayload())
  }
}

function onCanvasKeydown(event) {
  if (event.key !== "Delete" && event.key !== "Backspace") {
    return
  }

  const removedCount = removeSelectedElements()
  if (removedCount > 0) {
    event.preventDefault()
  }
}

function resizeGraph() {
  if (!cy.value) {
    return
  }

  cy.value.resize()
}

function attachResizeObserver() {
  if (!canvasShell.value) {
    return
  }

  resizeObserver.value = new ResizeObserver(() => {
    resizeGraph()
  })
  resizeObserver.value.observe(canvasShell.value)
}

function syncGraphEdges(edges) {
  return syncGraph({ edges })
}

function syncGraph(graphData) {
  if (!cy.value) {
    return 0
  }

  const snapshot = buildSnapshotFromGraphData(graphData)
  const previousCount = cy.value.edges().length
  restoreSnapshot(snapshot, { recordHistory: true })
  return Math.max(snapshot.edges.length - previousCount, 0)
}

function addSuggestedEdges(edges) {
  if (!cy.value || !Array.isArray(edges)) {
    return { addedCount: 0, nodeAddedCount: 0 }
  }

  let addedCount = 0
  let nodeAddedCount = 0

  cy.value.batch(() => {
    for (const [index, edge] of edges.entries()) {
      const sourceInput = { name: edge?.source }
      const targetInput = { name: edge?.target }
      const sourceNodeId = createNodeId(resolveVariable(sourceInput)?.id, sourceInput.name)
      const targetNodeId = createNodeId(resolveVariable(targetInput)?.id, targetInput.name)
      const hadSource = cy.value.getElementById(sourceNodeId).length > 0
      const hadTarget = cy.value.getElementById(targetNodeId).length > 0
      const sourceNode = ensureNode(sourceInput, null, index * 2, edges.length * 2)
      const targetNode = ensureNode(targetInput, null, index * 2 + 1, edges.length * 2)

      if (!hadSource && sourceNode) {
        nodeAddedCount += 1
      }
      if (!hadTarget && targetNode) {
        nodeAddedCount += 1
      }
      if (!sourceNode || !targetNode || sourceNode.id() === targetNode.id()) {
        continue
      }

      const existing = findEdge(sourceNode.id(), targetNode.id())
      const status = edge?.verification_status || edge?.status || ""
      const manualLock = Boolean(edge?.manual_lock)
      const evidence = Array.isArray(edge?.evidence) ? edge.evidence : []

      if (existing) {
        existing.data("status", status)
        existing.data("manual_lock", manualLock)
        existing.data("evidence", evidence)
        applyEdgeClass(existing)
        continue
      }

      const created = cy.value.add({
        group: "edges",
        data: {
          source: sourceNode.id(),
          target: targetNode.id(),
          status,
          manual_lock: manualLock,
          evidence,
        },
      })
      applyEdgeClass(created)
      addedCount += 1
    }
  })

  emitGraphChange()
  return { addedCount, nodeAddedCount }
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

  emitGraphChange()
}

function zoomAroundCenter(multiplier) {
  if (!cy.value) {
    return
  }

  const containerWidth = cyContainer.value?.clientWidth || 0
  const containerHeight = cyContainer.value?.clientHeight || 0
  cy.value.zoom({
    level: cy.value.zoom() * multiplier,
    renderedPosition: {
      x: containerWidth / 2,
      y: containerHeight / 2,
    },
  })
}

function zoomIn() {
  zoomAroundCenter(1.15)
}

function zoomOut() {
  zoomAroundCenter(1 / 1.15)
}

function fitGraph() {
  if (!cy.value) {
    return
  }

  cy.value.fit(cy.value.elements(), 30)
}

function centerGraph() {
  if (!cy.value) {
    return
  }

  cy.value.center(cy.value.elements())
}

function undo() {
  const history = getHistoryState()
  if (history.index <= 0) {
    return false
  }

  history.index -= 1
  restoreSnapshot(history.entries[history.index], { recordHistory: false })
  return true
}

function redo() {
  const history = getHistoryState()
  if (history.index < 0 || history.index >= history.entries.length - 1) {
    return false
  }

  history.index += 1
  restoreSnapshot(history.entries[history.index], { recordHistory: false })
  return true
}

function removeSelectedElements() {
  if (!cy.value) {
    return 0
  }

  const selected = cy.value.$(":selected")
  const removedCount = selected.length
  if (!removedCount) {
    return 0
  }

  selected.remove()
  emitGraphChange()
  return removedCount
}

function resetGraph() {
  if (!cy.value) {
    return
  }

  graphSnapshotCache.delete(getActiveSnapshotKey())
  graphHistoryCache.delete(getActiveSnapshotKey())
  restoreSnapshot({ nodes: [], edges: [] }, { recordHistory: true })
}

function serializeGraph() {
  const snapshot = serializeGraphSnapshot(cy.value)
  return {
    nodes: snapshot.nodes,
    edges: snapshot.edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      directed: true,
      manual_lock: Boolean(edge.manual_lock),
      evidence: Array.isArray(edge.evidence) ? edge.evidence : [],
    })),
  }
}

function getNodeCount() {
  return cy.value?.nodes().length || 0
}

function hasEdges() {
  return (cy.value?.edges().length || 0) > 0
}

watch(
  () => props.snapshotKey,
  async () => {
    await nextTick()
    if (!cy.value) {
      return
    }

    const snapshot = graphSnapshotCache.get(getActiveSnapshotKey()) || { nodes: [], edges: [] }
    restoreSnapshot(snapshot, {
      recordHistory: !graphHistoryCache.has(getActiveSnapshotKey()),
    })
  },
)

onMounted(async () => {
  await initializeGraph()
  attachResizeObserver()
})

onUnmounted(() => {
  const snapshot = serializeGraphSnapshot(cy.value)
  graphSnapshotCache.set(getActiveSnapshotKey(), snapshot)
  resizeObserver.value?.disconnect()
  edgeHandles.value?.destroy?.()
  cy.value?.destroy()
  cy.value = null
})

defineExpose({
  addSuggestedEdges,
  canRedo,
  canUndo,
  getNodeCount,
  hasEdges,
  centerGraph,
  fitGraph,
  relayoutGraph,
  redo,
  removeSelectedElements,
  resetGraph,
  serializeGraph,
  syncGraph,
  syncGraphEdges,
  undo,
  zoomIn,
  zoomOut,
})
</script>

<style scoped>
.graph-canvas-shell {
  min-width: 0;
  min-height: 420px;
  height: 100%;
  border: 2px dashed #d1d5db;
  border-radius: 6px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(241, 245, 249, 0.96));
  outline: none;
}

.graph-canvas-shell:focus-visible {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
}

.graph-canvas {
  width: 100%;
  height: 100%;
  min-height: 420px;
}

@media (max-width: 768px) {
  .graph-canvas-shell,
  .graph-canvas {
    min-height: 360px;
  }
}
</style>