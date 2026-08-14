<template>
  <section class="agent-panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">Causality Agent</h3>
        <p class="panel-subtitle">
          Optional assistant: profile the dataset, review a cleaning plan, and get a suggested causal model.
          Every stage waits for your approval.
        </p>
      </div>
      <div class="panel-actions">
        <button
          class="panel-action primary"
          type="button"
          :disabled="!graphId || busy"
          @click="$emit('run-profile')"
        >
          {{ profile ? "Re-run profile" : "1. Profile data" }}
        </button>
        <button
          v-if="hasAnyResult"
          class="panel-action ghost"
          type="button"
          :disabled="busy"
          @click="$emit('clear')"
        >
          Clear
        </button>
      </div>
    </div>

    <p v-if="!graphId" class="agent-hint">Upload a dataset to enable the agent.</p>
    <p v-else-if="busy" class="agent-hint">{{ busyLabel }}</p>

    <template v-if="profile">
      <div class="summary-grid">
        <article class="summary-card">
          <span class="summary-label">Rows</span>
          <strong>{{ profile.row_count }}</strong>
        </article>
        <article class="summary-card">
          <span class="summary-label">Columns</span>
          <strong>{{ profile.column_count }}</strong>
        </article>
        <article class="summary-card">
          <span class="summary-label">Duplicate rows</span>
          <strong>{{ profile.duplicate_row_count || 0 }}</strong>
        </article>
        <article class="summary-card">
          <span class="summary-label">Dataset</span>
          <strong>{{ profile.dataset_source === "cleaned" ? "cleaned copy" : "raw upload" }}</strong>
        </article>
      </div>

      <details class="agent-details" open>
        <summary>Data issues ({{ (profile.issues || []).length }})</summary>
        <ul v-if="profile.issues?.length" class="issue-list">
          <li v-for="(issue, index) in profile.issues" :key="`issue-${index}`">
            <span :class="['badge', issue.severity === 'warning' ? 'badge-warning' : 'badge-info']">
              {{ issue.severity }}
            </span>
            <span>{{ issue.description }}</span>
          </li>
        </ul>
        <p v-else class="agent-hint">No issues detected.</p>
      </details>

      <details class="agent-details">
        <summary>Column profile ({{ (profile.columns || []).length }})</summary>
        <div class="table-wrap">
          <table class="profile-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th>Missing</th>
                <th>Unique</th>
                <th>Range</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="column in profile.columns" :key="`col-${column.name}`">
                <td>{{ column.name }}</td>
                <td>{{ column.inferred_type }}</td>
                <td>{{ formatPercent(column.missing_ratio) }}</td>
                <td>{{ column.unique_count }}</td>
                <td>
                  <template v-if="column.min !== undefined">{{ formatNumber(column.min) }} .. {{ formatNumber(column.max) }}</template>
                  <template v-else>--</template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <div class="stage-row">
        <button
          class="panel-action primary"
          type="button"
          :disabled="busy"
          @click="$emit('suggest-cleaning')"
        >
          2. Suggest cleaning plan
        </button>
      </div>
    </template>

    <template v-if="cleaningPlan">
      <div class="stage-block">
        <h4 class="stage-title">Cleaning plan</h4>
        <p v-if="!cleaningPlan.length" class="agent-hint">
          The agent found nothing to clean - the dataset looks ready for analysis.
        </p>
        <template v-else>
          <article
            v-for="step in cleaningPlan"
            :key="step.step_id"
            class="step-card"
          >
            <label class="step-label">
              <input
                type="checkbox"
                :checked="selectedStepIds.has(step.step_id)"
                @change="toggleStep(step.step_id)"
              />
              <span class="step-name">{{ describeStep(step) }}</span>
              <span :class="['badge', step.severity === 'warning' ? 'badge-warning' : 'badge-info']">
                {{ step.severity }}
              </span>
              <span v-if="step.default_action === 'accept'" class="badge badge-accept">recommended</span>
            </label>
            <p class="step-rationale">{{ step.rationale }}</p>
          </article>
          <div class="stage-row">
            <button
              class="panel-action primary"
              type="button"
              :disabled="busy || !selectedSteps.length"
              @click="$emit('apply-cleaning', selectedSteps)"
            >
              Apply {{ selectedSteps.length }} selected step(s)
            </button>
            <span class="agent-hint">Applying writes a cleaned copy; the raw upload is kept unchanged.</span>
          </div>
        </template>
      </div>
    </template>

    <template v-if="cleaningResult">
      <div class="stage-block">
        <h4 class="stage-title">Cleaning applied</h4>
        <p class="agent-hint">
          Rows: {{ cleaningResult.row_count_before }} -> {{ cleaningResult.row_count_after }} |
          Columns: {{ cleaningResult.column_count_before }} -> {{ cleaningResult.column_count_after }}
          <template v-if="cleaningResult.dropped_columns?.length">
            | Dropped: {{ cleaningResult.dropped_columns.join(", ") }}
          </template>
        </p>
        <ul class="issue-list">
          <li v-for="step in cleaningResult.applied_steps" :key="`applied-${step.step_id}`">
            {{ step.detail }}
          </li>
        </ul>
      </div>
    </template>

    <template v-if="profile">
      <div class="stage-row">
        <button
          class="panel-action primary"
          type="button"
          :disabled="busy"
          @click="$emit('suggest-model')"
        >
          3. Suggest causal model
        </button>
      </div>
    </template>

    <template v-if="modelSuggestion">
      <div class="stage-block">
        <h4 class="stage-title">Suggested causal model</h4>
        <p class="agent-hint">
          {{ modelSuggestion.llm_used ? "Drafted by the LLM and statistically verified against the dataset." : "Drafted from statistical heuristics (no LLM key configured)." }}
        </p>

        <ul v-if="modelSuggestion.notes?.length" class="issue-list">
          <li v-for="(note, index) in modelSuggestion.notes" :key="`note-${index}`">{{ note }}</li>
        </ul>

        <div class="role-grid">
          <article class="assessment-card">
            <h5>Treatment candidates</h5>
            <ul class="candidate-list">
              <li v-for="item in modelSuggestion.treatment_candidates" :key="`t-${item.name}`">
                <strong>{{ item.name }}</strong>
                <span class="candidate-reason">{{ item.reason }}</span>
              </li>
              <li v-if="!modelSuggestion.treatment_candidates?.length" class="agent-hint">None found.</li>
            </ul>
          </article>
          <article class="assessment-card">
            <h5>Outcome candidates</h5>
            <ul class="candidate-list">
              <li v-for="item in modelSuggestion.outcome_candidates" :key="`o-${item.name}`">
                <strong>{{ item.name }}</strong>
                <span class="candidate-reason">{{ item.reason }}</span>
              </li>
              <li v-if="!modelSuggestion.outcome_candidates?.length" class="agent-hint">None found.</li>
            </ul>
          </article>
          <article class="assessment-card">
            <h5>Recommended estimator</h5>
            <p v-if="modelSuggestion.recommended_estimator?.method_name">
              <strong>{{ modelSuggestion.recommended_estimator.method_name }}</strong>
            </p>
            <p class="candidate-reason">{{ modelSuggestion.recommended_estimator?.rationale || "Pick treatment and outcome first." }}</p>
            <p v-if="modelSuggestion.identification" class="candidate-reason">
              Identifiability: {{ describeIdentification(modelSuggestion.identification) }}
            </p>
            <p v-if="methodOverride" class="candidate-reason override-note">
              Selected in Controls: <strong>{{ selectedMethod }}</strong> - your choice overrides
              this recommendation and will be used for estimation.
            </p>
            <p class="candidate-reason basis-note">
              {{ modelSuggestion.estimate_basis === "canvas"
                ? "Reflects the current canvas graph - updates automatically as you edit it."
                : "Based on the agent's proposed edges; edits on the canvas will update this automatically." }}
            </p>
          </article>
        </div>

        <div class="stage-row">
          <button
            class="panel-action primary"
            type="button"
            :disabled="busy || !modelSuggestion.edges?.length"
            @click="$emit('adopt-model')"
          >
            Review {{ modelSuggestion.edges?.length || 0 }} edge(s) in Copilot &amp; apply roles
          </button>
          <button
            class="panel-action primary"
            type="button"
            :disabled="busy"
            @click="$emit('run-estimation')"
          >
            4. Run estimation
          </button>
          <span class="agent-hint">The suggested model is already drawn on the canvas - modify it there. "Run estimation" uses the same pipeline as Controls' Run Inference, filling in the agent's roles/estimator where you have not chosen your own.</span>
        </div>
      </div>
    </template>

    <template v-if="estimation">
      <div
        :class="[
          'stage-block',
          'estimation-block',
          estimation.status === 'success' ? 'estimation-success' : 'estimation-blocked',
        ]"
      >
        <h4 class="stage-title">
          <span class="estimation-icon">{{ estimation.status === "success" ? "✓" : "⚠" }}</span>
          {{ estimation.status === "success" ? "Estimation complete" : "Analysis not possible" }}
        </h4>

        <template v-if="estimation.status === 'success'">
          <div class="estimation-grid">
            <article class="estimation-card">
              <p class="estimation-label">Estimated Effect</p>
              <p class="estimation-effect">{{ formatEffectValue(estimation.effect) }}</p>
            </article>
            <article class="estimation-card">
              <p class="estimation-label">Method</p>
              <p class="estimation-value">{{ methodLabel(estimation.method) }}</p>
            </article>
            <article class="estimation-card">
              <p class="estimation-label">Interpretation</p>
              <p class="estimation-value">{{ interpretEffect(estimation.effect) }}</p>
            </article>
          </div>
          <p class="estimation-line">
            Causal effect of <strong>{{ estimation.treatmentName }}</strong> on
            <strong>{{ estimation.outcomeName }}</strong>.
          </p>
          <p v-if="estimation.warning" class="estimation-warning">{{ estimation.warning }}</p>
          <p class="agent-hint">
            The full result (identification summary with all estimands, graph image, raw payload)
            is in the Inference Result panel below - identical to a run without the agent. Use the
            Robustness Dashboard to pressure-test this number before acting on it.
          </p>
        </template>

        <template v-else>
          <p class="estimation-line">{{ estimation.reason }}</p>
          <ul v-if="estimation.hints?.length" class="issue-list">
            <li v-for="(hint, index) in estimation.hints" :key="`hint-${index}`">{{ hint }}</li>
          </ul>
        </template>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue"

