import { useState } from 'react'
import { api, inr, usd, when } from '../api'
import type { Order } from '../types'
import { Stamp } from './Stamp'

interface Props {
  order: Order
  fresh?: boolean
  onChange: (o: Order) => void
  onError: (msg: string) => void
}

export function OrderCard({ order, fresh, onChange, onError }: Props) {
  const [busy, setBusy] = useState<'approve' | 'reject' | 'refresh' | null>(null)
  const policyDecision = order.decisions.find((d) => d.decided_by === 'policy')
  const ownerDecision = order.decisions.find((d) => d.decided_by === 'owner')
  const rules = policyDecision?.rules_fired ?? []

  async function act(kind: 'approve' | 'reject' | 'refresh') {
    setBusy(kind)
    try {
      onChange(await api[kind](order.id))
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className={`po po--${order.status.toLowerCase()}${fresh ? ' po--fresh' : ''}`} aria-labelledby={`po-${order.id}`}>
      <header className="po__head">
        <div>
          <h3 id={`po-${order.id}`} className="po__title">
            PO {order.id} <span className="po__supplier">· {order.supplier.name}</span>
          </h3>
          <p className="po__meta">
            {when(order.created_at)}
            {!order.supplier.approved && <span className="tag tag--bad">Not an approved supplier</span>}
          </p>
        </div>
        <Stamp status={order.status} />
      </header>

      <p className="po__request">“{order.request_text}”</p>

      <table className="po__lines">
        <thead>
          <tr><th scope="col">Item</th><th scope="col" className="num">Qty</th><th scope="col" className="num">Rate</th><th scope="col" className="num">Amount</th></tr>
        </thead>
        <tbody>
          {order.lines.map((l) => (
            <tr key={l.item_id}>
              <td>{l.name}</td>
              <td className="num">{l.qty}</td>
              <td className="num">{inr(l.unit_price_inr)}</td>
              <td className="num">{inr(l.line_total_inr)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr><th scope="row" colSpan={3}>Total</th><td className="num total">{inr(order.total_inr)}</td></tr>
        </tfoot>
      </table>

      <div className="po__why">
        <h4>Why the agent chose this</h4>
        <p>{order.agent_reasoning || 'The agent gave no reason.'}</p>
      </div>

      <div className="po__rules">
        <h4>What the rules said</h4>
        {rules.length === 0 ? (
          <p className="rule rule--ok">Passed every rule, so it was paid without asking you.</p>
        ) : (
          <ul>
            {rules.map((r, i) => (
              <li key={i} className={`rule rule--${r.outcome === 'BLOCK' ? 'block' : 'hold'}`}>{r.message}</li>
            ))}
          </ul>
        )}
        {ownerDecision && (
          <p className="rule rule--owner">
            You {ownerDecision.outcome === 'APPROVE' ? 'approved' : 'rejected'} this on {when(ownerDecision.at)}.
          </p>
        )}
      </div>

      {order.status === 'PENDING_APPROVAL' && (
        <div className="po__actions">
          <button className="btn btn--primary" disabled={busy !== null} onClick={() => act('approve')}>
            {busy === 'approve' ? 'Paying…' : `Approve and pay ${inr(order.total_inr)}`}
          </button>
          <button className="btn btn--quiet" disabled={busy !== null} onClick={() => act('reject')}>
            {busy === 'reject' ? 'Rejecting…' : 'Reject'}
          </button>
        </div>
      )}

      {order.payment && (
        <footer className="po__pay">
          <span>
            PayPal payout {usd(order.payment.amount_usd)} to {order.payment.receiver_email}
          </span>
          <span className="po__batch">
            {order.payment.paypal_batch_id ? `Batch ${order.payment.paypal_batch_id}` : 'No batch'} · {order.payment.status}
          </span>
          {order.status === 'PAYING' && (
            <button className="btn btn--quiet btn--small" disabled={busy !== null} onClick={() => act('refresh')}>
              {busy === 'refresh' ? 'Checking…' : 'Check payment status'}
            </button>
          )}
        </footer>
      )}
    </article>
  )
}
