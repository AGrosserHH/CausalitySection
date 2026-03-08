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

- `src/App.vue` - page orchestration
- `src/components/` - UI components
- `src/composables/useCausalApi.js` - API client wrapper

## UI Workflow

1. Upload a CSV in the Dataset panel.
2. Drag variables to the canvas to create nodes.
3. Drag from a node handle to another node to create an edge.
4. Right-drag from one node to another as fallback if handle gestures are not available.
5. Use controls for auto-layout, delete selected, undo/redo, zoom in/out, fit, and center.
6. Select treatment/outcome and click **Run Inference**.

Notes:

- CSV upload loads variables and preview only; it does not auto-create graph nodes/edges.
- The **Reset** button clears graph + analysis outputs but keeps uploaded dataset variables available.
- Shift-drag performs box selection and the Canvas Details panel shows selected node/edge metadata.
- Node positions are included in save payloads and restored from backend graph details.

## Debug Visibility

Inference actions log progress in browser console:

- run requested
- blocked conditions (if any)
- inference started payload
- inference completed response
- inference failure details

This helps diagnose UI vs API issues quickly during development.
