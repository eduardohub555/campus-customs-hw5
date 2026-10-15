import type { AgentEvent, CashState, RunResult, Ticket } from './types'

const BASE = 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) {
    // FastAPI puts the useful part in `detail`; surface it rather than a bare code.
    try {
      throw new Error(JSON.parse(text).detail ?? text)
    } catch (e) {
      throw e instanceof Error ? e : new Error(text)
    }
  }
  return JSON.parse(text) as T
}

export const api = {
  health: () => get<{ ok: boolean; model: string; shop_date: string }>('/health'),
  tickets: () => get<Ticket[]>('/tickets'),
  cash: () => get<CashState>('/cash'),
  events: (ticketId?: number, limit = 60) =>
    get<{ events: AgentEvent[]; total_available: number }>(
      `/events?limit=${limit}${ticketId ? `&ticket_id=${ticketId}` : ''}`,
    ),
  runTicket: (id: number) => post<RunResult>(`/tickets/${id}/run`),
  reset: () => post<{ reset: boolean; after: Record<string, number> }>('/reset'),
  approve: (body: {
    kind: 'invoice' | 'rent' | 'purchase_order'
    ref_id: number
    approved_by: string
    confirm: boolean
    ticket_id?: number
    sku?: string
    size?: string
    qty?: number
  }) => post<{ approved: boolean; amount?: number; balance_after?: number; cash_changed: boolean }>(
    '/approvals',
    body,
  ),
}