import { formatEffectValue, interpretEffect, methodLabel } from "../composables/useInferenceFormatting"

const props = defineProps({
  graphId: {
    type: [String, Number, null],
    default: null,
  },
  profile: {
    type: Object,
    default: null,
  },
  cleaningPlan: {
    type: Array,
    default: null,
  },
  cleaningResult: {
    type: Object,
    default: null,
  },
  modelSuggestion: {
    type: Object,
    default: null,
  },
  selectedMethod: {
    type: String,
    default: "",
  },
  estimation: {
    type: Object,
    default: null,
  },
  busy: {
    type: Boolean,
    default: false,
  },
  busyLabel: {
    type: String,
    default: "The agent is working...",
  },
})

defineEmits([
  "run-profile",
  "suggest-cleaning",
  "apply-cleaning",
  "suggest-model",
  "adopt-model",
  "run-estimation",
  "clear",
])

const selectedStepIds = ref(new Set())

watch(
  () => props.cleaningPlan,
  (steps) => {
    const next = new Set()
    for (const step of steps || []) {
      if (step.default_action === "accept") {
        next.add(step.step_id)
      }
    }
    selectedStepIds.value = next
  },
  { immediate: true },
)

const selectedSteps = computed(() =>
  (props.cleaningPlan || []).filter((step) => selectedStepIds.value.has(step.step_id)),
)

