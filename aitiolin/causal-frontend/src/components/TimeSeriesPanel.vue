<template>
  <section class="time-series-panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">Time-series Mode</h3>
        <p class="panel-subtitle">Lag stability, rolling windows, and dynamic graph snapshots.</p>
      </div>
      <div class="panel-actions">
        <button class="panel-action primary" type="button" @click="$emit('run')">Run time-series analysis</button>
        <button class="panel-action" type="button" :disabled="!hasPreview" @click="$emit('restore-preview')">Restore graph</button>
      </div>
    </div>

    <div class="form-grid">
      <label class="control-label">
        Time column
        <input :value="timeColumn" class="control-input" type="text" placeholder="timestamp" @input="$emit('update:time-column', $event.target.value)" />
      </label>
      <label class="control-label">
        Entity column
        <input :value="entityColumn" class="control-input" type="text" placeholder="optional" @input="$emit('update:entity-column', $event.target.value)" />
      </label>
      <label class="control-label">
        Window count
        <input :value="windowCount" class="control-input" type="number" min="2" max="12" @input="$emit('update:window-count', $event.target.value)" />
      </label>
      <label class="control-label">
        Max lag
        <input :value="maxLag" class="control-input" type="number" min="1" max="12" @input="$emit('update:max-lag', $event.target.value)" />
      </label>
    </div>

    <template v-if="result">
      <div v-if="result.diagnostics?.length" class="diagnostic-grid">
        <article v-for="item in result.diagnostics" :key="item.label" class="diagnostic-card">
          <span class="metric-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.details }}</p>
        </article>
      </div>

      <div class="content-grid">
        <article class="panel-card">
          <h4>Edge stability</h4>
          <ul class="compact-list">
            <li v-for="edge in result.edge_stability || []" :key="`${edge.source}-${edge.target}`">
              <strong>{{ edge.source }} -> {{ edge.target }}</strong>
              <span> | {{ edge.status }}</span>
              <span> | lag {{ edge.best_lag ?? 'n/a' }}</span>
              <span> | strength {{ formatMetric(edge.mean_strength) }}</span>
              <span> | stability {{ formatMetric(edge.stability) }}</span>
            </li>
          </ul>
        </article>

        <article class="panel-card">
          <h4>Dynamic graph windows</h4>
          <div class="window-list">
            <div v-for="(window, index) in result.dynamic_graphs || []" :key="`${window.label}-${index}`" class="window-card">
              <div class="window-header">
                <div>
                  <strong>{{ window.label }}</strong>
                  <p>{{ window.start }} to {{ window.end }}</p>
                </div>
                <button class="panel-action" type="button" @click="$emit('preview-window', index)">Preview</button>
              </div>
              <ul class="compact-list">
                <li v-for="edge in window.edges || []" :key="`${window.label}-${edge.source}-${edge.target}`">
                  {{ edge.source }} -> {{ edge.target }} | {{ formatMetric(edge.strength) }} | lag {{ edge.best_lag ?? 'n/a' }}
                </li>
              </ul>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>

<script setup>
defineProps({
  result: {
    type: Object,
    default: null,
  },
  timeColumn: {
    type: String,
    default: "",
  },
  entityColumn: {
    type: String,
    default: "",
  },
  windowCount: {
    type: [Number, String],
    default: 4,
  },
  maxLag: {
    type: [Number, String],
    default: 3,
  },
  hasPreview: {
    type: Boolean,
    default: false,
  },
})

defineEmits([
  "run",
  "preview-window",
  "restore-preview",
  "update:time-column",
  "update:entity-column",
  "update:window-count",
  "update:max-lag",
])

function formatMetric(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return parsed.toFixed(4)
}
</script>

<style scoped>
.time-series-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-header,
.window-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.panel-title {
  margin: 0;
  color: var(--color-heading);
}

.panel-subtitle {
  margin: 4px 0 0;
  color: var(--vt-c-text-light-2);
  font-size: 0.9rem;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.panel-action {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 8px 12px;
  background: white;
  cursor: pointer;
}

.panel-action.primary {
  background: #0f766e;
  border-color: #0f766e;
  color: white;
}

.panel-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.form-grid,
.diagnostic-grid,
.content-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.diagnostic-grid,
.content-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.control-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--color-heading);
  font-size: 0.9rem;
}

.control-input {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 8px;
}

.diagnostic-card,
.panel-card,
.window-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.metric-label {
  display: block;
  color: var(--vt-c-text-light-2);
  font-size: 0.82rem;
  margin-bottom: 4px;
}

.diagnostic-card p,
.window-card p,
.panel-card h4 {
  margin: 4px 0 0;
}

.window-list,
.compact-list {
  display: grid;
  gap: 8px;
}

.compact-list {
  margin: 0;
  padding-left: 18px;
}

@media (max-width: 900px) {
  .form-grid,
  .diagnostic-grid,
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
