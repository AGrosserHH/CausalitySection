# causal-frontend

Vue 3 + Vite client for the CausalGUI project.

## Requirements

- Node.js 20+
- npm

## Install

```sh
npm install
```

## Run

```sh
npm run dev
```

The app runs on `http://localhost:5173` and proxies API calls to `http://127.0.0.1:8000`.

## Quality Commands

```sh
npm run lint
npm run test
npm run build
```

## Main Structure

- `src/AppRoot.vue` - root orchestration component (entry point via `main.js`)
- `src/App.vue` - legacy shell (kept for reference; not active)
- `src/components/GraphCanvas.vue` - Cytoscape canvas (undo/redo, edge handles, right-drag fallback)
- `src/components/DatasetSidebar.vue` - CSV upload, variable list, drag-to-canvas
- `src/components/GraphControls.vue` - layout, delete, zoom, inference trigger
- `src/components/GraphCopilotPanel.vue` - LLM edge suggestions with verifier breakdown
- `src/components/IdentificationPanel.vue` - admissibility checklist, adjustment sets, backdoor paths
- `src/components/RobustnessDashboard.vue` - estimator comparison, refutations, sensitivity, export
- `src/components/TimeSeriesPanel.vue` - rolling-window config, edge stability, per-window preview
- `src/components/InferenceResult.vue` - causal inference output display
- `src/composables/useCausalApi.js` - API client wrapper (all endpoints)
- `src/composables/useGraphCanvas.js` - pure graph helpers (node ids, serialization, state signatures)

## UI Workflow

1. Upload a CSV in the Dataset panel.
2. Drag variables to the canvas to create nodes.
3. Drag from a node handle to another node to create an edge (or right-drag as fallback).
4. Click **Graph Copilot** to get LLM-powered edge suggestions. Review each in the Copilot panel and accept, lock-accept, or skip.
5. Open **Identification** to check DAG validity, admissibility, backdoor paths, and adjustment sets.
6. Select treatment/outcome and click **Estimate Effect**.
7. Open **Robustness Dashboard** to compare estimators, run refutations, and see the robustness score. Export results as JSON or CSV.
8. Open **Time Series** to configure rolling-window analysis and inspect per-edge stability across time windows.

Notes:

- CSV upload loads variables and preview only; it does not auto-create graph nodes/edges.
- The **Reset** button clears graph + analysis outputs but keeps uploaded dataset variables available.
- Shift-drag performs box selection; Canvas Details shows selected node/edge metadata.
- Node positions are included in save payloads and restored from backend graph details.
- Graph Copilot requires `OPENAI_API_KEY` configured in `causalproject/.env` on the backend.

## Debug Visibility

Inference actions log progress in browser console:

- run requested
- blocked conditions (if any)
- inference started payload
- inference completed response
- inference failure details

This helps diagnose UI vs API issues quickly during development.

## Troubleshooting

- Cannot draw edges:
	- Confirm you already dropped at least two nodes on the canvas.
	- Preferred gesture: drag from a node handle to another node.
	- Fallback gesture: right-drag from source node to target node.
	- If selection feels stuck, click empty canvas first and retry.
	- Hard refresh the browser (Ctrl+F5) after frontend updates.
