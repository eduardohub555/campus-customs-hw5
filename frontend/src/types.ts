export type TicketStatus = 'open' | 'resolved'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: TicketStatus
  is_open: boolean
  notes?: string | null
  sku?: string | null
  size?: string | null
  qty?: number | null
  lease_id?: number | null
  invoice_id?: number | null
  created_at: string
}

export interface AgentSummary {
  agent: AgentKey
  says: string | null
  action: string | null
  draft: string | null
  needs_human_approval: boolean | null
  tools: string[]
}

export interface RunResult {
  run_id: string
  ticket_id: number
  model: string
  decision: {
    decision: string
    rationale: string
    assigned_to: string
    instruction_given: string
    needs_human_approval: boolean
    awaiting_human: string | null
  }
  agents_involved: AgentKey[]
  tools_called: string[]
  delegations: string[]
  agent_summaries: AgentSummary[]
  needs_human_approval: boolean
  awaiting_human: string | null
  resolved: boolean
  duration_ms: number
  tokens: { input: number; output: number }
  vs_expected: Record<string, unknown>
}

export interface Obligation {
  kind: 'invoice' | 'rent'
  ref_id: number
  label: string
  payee: string
  amount: number
  paid: boolean
}

export interface CashState {
  account: string
  balance: number
  as_of: string
  open_invoice_total: number
  rent_total: number
  remaining_if_all_paid: number
  outstanding_total: number
  obligations: Obligation[]
  payment_count: number
  payments: Array<{
    id: number
    kind: string
    ref_id: number
    amount: number
    paid_at: string
    approved_by: string
  }>
}

export interface AgentEvent {
  run_id: string
  step: number
  at: string
  agent: AgentKey
  event: 'agent_run' | 'tool_call' | 'delegation' | 'refusal' | 'approval' | 'reset'
  ticket_id: number | null
  note?: string | null
  tool_name?: string
  tool_args?: Record<string, unknown>
  says?: string | null
  draft_message?: string | null
}

export type AgentKey =
  | 'boss'
  | 'inventory'
  | 'accounting'
  | 'facilities'
  | 'customer_service'
