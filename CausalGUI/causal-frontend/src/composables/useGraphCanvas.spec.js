import { describe, expect, it } from "vitest"

import { buildVariableLookups, createEdgeSignature, createGraphStateSignature, createNodeId } from "./useGraphCanvas"

describe("useGraphCanvas helpers", () => {
  it("creates stable node ids from backend ids", () => {
    expect(createNodeId(42, "Revenue")).toBe("variable-42")
  })

  it("falls back to sanitized names when an id is missing", () => {
    expect(createNodeId(null, "Monthly Charges")).toBe("name-monthly-charges")
  })

  it("builds lookups by id and name", () => {
    const lookups = buildVariableLookups([
      { id: 1, name: "A" },
      { id: 2, name: "B" },
    ])

    expect(lookups.byId.get(1)?.name).toBe("A")
    expect(lookups.byName.get("B")?.id).toBe(2)
  })

  it("normalizes edge signatures independent of order", () => {
    const first = createEdgeSignature([
      { source: "B", target: "C", manual_lock: false },
      { source: "A", target: "B", manual_lock: true },
    ])
    const second = createEdgeSignature([
      { source: "A", target: "B", manual_lock: true },
      { source: "B", target: "C", manual_lock: false },
    ])

    expect(first).toBe(second)
  })

  it("includes node positions in graph state signatures", () => {
    const first = createGraphStateSignature({
      nodes: [{ id: "variable-1", position: { x: 10, y: 20 } }],
      edges: [],
    })
    const second = createGraphStateSignature({
      nodes: [{ id: "variable-1", position: { x: 10, y: 21 } }],
      edges: [],
    })

    expect(first).not.toBe(second)
  })
})