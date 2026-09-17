<template>
  <details class="analysis-panel">
    <summary>Reviewed comparison</summary>
    <p>Explicit treatment comparisons, encoding, uncertainty and group comparability for independent observations. These settings apply only to “Run reviewed comparison”, not the legacy controls.</p>
    <div class="actions">
      <button type="button" :disabled="busy" @click="loadSynthetic('randomized')">Load synthetic campaign</button>
      <button type="button" :disabled="busy" @click="loadSynthetic('poor-overlap')">Load overlap stress test</button>
      <button type="button" :disabled="busy || !graphId" @click="refreshSchema">Review current data and graph</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="!graphId">Load a sample or CSV above. No account or external AI call is needed.</p>
    <template v-if="schema">
      <p><strong>Selected variables:</strong> {{ treatmentName || 'Select treatment in Controls' }} → {{ outcomeName || 'Select outcome in Controls' }}. Data source: {{ schema.effective_data }}.</p>
      <fieldset :disabled="busy">
        <legend>Define the comparison</legend>
        <div class="fields">
          <label>Analysis name <input v-model="form.name" maxlength="160" /></label>
          <label>Treatment type <select v-model="form.treatment_kind"><option value="categorical">Two selected categories</option><option value="continuous">Continuous — two fixed doses</option></select></label>
          <label>Control value
            <select v-if="form.treatment_kind === 'categorical'" v-model="form.control_value"><option value="" disabled>Select</option><option v-for="level in treatmentColumn?.levels || []" :key="level" :value="level">{{ level }}</option></select>
            <input v-else v-model.number="form.control_value" type="number" step="any" />
          </label>
          <label>Treatment value
            <select v-if="form.treatment_kind === 'categorical'" v-model="form.treatment_value"><option value="" disabled>Select</option><option v-for="level in treatmentColumn?.levels || []" :key="level" :value="level">{{ level }}</option></select>
            <input v-else v-model.number="form.treatment_value" type="number" step="any" />
          </label>
          <label>Outcome type <select v-model="form.outcome_kind"><option value="continuous">Continuous numeric</option><option value="binary">Binary event</option></select></label>
          <label v-if="form.outcome_kind === 'binary'">Event coded as 1 <select v-model="form.event_value"><option value="" disabled>Select event</option><option v-for="level in outcomeColumn?.levels || []" :key="level" :value="level">{{ level }}</option></select></label>
          <label v-else>Outcome units <input v-model="form.units" maxlength="160" /></label>
          <label>Target population <select v-model="form.estimand"><option value="ATE">ATE — eligible analysis sample</option><option value="ATT" :disabled="form.treatment_kind === 'continuous'">ATT — treated group</option><option value="ATC" :disabled="form.treatment_kind === 'continuous'">ATC — control group</option></select></label>
          <label>Method <select v-model="form.method"><option v-for="[value, label] in methods" :key="value" :value="value">{{ label }}</option></select></label>
          <label>Missing values <select v-model="form.missing"><option value="error">Stop for review</option><option value="complete_case">Explicitly exclude incomplete observations</option></select></label>
          <label>Uncertainty <select v-model="form.uncertainty"><option value="auto">Calculate where supported</option><option value="none">Do not calculate</option></select></label>
          <label>Confidence level <select v-model.number="form.confidence"><option :value="0.9">90%</option><option :value="0.95">95%</option><option :value="0.99">99%</option></select></label>
          <label v-if="form.method === 'propensity_score_weighting'">Full-refit bootstrap repetitions <input v-model.number="form.bootstrap_reps" type="number" min="50" max="500" step="1" /></label>
        </div>
        <p>Uses the workspace analysis seed. Other categorical treatment levels are excluded and reported. Continuous treatment supports ATE between two fixed doses only.</p>
      </fieldset>
      <fieldset :disabled="busy">
        <legend>Review adjustment and encoding</legend>
        <p>{{ schema.warning }}</p>
        <div class="table-wrap"><table>
          <caption>Original variables remain DAG nodes; nominal predictors are one-hot encoded internally.</caption>
          <thead><tr><th scope="col">Adjust</th><th scope="col">Variable</th><th scope="col">Encoding</th><th scope="col">Reference</th><th scope="col">Treatment interaction</th></tr></thead>
          <tbody><tr v-for="cov in form.covariates" :key="cov.name">
            <td><input v-model="cov.enabled" type="checkbox" :aria-label="`Adjust for ${cov.name}`" /></td><th scope="row">{{ cov.name }}</th>
            <td><select v-model="cov.kind" :aria-label="`Encoding for ${cov.name}`"><option value="numeric">Numeric</option><option value="nominal">Nominal / one-hot</option></select></td>
            <td><select v-if="cov.kind === 'nominal'" v-model="cov.reference" :aria-label="`Reference for ${cov.name}`"><option v-for="level in cov.levels" :key="level" :value="level">{{ level }}</option></select><span v-else>Not applicable</span></td>
            <td><input v-model="cov.interaction" type="checkbox" :disabled="!cov.enabled || !['linear_regression','logistic_regression'].includes(form.method)" :aria-label="`Treatment interaction with ${cov.name}`" /></td>
          </tr></tbody>
        </table></div>
        <p>Numeric category codes are not automatically recognized as nominal. Check the event definition, references and measurement timing. Treatment descendants cannot be adjusted for in this total-effect path.</p>
      </fieldset>
      <fieldset :disabled="busy">
        <legend>Confirm before estimation</legend>
        <label><input v-model="independent" type="checkbox" /> Rows represent independent observations; repeated customer/country rows are not treated as independent.</label>
        <label><input v-model="reviewed" type="checkbox" /> I reviewed the saved graph, treatment comparison, outcome event, encoding, missing-data policy and causal assumptions.</label>
        <button type="button" :disabled="busy || !reviewed || !independent || !treatmentName || !outcomeName" @click="run">Run reviewed comparison</button>
      </fieldset>
    </template>
    <article v-if="result" aria-live="polite">
      <h3>Recorded comparison: {{ result.specification.name }}</h3>
      <p v-if="stale" class="notice">Settings or the canvas changed. This is a historical result, not an estimate for the current workspace.</p>
      <p><strong>{{ result.analysis_kind === 'descriptive' ? 'Descriptive difference — not causal' : 'Estimate conditional on the graph' }}:</strong> {{ numberText(result.estimated_effect) }} {{ result.units }}<span v-if="result.percentage_points !== null"> ({{ numberText(result.percentage_points) }} percentage points)</span>.</p>
      <p>{{ result.method_label }} · {{ result.target_population }} · {{ result.sample.analysis }} observations, target {{ result.sample.target }}.</p>
      <p v-if="result.confidence_interval.status === 'available'">{{ Math.round(result.confidence_interval.level * 100) }}% interval: [{{ numberText(result.confidence_interval.lower) }}, {{ numberText(result.confidence_interval.upper) }}]. {{ result.confidence_interval.method }}.</p>
      <p v-else>Uncertainty unavailable: {{ result.confidence_interval.reason }}</p>
      <p>Intervals do not account for graph uncertainty or unmeasured confounding.</p>
      <ul><li v-for="warning in result.warnings" :key="warning">{{ warning }}</li></ul>
      <details open><summary>Group comparability and overlap</summary>
        <p>{{ result.diagnostics.note }}</p>
        <p v-if="result.diagnostics.outside_common_range_fraction !== undefined">Outside common propensity range: {{ numberText(100 * result.diagnostics.outside_common_range_fraction) }}%.</p>
        <div v-if="histRows.length" class="table-wrap"><table><caption>Estimated propensity distribution (counts)</caption>
          <thead><tr><th scope="col">Bin</th><th scope="col">Treated</th><th scope="col">Control</th></tr></thead>
          <tbody><tr v-for="row in histRows" :key="row.label"><th scope="row">{{ row.label }}</th><td><span class="bar" :style="{width: `${120 * row.treated / maxBin}px`}"></span> {{ row.treated }}</td><td><span class="bar" :style="{width: `${120 * row.control / maxBin}px`}"></span> {{ row.control }}</td></tr></tbody>
        </table></div>
        <div v-if="result.diagnostics.balance?.length" class="table-wrap"><table><caption>Standardized mean differences; “after” is available only for matching/weighting.</caption>
          <thead><tr><th scope="col">Covariate</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
          <tbody><tr v-for="row in result.diagnostics.balance" :key="row.covariate"><th scope="row">{{ row.covariate }}</th><td>{{ numberText(row.smd_before) }}</td><td>{{ numberText(row.smd_after) }}</td></tr></tbody>
        </table></div>
        <p v-if="result.diagnostics.weights">Effective sample sizes: treated {{ numberText(result.diagnostics.weights.treated_ess) }}, control {{ numberText(result.diagnostics.weights.control_ess) }}.</p>
        <p>{{ result.diagnostics.propensity_model }}</p>
      </details>
      <details><summary>Encoding, exclusions and full recorded output</summary><pre>{{ JSON.stringify(result, null, 2) }}</pre></details>
      <p>Use <strong>Reproducibility exports</strong> above to export this recorded comparison. Legacy diagnostic results are not reused for this comparison.</p>
    </article>
    <details v-if="graphId"><summary>Named runs, comparison and restore</summary>
      <button type="button" :disabled="busy" @click="refreshHistory">Refresh named runs</button>
      <div class="fields"><label>First run <select v-model="compareIds[0]"><option value="">Select</option><option v-for="r in runs" :key="r.id" :value="r.id">{{ r.name }} · {{ r.created_at }}</option></select></label><label>Second run <select v-model="compareIds[1]"><option value="">Select</option><option v-for="r in runs" :key="r.id" :value="r.id">{{ r.name }} · {{ r.created_at }}</option></select></label></div>
      <button type="button" :disabled="busy || !compareIds[0] || !compareIds[1]" @click="compareRuns">Compare recorded specifications</button>
      <pre v-if="comparison">{{ JSON.stringify(comparison, null, 2) }}</pre>
      <label>Restore a comparison JSON/ZIP bundle using this graph's raw data <input type="file" accept=".json,.zip" :disabled="busy" @change="selectBundle" /></label>
      <p>Load the matching raw CSV first. Preview validates the graph and cleaning replay, then confirmation creates a new graph. Existing analyses are never overwritten. Bundles without a reviewed comparison are not imported.</p>
      <button type="button" :disabled="busy || !bundleFile" @click="previewImport">Preview restore</button>
      <template v-if="importPreview"><pre>{{ JSON.stringify(importPreview, null, 2) }}</pre><label><input v-model="importConfirmed" type="checkbox" /> I reviewed this exact bundle, including cleaning and environment differences.</label><button type="button" :disabled="busy || !importConfirmed" @click="confirmImport">Restore into a new graph</button></template>
    </details>
  </details>
