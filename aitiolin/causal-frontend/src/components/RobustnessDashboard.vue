<template>
  <section class="robustness-panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">Refutation & Sensitivity Dashboard</h3>
        <p class="panel-subtitle">Cross-estimator agreement, refuters, and sensitivity curves.</p>
      </div>
      <div class="panel-actions">
        <button class="panel-action primary" type="button" :disabled="running" @click="$emit('run')">
          <span v-if="running" class="spinner" aria-hidden="true"></span>
          {{ running ? "Running checks..." : "Run checks" }}
        </button>
        <button class="panel-action" type="button" :disabled="!result || running" @click="$emit('export-json')">Export JSON</button>
        <button class="panel-action" type="button" :disabled="!result || running" @click="$emit('export-csv')">Export CSV</button>
      </div>
    </div>

    <div v-if="running" class="running-banner" role="status">
      <span class="spinner" aria-hidden="true"></span>
      Robustness analysis is running: comparing estimators, applying refuters, and sweeping
      confounder sensitivity. On larger datasets this can take a minute - the results will appear
      here when finished.
    </div>

    <template v-if="result && !running">
      <div class="metric-grid">
        <article class="metric-card">
          <span class="metric-label">Baseline method</span>
          <strong>{{ result.baseline_method || 'n/a' }}</strong>
        </article>
        <article class="metric-card">
          <span class="metric-label">Baseline effect</span>
          <strong>{{ formatMetric(result.baseline_estimate) }}</strong>
        </article>
        <article class="metric-card">
          <span class="metric-label">Robustness score</span>
          <strong>{{ formatPercent(result.robustness_score) }}</strong>
        </article>
      </div>

      <div v-if="result.diagnostics?.length" class="diagnostic-grid">
        <article v-for="item in result.diagnostics" :key="item.label" class="metric-card">
          <span class="metric-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.details }}</p>
        </article>
      </div>

      <div class="content-grid">
        <article class="panel-card">
          <h4>Estimator comparison</h4>
          <ul class="compact-list">
            <li v-for="item in result.estimator_comparison || []" :key="item.method_name">
              <strong>{{ item.method_name }}</strong>
              <span> | {{ item.error ? 'error' : formatMetric(item.estimated_effect) }}</span>
              <span v-if="item.error"> | {{ item.error }}</span>
            </li>
          </ul>
        </article>

        <article class="panel-card">
          <h4>Refuters</h4>
          <ul class="compact-list">
            <li v-for="(value, key) in result.refutations || {}" :key="key">
              <strong>{{ key }}</strong>
              <span> | {{ value.status }}</span>
              <span v-if="value.delta !== null && value.delta !== undefined"> | delta {{ formatMetric(value.delta) }}</span>
            </li>
          </ul>
        </article>

        <article class="panel-card">
          <h4>Sensitivity</h4>
          <ul class="compact-list">
            <li v-for="(value, key) in result.sensitivity || {}" :key="key">
              <strong>{{ key }}</strong>
              <span> | {{ value.status }}</span>
              <span v-if="value.delta !== null && value.delta !== undefined"> | delta {{ formatMetric(value.delta) }}</span>
              <span v-if="value.robustness_value !== null && value.robustness_value !== undefined">
                | robustness value {{ formatMetric(value.robustness_value) }}
                (an unobserved confounder would need to explain {{ formatPercent(value.robustness_value) }} of the
                residual variance of both treatment and outcome to bring the effect to zero)
              </span>
            </li>
          </ul>
        </article>
      </div>

      <article v-if="result.sensitivity_points?.length" class="panel-card">
        <h4>Confounder sensitivity sweep</h4>
        <ul class="compact-list">
          <li v-for="point in result.sensitivity_points" :key="point.confounder_strength">
            <strong>{{ point.confounder_strength }}</strong>
            <span> | adjusted effect {{ formatMetric(point.adjusted_effect) }}</span>
          </li>
        </ul>
      </article>
    </template>
  </section>
</template>

<script setup>
defineProps({
  result: {
    type: Object,
    default: null,
  },
  running: {
    type: Boolean,
    default: false,
  },
})

defineEmits(["run", "export-json", "export-csv"])

function formatMetric(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return parsed.toFixed(4)
}

function formatPercent(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return `${Math.round(parsed * 100)}%`
}
</script>

<style scoped>
.robustness-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.panel-title {
  margin: 0;
  color: var(--color-heading);
}

.running-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e40af;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.92rem;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: robustness-spin 0.8s linear infinite;
  vertical-align: -2px;
  margin-right: 6px;
}

.running-banner .spinner {
  margin-right: 0;
}

@keyframes robustness-spin {
  to {
    transform: rotate(360deg);
  }
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
  background: #059669;
  border-color: #059669;
  color: white;
}

.panel-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.metric-grid,
.diagnostic-grid,
.content-grid {
  display: grid;
  gap: 10px;
}

.metric-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.diagnostic-grid,
.content-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-card,
.panel-card {
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

.metric-card p,
.panel-card h4 {
  margin: 0 0 8px;
}

.compact-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}

@media (max-width: 900px) {
  .metric-grid,
  .diagnostic-grid,
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
