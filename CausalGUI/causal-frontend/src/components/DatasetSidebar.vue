<template>
  <aside class="sidebar">
    <h2 class="sidebar-title">📊 Dataset</h2>
    <p class="sidebar-note">Upload a CSV and drag variables into the graph.</p>
    <input class="file-input" type="file" accept=".csv" @change="onFileChange" />

    <div class="section-header">
      <h3>📌 Variables</h3>
      <span class="variable-count">{{ variables.length }}</span>
    </div>
    <ul v-if="variables.length" class="variables-list">
      <li
        v-for="item in variables"
        :key="item.id"
        class="variable-item"
        draggable="true"
        @dragstart="onDragStart(item.name, $event)"
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
defineProps({
  variables: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(["file-upload", "drag-start"])

function onFileChange(event) {
  emit("file-upload", event)
}

function onDragStart(variableName, event) {
  emit("drag-start", variableName, event)
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
