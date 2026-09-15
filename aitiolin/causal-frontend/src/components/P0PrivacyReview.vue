<template>
  <dialog ref="dialog" class="privacy-dialog" aria-labelledby="privacy-review-title" @cancel.prevent="resolveReview(false)">
    <template v-if="p0State.review">
      <h2 id="privacy-review-title">Review what will be sent</h2>
      <p>{{ p0State.review.policy }}</p>
      <p><strong>Destination:</strong> {{ p0State.review.provider }} · Model: {{ p0State.review.payload?.model }}</p>
      <pre tabindex="0" aria-label="Exact outgoing request">{{ JSON.stringify(p0State.review.payload, null, 2) }}</pre>
      <p>{{ p0State.review.provider_notice }}</p>
      <p>Approval is for this payload only and expires after two minutes. Closing this dialog sends nothing.</p>
      <div class="actions">
        <button type="button" autofocus @click="resolveReview(false)">Cancel — do not send</button>
        <button type="button" @click="resolveReview(true)">Approve this request</button>
      </div>
    </template>
  </dialog>
</template>
<script setup>
import { nextTick, onUnmounted, ref, watch } from "vue"
import { p0State, resolveReview } from "../p0/client.js"
const dialog = ref(null)
watch(() => p0State.review, async review => {
  await nextTick()
  if (review && !dialog.value?.open) dialog.value?.showModal()
  if (!review && dialog.value?.open) dialog.value?.close()
})
onUnmounted(() => resolveReview(false))
</script>
<style scoped>
.privacy-dialog{width:min(760px,92vw);max-height:85vh;border:1px solid var(--color-border,#ccc);border-radius:12px;padding:1.4rem;color:var(--color-text,#182235);background:var(--color-background,#fff)}
.privacy-dialog::backdrop{background:rgba(0,0,0,.5)}
pre{max-height:35vh;overflow:auto;white-space:pre-wrap;word-break:break-word;background:#f4f6f8;padding:1rem;color:#182235}
.actions{display:flex;flex-wrap:wrap;gap:.8rem}button{min-height:44px;padding:.6rem 1rem;cursor:pointer}
</style>
