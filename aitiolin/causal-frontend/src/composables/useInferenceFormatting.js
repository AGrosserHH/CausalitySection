export const METHOD_LABELS = {
  "backdoor.linear_regression": "Backdoor | Linear Regression",
  "backdoor.propensity_score_matching": "Backdoor | Propensity Score Matching",
  "backdoor.propensity_score_weighting": "Backdoor | Propensity Score Weighting",
  "backdoor.doubly_robust_estimator": "Backdoor | Doubly Robust",
  "iv.instrumental_variable": "Instrumental Variable",
  "frontdoor.two_stage_regression": "Frontdoor | Two-Stage Regression",
  "backdoor.diff_in_means_fallback": "Fallback | Difference in Means",
}

export function methodLabel(method) {
  if (!method) {
    return "Not specified"
  }
  return METHOD_LABELS[method] || method
}

export function formatEffectValue(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "N/A"
  }
  return parsed.toFixed(4)
}

export function interpretEffect(value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return "No estimate was returned."
  }
  if (Math.abs(parsed) < 0.001) {
    return "Very small estimated effect."
  }
  if (parsed > 0) {
    return "Increasing treatment is associated with higher outcome."
  }
  return "Increasing treatment is associated with lower outcome."
}

export function buildInterpretation({ effect, treatmentName, outcomeName, methodName, adjustmentSet = [] }) {
  const parsed = Number(effect)
  if (!Number.isFinite(parsed)) {
    return ["No estimate was returned, so no interpretation is possible."]
  }

  const treatment = treatmentName || "the treatment"
  const outcome = outcomeName || "the outcome"
  const magnitude = Math.abs(parsed).toFixed(4)
  const sentences = []

  if (Math.abs(parsed) < 0.001) {
    sentences.push(
      `The estimated causal effect of "${treatment}" on "${outcome}" is essentially zero (${parsed.toFixed(4)}): according to this model, intervening on "${treatment}" would leave "${outcome}" practically unchanged.`,
    )
  } else {
    const direction = parsed > 0 ? "increase" : "decrease"
    sentences.push(
      `According to this model, a one-unit increase in "${treatment}" causes "${outcome}" to ${direction} by ${magnitude} on average.`,
    )
    sentences.push(
      parsed > 0
        ? `In practical terms: pushing "${treatment}" up is expected to push "${outcome}" up as well.`
        : `In practical terms: pushing "${treatment}" up is expected to bring "${outcome}" down.`,
    )
  }

  if (adjustmentSet.length) {
    sentences.push(
      `The estimate was computed with ${methodLabel(methodName)}, adjusting for ${adjustmentSet.join(", ")} to block the confounding paths your graph identifies.`,
    )
  } else {
    sentences.push(
      `The estimate was computed with ${methodLabel(methodName)}; the graph required no adjustment set, so the raw treatment-outcome relationship was taken at face value.`,
    )
  }

  sentences.push(
    "This number is only as trustworthy as the drawn graph: before acting on it, run the robustness checks and the competing-model comparison to see whether it survives different assumptions.",
  )

  return sentences
}
