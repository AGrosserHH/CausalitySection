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
