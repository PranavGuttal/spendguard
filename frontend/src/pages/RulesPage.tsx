import { useEffect, useState } from 'react'
import { api, inr } from '../api'
import type { Catalogue, Policy } from '../types'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const monthName = (key: string) => `${MONTHS[Number(key.slice(5, 7)) - 1] ?? key.slice(5, 7)} ${key.slice(0, 4)}`

function budgetDetail(p: Policy): string {
  const base = `${inr(p.monthly_budget_inr)} a month`
  const raised = Object.entries(p.budget_overrides ?? {})
  if (raised.length === 0) return base
  return `${base}. Raised for one month: ${raised.map(([m, v]) => `${monthName(m)} ${inr(v)}`).join(', ')}.`
}

export function RulesPage({ onError }: { onError: (m: string) => void }) {
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [cat, setCat] = useState<Catalogue | null>(null)
  useEffect(() => {
    api.policy().then(setPolicy).catch((e) => onError(e.message))
    api.catalogue().then(setCat).catch((e) => onError(e.message))
  }, [onError])
  if (!policy) return <div className="page"><p className="empty">Loading rules…</p></div>

  const rules: [string, string, 'block' | 'hold'][] = [
    ['Approved suppliers only', `${policy.approved_vendors.length} suppliers are on the list.`, 'block'],
    ['Allowed categories only', policy.allowed_categories.join(', '), 'block'],
    ['Stay inside the monthly budget', budgetDetail(policy), 'block'],
    ['Hard cap per order', `Nothing over ${inr(policy.hard_cap_inr)} is ever paid.`, 'block'],
    ['Auto-approve limit', `Orders over ${inr(policy.auto_approve_limit_inr)} wait for you.`, 'hold'],
    ['Price check', `A price more than ${policy.price_tolerance_pct}% above usual waits for you.`, 'hold'],
    ['No duplicates', `The same order to the same supplier within ${policy.duplicate_window_hours} hours waits for you.`, 'hold'],
    ['Daily limit', `More than ${policy.max_orders_per_day} orders in a day waits for you.`, 'hold'],
    ['Agent must explain itself', 'An order with no reason waits for you.', 'hold'],
  ]

  return (
    <div className="page">
      <h2 className="page-title">Your rules</h2>
      <p className="page-lead">
        The AI only proposes. These rules are plain code, so no prompt can talk them out of a decision.
        Edit them in <code>backend/policy.yaml</code>.
      </p>
      <ol className="rulebook">
        {rules.map(([name, detail, kind]) => (
          <li key={name} className={`rulebook__item rulebook__item--${kind}`}>
            <span className="rulebook__name">{name}</span>
            <span className="rulebook__detail">{detail}</span>
            <span className={`rulebook__effect rulebook__effect--${kind}`}>{kind === 'block' ? 'Blocks' : 'Asks you'}</span>
          </li>
        ))}
      </ol>
      {cat && (
        <>
          <h2 className="section-title">Suppliers</h2>
          <ul className="suppliers">
            {cat.suppliers.map((s) => (
              <li key={s.id}>
                <strong>{s.name}</strong> <span className="muted">{s.city}</span>
                {s.approved ? <span className="tag tag--ok">Approved</span> : <span className="tag tag--bad">Not approved</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="muted small">Payments run in PayPal's sandbox at a fixed demo rate of ₹{policy.inr_per_usd} per US dollar.</p>
    </div>
  )
}