</template>
<script setup>
import { computed, reactive, ref, watch } from 'vue'
import client, { workspaceState } from '../workspace/client.js'
import { availableMethods, numberText, requestSpec, histogramRows } from '../analysis/contracts.mjs'
const props=defineProps({graphId:{type:[Number,String],default:null},variables:{type:Array,default:()=>[]},treatmentId:{type:[Number,String],default:''},outcomeId:{type:[Number,String],default:''},graphRevision:{type:Number,default:0},dataRevision:{type:String,default:''},prepareGraph:{type:Function,default:null}})
const emit=defineEmits(['sample-loaded'])
const schema=ref(null),reviewed=ref(false),independent=ref(false),result=ref(null),stale=ref(false),error=ref(''),message=ref(''),working=ref(false)
const runs=ref([]),compareIds=ref(['','']),comparison=ref(null),bundleFile=ref(null),importPreview=ref(null),importConfirmed=ref(false),pendingRestore=ref(null),configuredRoles=ref('')
const form=reactive({name:'Reviewed comparison',treatment_kind:'categorical',outcome_kind:'continuous',control_value:'',treatment_value:'',event_value:'',estimand:'ATE',method:'linear_regression',units:'outcome units',covariates:[],missing:'error',uncertainty:'auto',confidence:.95,bootstrap_reps:200})
const treatmentName=computed(()=>props.variables.find(v=>String(v.id)===String(props.treatmentId))?.name||'')
const outcomeName=computed(()=>props.variables.find(v=>String(v.id)===String(props.outcomeId))?.name||'')
const treatmentColumn=computed(()=>schema.value?.columns.find(c=>c.name===treatmentName.value))
const outcomeColumn=computed(()=>schema.value?.columns.find(c=>c.name===outcomeName.value))
const methods=computed(()=>availableMethods(form.treatment_kind,form.outcome_kind))
const busy=computed(()=>working.value||workspaceState.pending>0)
const histRows=computed(()=>histogramRows(result.value?.diagnostics.histogram))
const maxBin=computed(()=>Math.max(1,...histRows.value.flatMap(r=>[r.treated,r.control])))
function fail(e){error.value=e?.response?.data?.error||e.message||'Comparison request failed.'}
function invalidate(){reviewed.value=false;stale.value=true;importPreview.value=null;importConfirmed.value=false}
watch(form,invalidate,{deep:true});watch(()=>props.graphRevision,invalidate);watch(()=>props.dataRevision,invalidate);watch(()=>workspaceState.seed,invalidate)
watch([()=>props.graphId,treatmentName,outcomeName],()=>{schema.value=null;independent.value=false;invalidate();runs.value=[];compareIds.value=['',''];comparison.value=null})
async function refreshSchema(){
 if(!props.graphId)return
 working.value=true;error.value=''
 try{
  if(props.prepareGraph&&!(await props.prepareGraph(false)))throw new Error('Save a graph before reviewing the comparison.')
  const roles=`${props.graphId}:${treatmentName.value}:${outcomeName.value}`,preserve=configuredRoles.value===roles
  const previous=new Map(form.covariates.map(c=>[c.name,{...c}]))
  schema.value=(await client.get('/api/analysis/schema/',{params:{graph_id:props.graphId,treatment:treatmentName.value}})).data
  form.covariates=schema.value.columns.filter(c=>![treatmentName.value,outcomeName.value].includes(c.name)).map(c=>({name:c.name,kind:c.suggested_kind,reference:c.levels[0]??'',enabled:schema.value.suggested_adjustment.includes(c.name),interaction:false,...(preserve?previous.get(c.name):{}),levels:c.levels}))
  if(!preserve){const levels=treatmentColumn.value?.levels||[];form.treatment_kind=levels.length?'categorical':'continuous';form.control_value=levels[0]??treatmentColumn.value?.min??'';form.treatment_value=levels[1]??treatmentColumn.value?.max??'';form.outcome_kind=outcomeColumn.value?.unique_count===2?'binary':'continuous';form.event_value='';form.estimand='ATE';form.method='linear_regression'}
  configuredRoles.value=roles
  if(pendingRestore.value){const imported=pendingRestore.value;for(const k of Object.keys(form))if(k!=='covariates'&&k in imported)form[k]=imported[k];form.covariates=form.covariates.map(c=>{const old=imported.covariates.find(v=>v.name===c.name);return {...c,...old,enabled:Boolean(old),interaction:imported.interactions.includes(c.name)}});pendingRestore.value=null}
  message.value='Review all settings. Select the binary outcome event explicitly, then confirm.'
 }catch(e){fail(e)}finally{working.value=false}
}
async function run(){
 const specification=requestSpec(form,{treatment:treatmentName.value,outcome:outcomeName.value,seed:workspaceState.seed,reviewed:reviewed.value,independent:independent.value}),state=schema.value?.state_id,gid=props.graphId
 if(!state)return
 working.value=true;error.value=''
 try{
  if(props.prepareGraph&&!(await props.prepareGraph(false)))throw new Error('Graph save failed.')
  const revision=props.graphRevision
  result.value=(await client.post('/api/analysis/estimate/',{graph_id:gid,state_id:state,specification})).data
  stale.value=props.graphRevision!==revision;message.value='Comparison recorded. Inspect uncertainty, exclusions and group comparability.';await refreshHistory()
 }catch(e){fail(e)}finally{working.value=false}
}
async function loadSynthetic(id){working.value=true;error.value='';try{emit('sample-loaded',(await client.post(`/api/analysis/examples/${id}/load/`,{})).data);message.value='Synthetic data loaded. Review current data and graph before estimating.'}catch(e){fail(e)}finally{working.value=false}}
async function refreshHistory(){try{runs.value=(await client.get('/api/analysis/history/',{params:{graph_id:props.graphId}})).data.runs}catch(e){fail(e)}}
async function compareRuns(){working.value=true;error.value='';try{comparison.value=(await client.post('/api/analysis/compare/',{run_ids:compareIds.value})).data}catch(e){fail(e)}finally{working.value=false}}
function selectBundle(event){bundleFile.value=event.target.files?.[0]||null;importPreview.value=null;importConfirmed.value=false}
function importForm(){const data=new FormData();data.append('graph_id',props.graphId);data.append('bundle',bundleFile.value);return data}
async function previewImport(){working.value=true;error.value='';importConfirmed.value=false;try{importPreview.value=(await client.post('/api/analysis/bundles/preview/',importForm())).data}catch(e){importPreview.value=null;fail(e)}finally{working.value=false}}
async function confirmImport(){working.value=true;error.value='';try{const data=importForm();data.append('confirmed','true');data.append('approval_digest',importPreview.value.approval_digest);const r=(await client.post('/api/analysis/bundles/restore/',data)).data;pendingRestore.value=r.comparison_specification;workspaceState.seed=r.comparison_specification.seed;emit('sample-loaded',r);schema.value=null;result.value=null;importPreview.value=null;importConfirmed.value=false;message.value='Restored into a new graph without estimating. Review current data and graph to load its settings.'}catch(e){fail(e)}finally{working.value=false}}
</script>
<style scoped>
.analysis-panel{border:1px solid var(--color-border,#ccd3dd);background:var(--color-background,#fff);padding:14px;margin:12px 0;border-radius:8px;min-width:0}summary{cursor:pointer;font-weight:650;padding:.5rem 0}p{line-height:1.6}.actions{display:flex;gap:.6rem;flex-wrap:wrap}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:12px}label{display:block;line-height:1.5;margin:.4rem 0}.fields label{display:flex;flex-direction:column;gap:5px}fieldset{min-width:0;margin:14px 0;padding:12px;border:1px solid var(--color-border,#ccd3dd);border-radius:8px}legend{font-weight:650}input:not([type=checkbox]),select,button{max-width:100%;min-height:40px;padding:8px;border:1px solid var(--color-border,#ccd3dd);border-radius:6px}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.55}pre{max-height:320px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:.82rem}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}caption{text-align:left;padding:.6rem 0}th,td{text-align:left;padding:.5rem;border-bottom:1px solid var(--color-border,#ccd3dd)}.bar{display:inline-block;height:.5rem;background:currentColor;opacity:.55}.notice{border-left:3px solid currentColor;padding:.6rem}button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid currentColor;outline-offset:3px}
</style>
