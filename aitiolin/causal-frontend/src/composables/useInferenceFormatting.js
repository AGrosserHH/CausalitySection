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
