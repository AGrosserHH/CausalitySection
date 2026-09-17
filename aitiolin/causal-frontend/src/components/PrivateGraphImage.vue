<template><img v-if="image" :src="image" alt="Recorded causal graph" /><p v-else-if="error" role="status">{{ error }}</p></template>
<script setup>
import { onUnmounted, ref, watch } from "vue"
import client from "../workspace/client.js"
const props = defineProps({ url: { type: String, default: "" } })
const image = ref(""), error = ref("")
let revision = 0
function revoke() { if (image.value) URL.revokeObjectURL(image.value); image.value = "" }
watch(() => props.url, async url => {
  const current = ++revision
  revoke(); error.value = ""
  if (!url) return
  try {
    if (!/^\/api\/workspace\/graphs\/\d+\/image\/$/.test(url)) throw new Error("Unexpected graph image route.")
    const response = await client.get(url, { responseType: "blob" })
    if (current === revision) image.value = URL.createObjectURL(response.data)
  } catch { if (current === revision) error.value = "Graph image unavailable; the canvas remains available." }
}, { immediate: true })
onUnmounted(() => { revision += 1; revoke() })
</script>
<style scoped>img{display:block;max-width:100%;height:auto}</style>
