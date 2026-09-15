<template>
  <section class="robustness-panel">
    <header class="panel-header">
      <div><h3>Evidence and sensitivity</h3><p>Inspect the checks and assumptions before interpreting any summary.</p></div>
      <div class="actions">
        <button type="button" :disabled="running" @click="$emit('run')">{{ running ? 'Running checks…' : 'Run checks' }}</button>
        <button type="button" :disabled="!result || running" @click="$emit('export-json')">Export JSON</button>
        <button type="button" :disabled="!result || running" @click="$emit('export-csv')">Export CSV</button>
      </div>
    </header>
    <p>Results belong to recorded runs. Re-run after changing the data, graph, treatment or outcome.</p>
    <p v-if="running" role="status">Comparing estimators and checking sensitivity. Do not interpret previous results as belonging to this run.</p>
    <template v-if="result && !running">
      <p class="notice">Identification depends on the proposed graph. Stable estimates and passed checks do not prove causation or exclude unmeasured confounding.</p>
      <div class="summary-grid">
        <article><h4>Baseline method</h4><p>{{ result.baseline_method || 'Not available' }}</p></article>
        <article><h4>Baseline estimate</h4><p>{{ metric(result.baseline_estimate) }}</p><small>Check treatment contrast, outcome encoding and units.</small></article>
      </div>
      <article v-if="result.diagnostics?.length">
        <h4>Assumptions and warnings</h4>
        <ul><li v-for="item in result.diagnostics" :key="item.label"><strong>{{ item.label }}:</strong> {{ item.value }} — {{ item.details }}</li></ul>
      </article>
      <div class="content-grid">
        <article><h4>Estimator comparison</h4>
          <p v-if="!result.estimator_comparison?.length">No estimator comparison recorded.</p>
          <ul><li v-for="item in result.estimator_comparison || []" :key="item.method_name"><strong>{{ item.method_name }}</strong>: {{ item.error ? 'Unavailable: ' + item.error : metric(item.estimated_effect) }}</li></ul>
          <p>Agreement can still reflect shared bias. An error or unsupported method is not a passed check.</p>
        </article>
        <article><h4>Individual refutations</h4>
          <p v-if="!Object.keys(result.refutations || {}).length">No refutations recorded.</p>
          <ul><li v-for="(value, key) in result.refutations || {}" :key="key"><strong>{{ key.replaceAll('_', ' ') }}</strong>: {{ evidenceStatus(value) }}
            <span v-if="finite(value.delta) !== null"> · change {{ metric(value.delta) }}</span>
            <details><summary>Check details</summary><pre>{{ JSON.stringify(value, null, 2) }}</pre></details>
          </li></ul>
        </article>
      </div>
      <article>
        <h4>Unmeasured-confounder sensitivity</h4>
        <p>These are hypothetical perturbations under the sensitivity model, not measured hidden confounders or confidence intervals.</p>
        <svg v-if="geometry" viewBox="0 0 620 265" role="img" aria-labelledby="sensitivity-plot-title" class="sweep">
          <title id="sensitivity-plot-title">Adjusted effect across hypothesised confounder strengths. Exact values are available in the table below.</title>
          <line x1="65" y1="45" x2="65" y2="210" stroke="currentColor" />
          <line x1="65" y1="210" x2="555" y2="210" stroke="currentColor" />
          <line x1="65" :y1="geometry.zero" x2="555" :y2="geometry.zero" stroke="currentColor" stroke-dasharray="5 5" />
          <polyline :points="geometry.points" fill="none" stroke="currentColor" stroke-width="3" />
          <text x="58" y="42" text-anchor="end">{{ metric(geometry.ymax) }}</text>
          <text x="58" y="215" text-anchor="end">{{ metric(geometry.ymin) }}</text>
          <text x="65" y="231">{{ metric(geometry.xmin) }}</text><text x="555" y="231" text-anchor="end">{{ metric(geometry.xmax) }}</text>
          <text x="310" y="255" text-anchor="middle">Hypothesised confounder strength</text>
          <text x="70" y="22">Adjusted effect (original estimate units)</text>
        </svg>
        <p v-else>No usable sensitivity curve was returned. This is not evidence of robustness.</p>
        <details v-if="result.sensitivity_points?.length"><summary>Exact sensitivity values</summary>
          <div class="table-wrap"><table><caption>Hypothesised strength and adjusted effect</caption><thead><tr><th scope="col">Strength</th><th scope="col">Adjusted effect</th></tr></thead><tbody><tr v-for="(point, index) in result.sensitivity_points" :key="index"><td>{{ metric(point.confounder_strength) }}</td><td>{{ metric(point.adjusted_effect) }}</td></tr></tbody></table></div>
        </details>
        <details v-for="(value, key) in result.sensitivity || {}" :key="key"><summary>{{ key.replaceAll('_', ' ') }} — {{ evidenceStatus(value) }}</summary><pre>{{ JSON.stringify(value, null, 2) }}</pre></details>
      </article>
      <article><h4>Competing causal models</h4>
        <p v-if="!comparison">No competing-model comparison supplied. Run “Compare alternative DAGs” in the guide or use the Causality Agent.</p>
        <template v-else-if="matchedComparison">
          <p>{{ comparison.stability?.summary || 'Inspect each result and its assumptions.' }}</p>
          <div class="table-wrap"><table><caption>Models compared for this recorded analysis</caption>
            <thead><tr><th scope="col">Model</th><th scope="col">Estimate</th></tr></thead>
            <tbody><tr v-for="model in comparison.models || []" :key="model.key"><td>{{ model.name || model.key }}</td><td>{{ metric(model.estimated_effect) }}</td></tr></tbody>
          </table></div>
          <p>Alternative graphs probe selected assumptions; they do not cover every plausible causal structure.</p>
          <details><summary>Model assumptions and full comparison details</summary><pre>{{ JSON.stringify(comparison, null, 2) }}</pre></details>
        </template>
        <p v-else>The available model comparison belongs to another run or lacks provenance. Run it again with the same data, graph, query and seed before comparing these values.</p>
      </article>
      <details class="secondary-score">
        <summary>Optional composite diagnostic summary</summary>
        <p><strong>{{ scoreLabel }}</strong></p>
        <p>A heuristic aggregation of the checks implemented in this version. It is not a confidence level, probability of causal correctness, pass/fail decision or certification.</p>
      </details>
    </template>
    <p v-else-if="!running">No diagnostic results yet.</p>
  </section>
