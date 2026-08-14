<template>
  <section v-if="result" class="assessment-panel">
    <div class="assessment-header">
      <div>
        <h3 class="assessment-title">Identification & Admissibility</h3>
        <p class="assessment-subtitle">Query-level diagnostics for the current treatment, outcome, and graph.</p>
      </div>
      <span :class="['assessment-badge', `assessment-badge-${result.badge || 'caution'}`]">{{ result.badge || 'caution' }}</span>
    </div>

    <div class="assessment-grid top-grid">
      <article class="assessment-card">
        <h4>Query</h4>
        <p><strong>Estimand:</strong> {{ result.selected_estimand || 'ATE' }}</p>
        <p><strong>Method:</strong> {{ result.suggested_method || 'n/a' }}</p>
        <p><strong>Sample size:</strong> {{ result.sample_size || 0 }}</p>
      </article>
      <article class="assessment-card">
        <h4>Variation</h4>
        <p><strong>Treatment:</strong> {{ formatMetric(result.treatment_variation) }}</p>
        <p><strong>Outcome:</strong> {{ formatMetric(result.outcome_variation) }}</p>
        <p><strong>DAG valid:</strong> {{ result.dag_valid ? 'yes' : 'no' }}</p>
      </article>
      <article class="assessment-card">
        <h4>Overlap</h4>
        <p><strong>Status:</strong> {{ result.overlap_ok ? 'ok' : 'warning' }}</p>
        <ul v-if="result.overlap_warnings?.length" class="compact-list">
          <li v-for="warning in result.overlap_warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-else>No overlap warnings.</p>
      </article>
    </div>

    <ul v-if="result.reasons?.length" class="assessment-reasons">
      <li v-for="reason in result.reasons" :key="reason">{{ reason }}</li>
    </ul>

    <div v-if="result.admissibility_checklist?.length" class="assessment-card">
      <h4>Checklist</h4>
      <ul class="checklist">
        <li v-for="item in result.admissibility_checklist" :key="item.label">
          <span :class="['check', `check-${item.status}`]">{{ item.status }}</span>
          <strong>{{ item.label }}</strong>
          <span> | {{ item.details }}</span>
        </li>
      </ul>
    </div>

    <div class="assessment-grid">
      <article class="assessment-card">
        <h4>Adjustment set</h4>
        <ul v-if="result.adjustment_set?.length" class="compact-list">
          <li v-for="item in result.adjustment_set" :key="`adj-${item}`">{{ item }}</li>
        </ul>
        <p v-else>None</p>
      </article>
      <article class="assessment-card">
        <h4>Minimal sets</h4>
        <ul v-if="result.minimal_adjustment_sets?.length" class="compact-list">
          <li v-for="(item, index) in result.minimal_adjustment_sets" :key="`min-${index}`">{{ item.join(', ') || 'None' }}</li>
        </ul>
        <p v-else>None</p>
      </article>
      <article class="assessment-card">
        <h4>IV / frontdoor</h4>
        <p><strong>IV candidates:</strong> {{ joinList(result.iv_candidates) }}</p>
        <p><strong>Frontdoor:</strong> {{ joinList(result.frontdoor_variables) }}</p>
      </article>
    </div>

    <div class="assessment-grid">
      <article class="assessment-card">
        <h4>Open backdoor paths</h4>
        <ul v-if="result.open_backdoor_paths?.length" class="compact-list">
          <li v-for="item in result.open_backdoor_paths" :key="item">{{ item }}</li>
        </ul>
        <p v-else>None detected</p>
      </article>
      <article class="assessment-card">
        <h4>Blocked paths</h4>
        <ul v-if="result.blocked_paths?.length" class="compact-list">
          <li v-for="item in result.blocked_paths" :key="item">{{ item }}</li>
        </ul>
        <p v-else>None recorded</p>
      </article>
      <article class="assessment-card">
        <h4>Graph issues</h4>
        <ul v-if="result.graph_issues?.length" class="compact-list">
          <li v-for="item in result.graph_issues" :key="item">{{ item }}</li>
        </ul>
        <p v-else>No graph issues detected</p>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({
  result: {
    type: Object,
    default: null,
  },
})

function formatMetric(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return parsed.toFixed(4)
}

function joinList(values) {
  return Array.isArray(values) && values.length ? values.join(", ") : "None"
}
</script>

<style scoped>
.assessment-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-background);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.assessment-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.assessment-title {
  margin: 0;
  color: var(--color-heading);
}

.assessment-subtitle {
  margin: 4px 0 0;
  color: var(--vt-c-text-light-2);
  font-size: 0.9rem;
}

.assessment-badge {
  border-radius: 999px;
  border: 1px solid var(--color-border);
  padding: 4px 10px;
  font-size: 0.76rem;
  text-transform: uppercase;
}

.assessment-badge-trust {
  color: #059669;
  border-color: #059669;
}

.assessment-badge-caution {
  color: #d97706;
  border-color: #d97706;
}

.assessment-badge-reject {
  color: #dc2626;
  border-color: #dc2626;
}

.assessment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.assessment-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.assessment-card h4 {
  margin: 0 0 8px;
  color: var(--color-heading);
}

.assessment-card p {
  margin: 0 0 6px;
}

.assessment-reasons,
.compact-list,
.checklist {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}

.check {
  display: inline-block;
  min-width: 42px;
  text-transform: uppercase;
  font-size: 0.72rem;
}

.check-pass {
  color: #059669;
}

.check-warn {
  color: #d97706;
}

.check-fail {
  color: #dc2626;
}

@media (max-width: 900px) {
  .assessment-grid {
    grid-template-columns: 1fr;
  }
}
</style>
