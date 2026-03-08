<template>
  <aside class="sidebar">
    <h2 class="sidebar-title">Dataset</h2>
    <p class="sidebar-note">Upload a CSV and drag variables into the graph.</p>
    <input class="file-input" type="file" accept=".csv" @change="onFileChange" />

    <div v-if="datasetName" class="dataset-meta">
      <p class="dataset-line"><strong>Loaded:</strong> {{ datasetName }}</p>
      <p class="dataset-line"><strong>Graph ID:</strong> {{ graphId }}</p>
    </div>

    <div v-if="previewHeaders.length" class="preview-wrap">
      <div class="section-header preview-header">
        <h3>Preview</h3>
        <span class="variable-count">{{ previewRows.length }}</span>
      </div>
      <div class="preview-table-wrap">
        <table class="preview-table">
          <thead>
            <tr>
              <th v-for="header in previewHeaders" :key="`header-${header}`">{{ header }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in previewRows" :key="`row-${index}`">
              <td v-for="header in previewHeaders" :key="`cell-${index}-${header}`">
                {{ normalizeCellValue(row?.[header]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="section-header">
      <h3>Variables</h3>
      <span class="variable-count">{{ variables.length }}</span>
    </div>
    <ul v-if="variables.length" class="variables-list">
      <li
        v-for="item in variables"
        :key="item.id"
        class="variable-item"
        draggable="true"
        @dragstart="onDragStart(item, $event)"
      >
        {{ item.name }}
      </li>
    </ul>

    <div v-else class="empty-state">
      <p>No variables yet.</p>
      <p class="empty-state-hint">Upload a CSV file to populate this panel.</p>
    </div>
  </aside>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  variables: {
    type: Array,
    default: () => [],
  },
  datasetName: {
    type: String,
    default: "",
  },
  graphId: {
    type: [String, Number, null],
    default: null,
  },
  previewRows: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(["file-upload"])

const previewHeaders = computed(() => {
  const firstRow = props.previewRows?.[0]
  if (!firstRow || typeof firstRow !== "object") {
    return []
  }

  return Object.keys(firstRow)
})

function normalizeCellValue(value) {
  if (value === null || value === undefined || value === "") {
    return "--"
  }
  return String(value)
}

function onFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) {
    return
  }

  emit("file-upload", file)
  event.target.value = ""
}

function onDragStart(variable, event) {
  event.dataTransfer.setData(
    "application/json",
    JSON.stringify({
      id: variable.id,
      name: variable.name,
    }),
  )
  event.dataTransfer.setData("text/plain", variable.name)
  event.dataTransfer.effectAllowed = "copy"
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 260px;
  background-color: #1f2937;
  color: white;
  padding: 18px 16px;
  box-sizing: border-box;
  overflow-y: auto;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
}

.sidebar-note {
  margin: 6px 0 12px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
}

.file-input {
  width: 100%;
  margin-bottom: 14px;
}

.dataset-meta {
  margin: 2px 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 6px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.06);
}

.dataset-line {
  margin: 0;
  font-size: 0.82rem;
  word-break: break-word;
}

.dataset-line + .dataset-line {
  margin-top: 4px;
}

.preview-wrap {
  margin-bottom: 14px;
}

.preview-header {
  margin-top: 2px;
}

.preview-table-wrap {
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  overflow-x: auto;
  max-height: 180px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.76rem;
}

.preview-table th,
.preview-table td {
  text-align: left;
  vertical-align: top;
  padding: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  white-space: nowrap;
}

.preview-table th {
  position: sticky;
  top: 0;
  background: #1f2937;
  z-index: 1;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.variable-count {
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  padding: 2px 10px;
  font-size: 0.8rem;
}

.variables-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.variable-item {
  padding: 7px 8px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 4px;
  cursor: grab;
  word-break: break-word;
}

.variable-item:hover {
  background: rgba(255, 255, 255, 0.2);
}

.empty-state {
  margin-top: 6px;
  border: 1px dashed rgba(255, 255, 255, 0.3);
  border-radius: 6px;
  padding: 10px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.9rem;
}

.empty-state-hint {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.82rem;
}

@media (max-width: 1024px) {
  .sidebar {
    width: 240px;
    min-width: 220px;
  }
}

@media (max-width: 768px) {
  .sidebar {
    width: 100%;
    min-width: 0;
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
}
</style>
