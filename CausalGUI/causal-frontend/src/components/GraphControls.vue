<template>
  <div class="controls-panel">
    <h3>🎛️ Controls</h3>

    <label class="control-label">
      Treatment:
      <select :value="selectedTreatment" class="control-select" @change="onTreatmentChange">
        <option disabled value="">-- Select treatment --</option>
        <option v-for="item in variables" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </label>

    <label class="control-label">
      Outcome:
      <select :value="selectedOutcome" class="control-select" @change="onOutcomeChange">
        <option disabled value="">-- Select outcome --</option>
        <option v-for="item in variables" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </label>

    <label class="control-label">
      Method:
      <select :value="selectedMethod" class="control-select" @change="onMethodChange">
        <option disabled value="">--Select--</option>
        <option value="backdoor.linear_regression">Backdoor: Linear Regression</option>
        <option value="backdoor.propensity_score_matching">Propensity Matching</option>
        <option value="iv.instrumental_variable">Instrumental Variable</option>
        <option value="frontdoor.two_stage_regression">2-Stage Regression</option>
      </select>
    </label>

    <div class="button-grid">
      <button class="btn btn-save" type="button" @click="$emit('save')">💾 Save Graph</button>
      <button class="btn btn-ai" type="button" @click="$emit('suggest')">✨ AI Draft + Verify</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('relayout')">🧭 Auto Layout</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('delete-selected')">🗑️ Delete Selected</button>
      <button class="btn btn-secondary" type="button" :disabled="!canUndo" @click="$emit('undo')">↶ Undo</button>
      <button class="btn btn-secondary" type="button" :disabled="!canRedo" @click="$emit('redo')">↷ Redo</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('zoom-in')">＋ Zoom In</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('zoom-out')">－ Zoom Out</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('fit')">⤢ Fit</button>
      <button class="btn btn-secondary" type="button" :disabled="!hasGraph" @click="$emit('center')">◎ Center</button>
      <button class="btn btn-run" type="button" @click="$emit('run')">🔍 Run Inference</button>
      <button class="btn btn-reset" type="button" @click="$emit('reset')">♻️ Reset</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  variables: {
    type: Array,
    default: () => [],
  },
  selectedTreatment: {
    type: [String, Number],
    default: "",
  },
  selectedOutcome: {
    type: [String, Number],
    default: "",
  },
  selectedMethod: {
    type: String,
    default: "",
  },
  hasGraph: {
    type: Boolean,
    default: false,
  },
  canUndo: {
    type: Boolean,
    default: false,
  },
  canRedo: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  "update:selectedTreatment",
  "update:selectedOutcome",
  "update:selectedMethod",
  "save",
  "suggest",
  "relayout",
  "delete-selected",
  "undo",
  "redo",
  "zoom-in",
  "zoom-out",
  "fit",
  "center",
  "run",
  "reset",
])

function normalizeId(value) {
  if (value === "") {
    return ""
  }
  const parsed = Number(value)
  return Number.isNaN(parsed) ? value : parsed
}

function onTreatmentChange(event) {
  emit("update:selectedTreatment", normalizeId(event.target.value))
}

function onOutcomeChange(event) {
  emit("update:selectedOutcome", normalizeId(event.target.value))
}

function onMethodChange(event) {
  emit("update:selectedMethod", event.target.value)
}
</script>

<style scoped>
.controls-panel {
  width: 100%;
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 14px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-self: flex-start;
  position: sticky;
  top: 0;
}

.controls-panel h3 {
  margin: 0;
  color: var(--color-heading);
  font-size: 1rem;
  font-weight: 600;
}

.control-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.9rem;
  color: var(--color-heading);
}

.control-select {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-background);
  color: var(--color-text);
  padding: 8px;
}

.btn {
  padding: 9px;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.button-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.btn-save {
  background: #3b82f6;
}

.btn-run {
  background: #10b981;
}

.btn-ai {
  background: #7c3aed;
}

.btn-reset {
  background: #6b7280;
}

.btn-secondary {
  background: #334155;
}

@media (max-width: 768px) {
  .controls-panel {
    position: static;
  }

  .button-grid {
    grid-template-columns: 1fr;
  }
}
</style>
