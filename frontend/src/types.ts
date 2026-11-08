export type OrderStatus = 'PAYING' | 'PAID' | 'FAILED' | 'PENDING_APPROVAL' | 'REJECTED' | 'BLOCKED'

export interface RuleHit { rule: string; outcome: 'APPROVE' | 'NEEDS_APPROVAL' | 'BLOCK'; message: string }

export interface DecisionView {
  outcome: string
  decided_by: 'policy' | 'owner'
  note: string
  rules_fired: RuleHit[]
  at: string
}

export interface Order {
  id: number
  request_text: string
  status: OrderStatus
  total_inr: number
  supplier: { id: string; name: string; approved: boolean }
  lines: { item_id: string; name: string; qty: number; unit_price_inr: number; line_total_inr: number }[]
  agent_reasoning: string
  decisions: DecisionView[]
  payment: null | { paypal_batch_id: string; amount_usd: number; status: string; receiver_email: string }
  created_at: string
}

export interface RequestResult {
  order: Order | null
  agent_message: string
  agent_steps: { tool: string; args: Record<string, unknown> }[]
}

export interface Budget {
  monthly_budget_inr: number
  normal_monthly_budget_inr: number
  raised_this_month: boolean
  spent_inr: number
  pending_approval_inr: number
  remaining_inr: number
  auto_approve_limit_inr: number
  hard_cap_inr: number
}

export interface Policy {
  monthly_budget_inr: number
  this_month_budget_inr: number
  budget_overrides: Record<string, number>
  auto_approve_limit_inr: number
  hard_cap_inr: number
  max_orders_per_day: number
  price_tolerance_pct: number
  duplicate_window_hours: number
  approved_vendors: string[]
  allowed_categories: string[]
  inr_per_usd: number
}

export interface AuditRow { order_id: number; outcome: string; decided_by: string; note: string; rules_fired: RuleHit[]; at: string }

export interface Catalogue {
  suppliers: { id: string; name: string; city: string; approved: boolean; categories: string[] }[]
  items: { id: string; supplier_id: string; name: string; category: string; unit: string; unit_price_inr: number }[]
}