</template>
<script setup>
import { computed } from "vue"
import { evidenceStatus, finite, metric, sweepGeometry } from "../p0/contracts.mjs"
const props = defineProps({ result: { type: Object, default: null }, running: Boolean,
  comparison: { type: Object, default: null } })
defineEmits(["run", "export-json", "export-csv"])
const matchedComparison = computed(() => Boolean(props.result?.p0_analysis_key) && props.result.p0_analysis_key === props.comparison?.p0_analysis_key)
const geometry = computed(() => sweepGeometry(props.result?.sensitivity_points || []))
const scoreLabel = computed(() => {
  const score = finite(props.result?.robustness_score)
  return score === null ? "Not available" : `Composite diagnostic: ${Math.round(score * 100)} / 100`
})
</script>
<style scoped>
.robustness-panel{border:1px solid var(--color-border,#ccd3dd);border-radius:8px;background:var(--color-background,#fff);padding:14px;display:grid;gap:14px}
.panel-header,.actions{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px}.panel-header h3{margin:0}.panel-header p{margin:.4rem 0}.actions{justify-content:flex-start;align-items:start}
button{min-height:40px;padding:8px 12px;border:1px solid var(--color-border,#ccd3dd);border-radius:6px;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}
.summary-grid,.content-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}article{border:1px solid var(--color-border,#ccd3dd);border-radius:8px;padding:12px;min-width:0}h4{margin:0 0 8px}li{margin-bottom:.6rem}.notice{border-left:3px solid currentColor;padding-left:.8rem}.sweep{display:block;width:100%;height:auto;max-height:350px}svg text{font-size:12px;fill:currentColor}pre{overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;font-size:.83rem}summary{cursor:pointer;padding:6px 0}.secondary-score{font-size:.85rem;opacity:.85}.table-wrap{overflow:auto}td,th{text-align:left;padding:6px 16px 6px 0}
@media(max-width:800px){.summary-grid,.content-grid{grid-template-columns:1fr}}
</style>
