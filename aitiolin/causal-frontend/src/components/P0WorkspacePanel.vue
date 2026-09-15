<template>
  <section class="p0-panel" aria-label="Prototype samples, exports and privacy">
    <p class="notice">{{ prototypeNotice }}</p>
    <p class="notice">CSV files are processed and stored by the Django server. This is local only when you run that server on your own computer. External AI is off by default.</p>
    <div class="toolbar">
      <label>Try a sample
        <select v-model="sampleId" :disabled="busy">
          <option v-for="item in samples" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </label>
      <button type="button" :disabled="busy || !sampleId" @click="loadSample">Load guided example</button>
      <label>Analysis seed <input v-model.number="p0State.seed" type="number" min="0" max="4294967295" step="1" placeholder="42 (default)" :disabled="busy" /></label>
    </div>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <details v-if="selectedSample">
      <summary>Sample question and limitations</summary>
      <p>{{ selectedSample.description }}</p>
      <ul><li v-for="warning in selectedSample.warnings" :key="warning">{{ warning }}</li></ul>
      <p>No LLM call or silent cleaning is needed to load the preset. Review the graph before analysis.</p>
    </details>
    <div v-if="guide" class="guide">
      <strong>Guided example</strong>
      <label><input v-model="reviewed" type="checkbox" /> I have reviewed the preset graph and its limitations.</label>
      <ol>
        <li>Review the preset DAG and sample limitations on the canvas.</li>
        <li><button type="button" :disabled="busy || !graphId || !reviewed" @click="$emit('estimate')">Estimate under this graph</button></li>
        <li><button type="button" :disabled="busy || !hasEstimate" @click="$emit('check')">Run diagnostic checks</button>
            <button type="button" :disabled="busy || !hasEstimate" @click="$emit('compare')">Compare alternative DAGs</button></li>
        <li>Inspect the evidence; export a recorded run below. No result is a recommendation.</li>
      </ol>
      <button type="button" @click="guide = false">Hide guide</button>
    </div>
    <details>
      <summary>Reproducibility exports</summary>
      <p>Exports contain recorded metadata and results, not CSV rows. Variable names and annotations can still be sensitive. Choose the latest completed stage to include preceding checks from the same graph, data, query and seed. Re-running requires matching local data.</p>
      <div class="toolbar">
        <button type="button" :disabled="busy || !graphId" @click="refreshRuns">Refresh runs</button>
        <label>Recorded stage <select v-model="runId" :disabled="busy"><option value="">Choose a run</option><option v-for="run in runs" :key="run.id" :value="run.id">{{ run.operation }} · {{ run.status }} · {{ run.created_at }}</option></select></label>
        <button type="button" :disabled="busy || !runId" @click="download('zip')">Export ZIP</button>
        <button type="button" :disabled="busy || !runId" @click="download('json')">Export JSON</button>
      </div>
    </details>
    <details>
      <summary>What leaves this machine? Privacy and deletion</summary>
      <dl v-if="session"><template v-for="(text, key) in session.data_flow" :key="key"><dt>{{ key.replaceAll('_', ' ') }}</dt><dd>{{ text }}</dd></template></dl>
      <label><input v-model="p0State.llmEnabled" type="checkbox" :disabled="busy || !session?.llm_available" /> Enable LLM-assisted actions, with a preview before every transmission</label>
      <p v-if="!session?.llm_available">No provider key configured. Deterministic profiling, cleaning and heuristic model suggestions remain available.</p>
      <p v-if="session">Server access expires: {{ session.expires_at }}</p>
      <div class="toolbar">
        <label>Maximum remaining retention <select v-model.number="retention" :disabled="busy"><option :value="1">1 hour</option><option :value="6">6 hours</option><option :value="24">24 hours</option></select></label>
        <button type="button" :disabled="busy" @click="saveRetention">Set retention</button>
        <button type="button" :disabled="busy" @click="deleteData">Delete session data</button>
      </div>
      <p>Deletion removes owned server files and records and this tab's session key; reloading clears the in-memory workspace. Unrelated browser storage, downloaded bundles, host logs/backups and provider-side records are outside this action.</p>
    </details>
    <P0PrivacyReview />
  </section>
