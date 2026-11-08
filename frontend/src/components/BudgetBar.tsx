import { inr } from '../api'
import type { Budget } from '../types'

export function BudgetBar({ budget }: { budget: Budget | null }) {
  if (!budget) return <div className="budget budget--loading">Loading budget…</div>
  const total = budget.monthly_budget_inr || 1
  const spentPct = Math.min(100, (budget.spent_inr / total) * 100)
  const heldPct = Math.min(100 - spentPct, (budget.pending_approval_inr / total) * 100)
  return (
    <section className="budget" aria-label="This month's budget">
      <p className="budget__left">{inr(budget.remaining_inr)}</p>
      <p className="budget__of">left of {inr(budget.monthly_budget_inr)} this month</p>
      {budget.raised_this_month && (
        <p className="budget__raised">Raised for this month only (normally {inr(budget.normal_monthly_budget_inr)})</p>
      )}
      <div className="budget__track" role="img"
        aria-label={`Spent ${inr(budget.spent_inr)}, waiting for approval ${inr(budget.pending_approval_inr)}`}>
        <div className="budget__spent" style={{ width: `${spentPct}%` }} />
        <div className="budget__held" style={{ width: `${heldPct}%` }} />
      </div>
      <div className="budget__key">
        <span><i className="key key--spent" />Spent {inr(budget.spent_inr)}</span>
        <span><i className="key key--held" />Waiting {inr(budget.pending_approval_inr)}</span>
      </div>
    </section>
  )
}
