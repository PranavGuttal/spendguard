import type { AuditRow, Budget, Catalogue, Order, Policy, RequestResult } from './types'

const PW_KEY = 'spendguard-demo-password'

function readPassword(): string {
  try { return localStorage.getItem(PW_KEY) ?? '' } catch { return '' }
}
export function savePassword(pw: string): void {
  try { localStorage.setItem(PW_KEY, pw) } catch { /* storage unavailable: kept for this page only */ }
  memoryPassword = pw
}
let memoryPassword = readPassword()

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (memoryPassword) headers['X-Demo-Password'] = memoryPassword
  let res: Response
  try {
    res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) } })
  } catch {
    throw new ApiError(0, 'Cannot reach the SpendGuard server. Check that it is running.')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { const body = await res.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail) } catch { /* not JSON */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  request: (text: string) => call<RequestResult>('/api/requests', { method: 'POST', body: JSON.stringify({ text }) }),
  orders: () => call<Order[]>('/api/orders'),
  approve: (id: number) => call<Order>(`/api/orders/${id}/approve`, { method: 'POST', body: '{}' }),
  reject: (id: number) => call<Order>(`/api/orders/${id}/reject`, { method: 'POST', body: '{}' }),
  refresh: (id: number) => call<Order>(`/api/orders/${id}/refresh`, { method: 'POST' }),
  budget: () => call<Budget>('/api/budget'),
  audit: () => call<AuditRow[]>('/api/audit'),
  policy: () => call<Policy>('/api/policy'),
  catalogue: () => call<Catalogue>('/api/catalogue'),
  ask: (question: string) => call<{ answer: string; tools_used: string[] }>('/api/ask', { method: 'POST', body: JSON.stringify({ question }) }),
  reset: () => call<{ ok: boolean }>('/api/demo/reset', { method: 'POST' }),
}

export const inr = (n: number) => '₹' + Math.round(n).toLocaleString('en-IN')
export const usd = (n: number) => '$' + n.toFixed(2)
export const when = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
