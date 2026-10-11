const TOKEN_KEY = 'healthies.token'
const USER_KEY = 'healthies.user'

function safeGet(k) { try { return localStorage.getItem(k) } catch { return null } }
function safeSet(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch { /* ignore */ } }

export const session = {
  get token() { return safeGet(TOKEN_KEY) },
  get user() { try { return JSON.parse(safeGet(USER_KEY) || 'null') } catch { return null } },
  set(token, user) { safeSet(TOKEN_KEY, token); safeSet(USER_KEY, JSON.stringify(user)) },
  clear() { safeSet(TOKEN_KEY, null); safeSet(USER_KEY, null) },
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail?.message || 'Request failed')
    this.status = status
    this.detail = detail
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  let res
  try {
    res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError(0, null)
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && session.token) { session.clear(); window.dispatchEvent(new Event('healthies:signedout')) }
    let detail = data?.detail
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join('; ')
    throw new ApiError(res.status, detail)
  }
  return data
}

export const get = (p) => api(p)
export const post = (p, body = {}) => api(p, { method: 'POST', body })
export const put = (p, body = {}) => api(p, { method: 'PUT', body })
