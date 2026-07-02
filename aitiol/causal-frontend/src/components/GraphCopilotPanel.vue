<template>
  <section v-if="suggestions.length" class="copilot-panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">Verifier-backed Graph Copilot</h3>
        <p class="panel-subtitle">Review proposed edges before applying them to the canvas.</p>
      </div>
      <div class="panel-actions">
        <button class="panel-action primary" type="button" @click="$emit('accept-recommended')">Accept recommended</button>
        <button class="panel-action" type="button" @click="$emit('accept-all')">Accept all</button>
        <button class="panel-action ghost" type="button" @click="$emit('clear')">Clear</button>
      </div>
    </div>

    <div v-if="summary" class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">Mean confidence</span>
        <strong>{{ formatPercent(summary.mean_confidence) }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Accept</span>
        <strong>{{ summary.accept_count || 0 }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Review</span>
        <strong>{{ summary.review_count || 0 }}</strong>
      </article>
      <article class="summary-card">
        <span class="summary-label">Conflicts</span>
        <strong>{{ summary.status_counts?.conflict || 0 }}</strong>
      </article>
    </div>

    <div class="suggestion-list">
      <article v-for="(edge, index) in suggestions" :key="`${edge.source}-${edge.target}-${index}`" class="suggestion-card">
        <div class="suggestion-header">
          <div>
            <h4>{{ edge.source }} -> {{ edge.target }}</h4>
            <p class="suggestion-meta">
              <span :class="['badge', `badge-${edge.verification_status || 'weak'}`]">{{ edge.verification_status }}</span>
              <span class="confidence">{{ formatPercent(edge.confidence) }}</span>
              <span>{{ edge.recommended_action || 'review' }}</span>
            </p>
          </div>
          <div class="panel-actions compact">
            <button class="panel-action primary" type="button" @click="$emit('accept-edge', index)">Accept</button>
            <button class="panel-action" type="button" @click="$emit('accept-edge-locked', index)">Lock + accept</button>
          </div>
        </div>

        <p v-if="edge.reason" class="reason">{{ edge.reason }}</p>

        <ul v-if="edge.verifier_breakdown?.length" class="breakdown-list">
          <li v-for="item in edge.verifier_breakdown" :key="`${edge.source}-${edge.target}-${item.name}`">
            <strong>{{ item.name }}</strong>
            <span> | {{ item.status }}</span>
            <span v-if="item.score !== null && item.score !== undefined"> | {{ formatScore(item.score) }}</span>
            <span> | {{ item.details }}</span>
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({
  suggestions: {
    type: Array,
    default: () => [],
  },
  summary: {
    type: Object,
    default: null,
  },
})

defineEmits(["accept-edge", "accept-edge-locked", "accept-recommended", "accept-all", "clear"])

function formatPercent(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return `${Math.round(parsed * 100)}%`
}

function formatScore(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return parsed.toFixed(3)
}
</script>

<style scoped>
.copilot-panel {
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

.panel-actions.compact {
  justify-content: flex-end;
}

.panel-action {
  border: 1px solid var(--color-border);
  background: white;
  border-radius: 999px;
  padding: 8px 12px;
  cursor: pointer;
}

.panel-action.primary {
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: white;
}

.panel-action.ghost {
  background: transparent;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.summary-card,
.suggestion-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.summary-label {
  display: block;
  color: var(--vt-c-text-light-2);
  font-size: 0.82rem;
}

.suggestion-list {
  display: grid;
  gap: 10px;
}

.suggestion-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.suggestion-header h4 {
  margin: 0;
  color: var(--color-heading);
}

.suggestion-meta {
  margin: 6px 0 0;
  color: var(--vt-c-text-light-2);
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.86rem;
}

.badge {
  border-radius: 999px;
  padding: 2px 8px;
  border: 1px solid currentColor;
  text-transform: uppercase;
  font-size: 0.72rem;
}

.badge-supported {
  color: #059669;
}

.badge-weak {
  color: #d97706;
}

.badge-conflict,
.badge-rejected {
  color: #dc2626;
}

.reason {
  margin: 8px 0;
  color: var(--color-text);
}

.breakdown-list {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text);
  display: grid;
  gap: 6px;
}

@media (max-width: 900px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .suggestion-header {
    flex-direction: column;
  }
}
</style>