</template>
<script setup>
import { computed, onMounted, ref, watch } from "vue"
import client, { p0State } from "../p0/client.js"
import { clearSessionStorage } from "../p0/storage.js"
import { prototypeNotice } from "../p0/contracts.mjs"
import P0PrivacyReview from "./P0PrivacyReview.vue"
const props = defineProps({ graphId: { type: [Number, String], default: null }, hasEstimate: Boolean })
const emit = defineEmits(["sample-loaded", "estimate", "check", "compare"])
const samples = ref([]), sampleId = ref("churn"), session = ref(null), retention = ref(24)
const reviewed = ref(false), loadedSampleId = ref("")
const runs = ref([]), runId = ref(""), guide = ref(false), message = ref(""), error = ref("")
const busy = computed(() => p0State.pending > 0)
const selectedSample = computed(() => samples.value.find(item => item.id === (guide.value ? loadedSampleId.value : sampleId.value)))
function failure(err) { error.value = err?.response?.data?.error || err.message || "Request failed." }
async function refreshSession() { session.value = (await client.get("/api/p0/session/")).data }
onMounted(async () => {
  try { await refreshSession(); samples.value = (await client.get("/api/p0/samples/")).data.samples }
  catch (err) { failure(err) }
})
async function loadSample() {
  error.value = ""
  try {
    const response = await client.post(`/api/p0/samples/${sampleId.value}/load/`, {})
    loadedSampleId.value = sampleId.value
    emit("sample-loaded", response.data); guide.value = true; reviewed.value = false
    message.value = "Sample copied into this private session. Review the preset graph and limitations before estimating."
  } catch (err) { failure(err) }
}
async function refreshRuns() {
  if (!props.graphId) { runs.value = []; runId.value = ""; return }
  try {
    runs.value = (await client.get(`/api/p0/graphs/${props.graphId}/runs/`)).data.runs
    runId.value = runs.value[0]?.id || ""
  } catch (err) { failure(err) }
}
watch(() => props.graphId, () => { runs.value = []; runId.value = "" })
watch(() => p0State.runRevision, refreshRuns)
async function download(format) {
  try {
    const response = await client.get(`/api/p0/runs/${runId.value}/bundle/?file_format=${format}`, { responseType: "blob" })
    const url = URL.createObjectURL(response.data), link = document.createElement("a")
    link.href = url; link.download = `aitiolin-run-${runId.value}.${format}`
    document.body.appendChild(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) { failure(err) }
}
async function saveRetention() {
  try { session.value = (await client.patch("/api/p0/session/", { retention_hours: retention.value })).data }
  catch (err) { failure(err) }
}
async function deleteData() {
  if (!window.confirm("Delete this session's server uploads, cleaned copies, graphs and recorded runs? This cannot be undone. Downloaded exports and provider records are not removed.")) return
  try {
    await client.delete("/api/p0/session/data/")
    clearSessionStorage(); window.location.reload()
  } catch (err) { failure(err) }
}
</script>
<style scoped>
.p0-panel{border:1px solid var(--color-border,#ccd3dd);border-radius:8px;background:var(--color-background,#fff);padding:14px;margin:12px 0}
.notice{font-size:.9rem}.toolbar{display:flex;flex-wrap:wrap;gap:.7rem;align-items:end}.toolbar label{display:flex;flex-direction:column;gap:.3rem}button,select,input[type=number]{min-height:40px;padding:.45rem .65rem;max-width:100%;border:1px solid var(--color-border,#ccd3dd);border-radius:6px}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.55}details{margin-top:.8rem}summary{cursor:pointer;font-weight:600;padding:.35rem 0}.guide{border-left:3px solid var(--color-border,#9aa);padding:.5rem 1rem;margin-top:.8rem}li{margin-bottom:.5rem}dt{font-weight:600;text-transform:capitalize}dd{margin:0 0 .8rem}input[type=number]{width:140px}
</style>
