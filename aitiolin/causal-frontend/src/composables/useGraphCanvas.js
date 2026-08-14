function sanitizeToken(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

export function createNodeId(variableId, fallbackName = "") {
  if (variableId !== null && variableId !== undefined && variableId !== "") {
    return `variable-${variableId}`
  }

  const slug = sanitizeToken(fallbackName)
  return `name-${slug || "unknown"}`
}

export function buildVariableLookups(variables = []) {
  const byId = new Map()
  const byName = new Map()

  for (const item of variables) {
    byId.set(item.id, item)
    byName.set(item.name, item)
  }

  return { byId, byName }
}

export function serializeGraphSnapshot(cy) {
  if (!cy) {
    return { nodes: [], edges: [] }
  }

  const nodes = cy.nodes().map((node) => ({
    id: node.id(),
    variableId: node.data("variableId") ?? null,
    variableName: node.data("variableName") || node.data("label") || node.id(),
    label: node.data("label") || node.data("variableName") || node.id(),
    position: {
      x: node.position("x"),
      y: node.position("y"),
    },
  }))

  const edges = cy.edges().map((edge) => ({
    sourceId: edge.source().id(),
    targetId: edge.target().id(),
    source: edge.source().data("variableName") || edge.source().data("label") || edge.source().id(),
    target: edge.target().data("variableName") || edge.target().data("label") || edge.target().id(),
    directed: true,
    manual_lock: Boolean(edge.data("manual_lock")),
    evidence: Array.isArray(edge.data("evidence")) ? edge.data("evidence") : [],
    status: edge.data("status") || "",
  }))

  return { nodes, edges }
}

export function createEdgeSignature(edges = []) {
  return [...edges]
    .map((edge) => {
      const source = String(edge.source ?? "")
      const target = String(edge.target ?? "")
      const manualLock = edge.manual_lock ? "1" : "0"
      return `${source}->${target}:${manualLock}`
    })
    .sort()
    .join("|")
}

function normalizeCoordinate(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return 0
  }

  return Math.round(parsed * 1000) / 1000
}

export function createGraphStateSignature(graph = {}) {
  const nodes = [...(graph.nodes || [])]
    .map((node) => {
      return `${node.id || node.variableName || node.name}:${normalizeCoordinate(node.position?.x)}:${normalizeCoordinate(node.position?.y)}`
    })
    .sort()
    .join("|")

  return `${nodes}::${createEdgeSignature(graph.edges || [])}`
}