const hasAnyResult = computed(() =>
  Boolean(props.profile || props.cleaningPlan || props.cleaningResult || props.modelSuggestion),
)

const methodOverride = computed(
  () =>
    Boolean(props.selectedMethod) &&
    props.selectedMethod !== props.modelSuggestion?.recommended_estimator?.method_name,
)

function toggleStep(stepId) {
  const next = new Set(selectedStepIds.value)
  if (next.has(stepId)) {
    next.delete(stepId)
  } else {
    next.add(stepId)
  }
  selectedStepIds.value = next
}

const STEP_LABELS = {
  drop_column: "Drop column",
  drop_duplicate_rows: "Drop duplicate rows",
  coerce_numeric: "Convert to numeric",
  normalize_datetime: "Normalize datetime",
  cap_outliers: "Cap outliers",
  impute_missing: "Impute missing values",
}

function describeStep(step) {
  const label = STEP_LABELS[step.step_type] || step.step_type
  return step.column ? `${label}: ${step.column}` : label
}

function describeIdentification(identification) {
  if (!identification.checked) {
    return identification.note || "not checked"
  }
  if (!identification.identifiable) {
    return identification.note || "not identifiable"
  }
  const adjustment = identification.adjustment_set?.length
    ? `adjust for ${identification.adjustment_set.join(", ")}`
    : "no adjustment needed"
  return `identifiable (${adjustment})`
}

