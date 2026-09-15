const TOKEN_KEY = "aitiolin-p0-session"

export function sessionToken() {
  let token = sessionStorage.getItem(TOKEN_KEY)
  if (!/^[a-f0-9]{64}$/.test(token || "")) {
    const bytes = crypto.getRandomValues(new Uint8Array(32))
    token = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("")
    sessionStorage.setItem(TOKEN_KEY, token)
  }
  return token
}

export function clearSessionStorage() {
  // Graph drafts are in memory in the inspected application; reload clears them.
  // Do not delete unrelated site storage.
  sessionStorage.removeItem(TOKEN_KEY)
}
