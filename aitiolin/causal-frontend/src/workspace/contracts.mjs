export const prototypeNotice = "Experimental prototype for private learning and hypothesis exploration; not validated for production or operational business decisions."

export function finite(value) {
  if (value === null || value === undefined || (typeof value === "string" && !value.trim()) || !["number", "string"].includes(typeof value)) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function metric(value) {
  const number = finite(value)
  return number === null ? "Not available" : number.toFixed(4)
}

export function sweepGeometry(points = []) {
  const valid = points.map(point => ({ x: finite(point.confounder_strength), y: finite(point.adjusted_effect) }))
    .filter(point => point.x !== null && point.y !== null).sort((a, b) => a.x - b.x)
  if (valid.length < 2) return null
  const xmin = Math.min(...valid.map(p => p.x)), xmax = Math.max(...valid.map(p => p.x))
  const ymin = Math.min(0, ...valid.map(p => p.y)), ymax = Math.max(0, ...valid.map(p => p.y))
  const xspan = xmax - xmin || 1, yspan = ymax - ymin || 1
  return {
    points: valid.map(p => `${65 + (p.x - xmin) / xspan * 490},${210 - (p.y - ymin) / yspan * 165}`).join(" "),
    zero: 210 - (0 - ymin) / yspan * 165,
    xmin, xmax, ymin, ymax,
  }
}

export function evidenceStatus(value) {
  const status = String(value?.status || "not_run").toLowerCase()
  if (value?.error || ["error", "failed_to_run"].includes(status)) return "Error / unavailable"
  if (["passed", "pass", "stable"].includes(status)) return "No contradiction found by this check"
  if (["failed", "fail", "refuted", "unstable"].includes(status)) return "Potential contradiction — inspect details"
  if (["skipped", "unsupported", "not_run"].includes(status)) return "Not run / unsupported"
  return status.replaceAll("_", " ")
}