function formatPercent(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return `${Math.round(parsed * 100)}%`
}

function formatNumber(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "n/a"
  }
  return Math.abs(parsed) >= 1000 ? parsed.toFixed(0) : parsed.toFixed(2)
}

</script>

<style scoped>
.agent-panel {
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

.panel-actions,
.stage-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.panel-action {
  border: 1px solid var(--color-border);
  background: white;
  border-radius: 999px;
  padding: 8px 12px;
  cursor: pointer;
}

.panel-action.primary {
  background: #7c3aed;
  border-color: #7c3aed;
  color: white;
}

.panel-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.panel-action.ghost {
  background: transparent;
}

.agent-hint {
  margin: 0;
  color: var(--vt-c-text-light-2);
  font-size: 0.86rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.summary-card,
.assessment-card,
.step-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.summary-label {
  display: block;
  color: var(--vt-c-text-light-2);
  font-size: 0.82rem;
}

.agent-details summary {
  cursor: pointer;
  color: var(--color-heading);
  font-weight: 600;
  font-size: 0.92rem;
}

.issue-list {
  margin: 8px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: var(--color-text);
  font-size: 0.9rem;
}

.badge {
  border-radius: 999px;
  padding: 2px 8px;
  border: 1px solid currentColor;
  text-transform: uppercase;
  font-size: 0.7rem;
  margin-right: 6px;
}

.badge-warning {
  color: #d97706;
}

.badge-info {
  color: #2563eb;
}

.badge-accept {
  color: #059669;
}

.table-wrap {
  margin-top: 8px;
  overflow-x: auto;
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: 6px;
}

.profile-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
}

.profile-table th,
.profile-table td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.profile-table th {
  position: sticky;
  top: 0;
  background: var(--color-background);
}

.stage-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stage-title {
  margin: 0;
  color: var(--color-heading);
  font-size: 0.95rem;
}

.step-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-label {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  cursor: pointer;
}

.step-name {
  font-weight: 600;
  color: var(--color-heading);
}

.step-rationale {
  margin: 0 0 0 24px;
  color: var(--vt-c-text-light-2);
  font-size: 0.86rem;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.assessment-card h5 {
  margin: 0 0 8px;
  color: var(--color-heading);
}

.candidate-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}

.candidate-reason {
  display: block;
  color: var(--vt-c-text-light-2);
  font-size: 0.84rem;
}

.basis-note {
  font-style: italic;
}

.override-note {
  color: #7c3aed;
}

.estimation-block {
  border-radius: 8px;
  border: 2px solid;
  padding: 12px;
}

.estimation-success {
  border-color: #059669;
  background: #ecfdf5;
}

.estimation-blocked {
  border-color: #dc2626;
  background: #fef2f2;
}

.estimation-success .stage-title {
  color: #065f46;
}

.estimation-blocked .stage-title {
  color: #991b1b;
}

.estimation-icon {
  margin-right: 6px;
}

.estimation-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.estimation-card {
  border: 1px solid rgba(5, 150, 105, 0.35);
  border-radius: 8px;
  padding: 10px;
  background: white;
}

.estimation-label {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text);
  opacity: 0.8;
}

.estimation-value {
  margin: 4px 0 0;
  color: var(--color-heading);
  font-size: 0.95rem;
  font-weight: 500;
}

.estimation-effect {
  margin: 4px 0 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #065f46;
}

@media (max-width: 900px) {
  .estimation-grid {
    grid-template-columns: 1fr;
  }
}

.estimation-line {
  margin: 0;
  color: var(--color-text);
}

.estimation-warning {
  margin: 0;
  color: #b45309;
  font-size: 0.9rem;
}

@media (max-width: 900px) {
  .summary-grid,
  .role-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .summary-grid,
  .role-grid {
    grid-template-columns: 1fr;
  }
}
</style>
