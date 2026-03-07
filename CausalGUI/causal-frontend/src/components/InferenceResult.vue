<template>
  <div v-if="inferenceResult !== null" class="inference-result">
    <h3>📊 Inference Result</h3>
    <p><strong>Estimated Effect:</strong> {{ inferenceResult }}</p>
    <div v-if="causalGraphImageUrl">
      <h4>📈 Causal Graph</h4>
      <img :src="causalGraphImageUrl" alt="Causal Graph" class="graph-image" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  inferenceResult: {
    type: [String, Number, null],
    default: null,
  },
  causalGraphImageUrl: {
    type: String,
    default: "",
  },
})
</script>

<style scoped>
.inference-result {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  padding: 16px;
  border-radius: 8px;
}

.inference-result h3,
.inference-result h4,
.inference-result p {
  margin: 0;
}

.inference-result h3 {
  margin-bottom: 8px;
}

.inference-result p {
  margin-bottom: 12px;
}

.graph-image {
  max-width: 100%;
  border-radius: 6px;
  border: 1px solid var(--color-border);
}
</style>
