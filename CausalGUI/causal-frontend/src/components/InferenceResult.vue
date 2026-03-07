<template>
  <section v-if="hasResult" class="inference-result">
    <header class="result-header">
      <h3>📊 Inference Result</h3>
      <span class="result-pill">Completed</span>
    </header>

    <div class="result-grid">
      <article class="result-card">
        <p class="result-label">Estimated Effect</p>
        <p class="result-value">{{ formattedEffect }}</p>
      </article>
      <article class="result-card">
        <p class="result-label">Method</p>
        <p class="result-value result-value-small">{{ methodLabel }}</p>
      </article>
      <article class="result-card">
        <p class="result-label">Interpretation</p>
        <p class="result-value result-value-small">{{ effectInterpretation }}</p>
      </article>
    </div>

    <div v-if="estimandSections.length" class="estimand-block">
      <h4>Identification Summary</h4>
      <div class="estimand-list">
        <article v-for="section in estimandSections" :key="section.id" class="estimand-item">
          <p class="estimand-title">Estimand {{ section.id }}</p>
          <p class="estimand-name">{{ section.name }}</p>
          <p class="estimand-text">{{ section.summary }}</p>
        </article>
      </div>
    </div>

    <div v-if="causalGraphImageUrl" class="graph-wrap">
      <h4>📈 Causal Graph</h4>
      <img :src="causalGraphImageUrl" alt="Causal Graph" class="graph-image" />
    </div>

    <details v-if="inferenceResponse" class="payload-details">
      <summary>Backend response payload</summary>
      <pre>{{ formattedResponse }}</pre>
    </details>
  </section>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  inferenceResult: {
    type: [String, Number, null],
    default: null,
  },
  causalGraphImageUrl: {
    type: String,
    default: "",
  },
  inferenceResponse: {
    type: Object,
    default: null,
  },
})

const hasResult = computed(() => props.inferenceResponse !== null || props.inferenceResult !== null)

const effectValue = computed(() => {
  const value = props.inferenceResponse?.estimated_effect ?? props.inferenceResult
  if (value === null || value === undefined) {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
})

const formattedEffect = computed(() => {
  if (effectValue.value === null) {
    return "N/A"
  }
  return effectValue.value.toFixed(4)
})

const methodLabel = computed(() => {
  const method = props.inferenceResponse?.method_name
  if (!method) {
    return "Not specified"
  }

  const labels = {
    "backdoor.linear_regression": "Backdoor · Linear Regression",
    "backdoor.propensity_score_matching": "Backdoor · Propensity Score Matching",
    "backdoor.propensity_score_weighting": "Backdoor · Propensity Score Weighting",
    "backdoor.doubly_robust_estimator": "Backdoor · Doubly Robust",
    "iv.instrumental_variable": "Instrumental Variable",
    "frontdoor.two_stage_regression": "Frontdoor · Two-Stage Regression",
    "backdoor.diff_in_means_fallback": "Fallback · Difference in Means",
  }

  return labels[method] || method
})

const effectInterpretation = computed(() => {
  if (effectValue.value === null) {
    return "No estimate was returned."
  }

  const absValue = Math.abs(effectValue.value)
  if (absValue < 0.001) {
    return "Very small estimated effect."
  }
  if (effectValue.value > 0) {
    return "Increasing treatment is associated with higher outcome."
  }
  return "Increasing treatment is associated with lower outcome."
})

const estimandSections = computed(() => {
  const raw = props.inferenceResponse?.estimand_string
  if (!raw || typeof raw !== "string") {
    return []
  }

  const chunks = raw
    .split("### Estimand :")
    .map((chunk) => chunk.trim())
    .filter(Boolean)

  return chunks.map((chunk) => {
    const lines = chunk
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)

    const id = lines[0] || "?"
    const nameLine = lines.find((line) => line.toLowerCase().startsWith("estimand name:"))
    const expressionLine = lines.find((line) => line.toLowerCase().startsWith("estimand expression:"))
    const noVariableLine = lines.find((line) => line.toLowerCase().includes("no such variable"))

    const name = nameLine ? nameLine.replace(/^Estimand name:\s*/i, "") : "Unknown"
    let summary = ""
    if (noVariableLine) {
      summary = "No valid variable set found for this strategy."
    } else if (expressionLine) {
      summary = expressionLine.replace(/^Estimand expression:\s*/i, "Expression available.")
    } else {
      summary = lines.slice(1, 4).join(" ") || "Details available in payload."
    }

    return {
      id,
      name,
      summary,
    }
  })
})

const formattedResponse = computed(() => JSON.stringify(props.inferenceResponse ?? {}, null, 2))
</script>

<style scoped>
.inference-result {
  background: var(--color-background);
  border: 1px solid var(--color-border);
  padding: 16px;
  border-radius: 8px;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.result-header h3 {
  margin: 0;
  color: var(--color-heading);
}

.result-pill {
  border-radius: 999px;
  border: 1px solid var(--color-border);
  padding: 2px 10px;
  font-size: 0.78rem;
  color: var(--color-text);
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.result-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
}

.result-label {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text);
  opacity: 0.8;
}

.result-value {
  margin: 4px 0 0;
  color: var(--color-heading);
  font-size: 1.1rem;
  font-weight: 600;
}

.result-value-small {
  font-size: 0.95rem;
  font-weight: 500;
}

.estimand-block {
  margin-bottom: 14px;
}

.estimand-block h4,
.graph-wrap h4 {
  margin: 0 0 8px;
  color: var(--color-heading);
}

.estimand-list {
  display: grid;
  gap: 8px;
}

.estimand-item {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 8px;
}

.estimand-title {
  margin: 0;
  font-size: 0.78rem;
  opacity: 0.8;
}

.estimand-name {
  margin: 4px 0 2px;
  font-weight: 600;
  color: var(--color-heading);
}

.estimand-text {
  margin: 0;
  font-size: 0.86rem;
  color: var(--color-text);
}

.graph-wrap {
  margin-bottom: 10px;
}

.payload-details {
  margin-top: 8px;
}

.payload-details summary {
  cursor: pointer;
  color: var(--color-heading);
}

.payload-details pre {
  margin: 8px 0 0;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-background);
  color: var(--color-text);
  overflow: auto;
  font-size: 0.78rem;
}

.graph-image {
  max-width: 100%;
  border-radius: 6px;
  border: 1px solid var(--color-border);
}

@media (max-width: 900px) {
  .result-grid {
    grid-template-columns: 1fr;
  }
}
</style>
