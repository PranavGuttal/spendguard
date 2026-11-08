import { useState } from 'react'
import { api, ApiError } from '../api'
import { OrderCard } from '../components/OrderCard'
import type { Order } from '../types'

const EXAMPLES = [
  '20 HSS tool bits for the lathe',
  '10 boxes of CNMG carbide inserts for the big shaft job',
  'Buy a 15 inch laptop for the office',
]

interface Props {
  orders: Order[]
  onOrder: (o: Order) => void
  onError: (msg: string, status?: number) => void
}

export function PurchasePage({ orders, onOrder, onError }: Props) {
  const [text, setText] = useState('')
  const [working, setWorking] = useState(false)
  const [freshId, setFreshId] = useState<number | null>(null)
  const [agentNote, setAgentNote] = useState<string | null>(null)

  async function submit(value: string) {
    const t = value.trim()
    if (t.length < 3 || working) return
    setWorking(true)
    setAgentNote(null)
    try {
      const res = await api.request(t)
      if (res.order) {
        onOrder(res.order)
        setFreshId(res.order.id)
        setText('')
      } else {
        setAgentNote(res.agent_message)
      }
    } catch (e) {
      onError((e as Error).message, e instanceof ApiError ? e.status : undefined)
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="page">
      <section className="slip" aria-labelledby="slip-title">
        <h2 id="slip-title" className="slip__title">What does the shop need?</h2>
        <p className="slip__hint">
          Write it the way you would tell your supplier. The agent picks items from the catalogue,
          then your rules decide whether PayPal pays now, waits for you, or never pays.
        </p>
        <form onSubmit={(e) => { e.preventDefault(); submit(text) }}>
          <label htmlFor="need" className="sr-only">Purchase request</label>
          <textarea id="need" className="slip__input" rows={3} maxLength={500} value={text}
            placeholder="e.g. 20 HSS tool bits for the lathe by Friday"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(text) }} />
          <div className="slip__row">
            <div className="examples" aria-label="Example requests">
              {EXAMPLES.map((ex) => (
                <button type="button" key={ex} className="chip" disabled={working} onClick={() => { setText(ex); submit(ex) }}>
                  {ex}
                </button>
              ))}
            </div>
            <button type="submit" className="btn btn--primary" disabled={working || text.trim().length < 3}>
              {working ? 'Agent is working…' : 'Send to agent'}
            </button>
          </div>
        </form>
        {working && <p className="working" role="status">Searching the catalogue and checking your rules…</p>}
        {agentNote && (
          <p className="agent-note" role="status"><strong>No order placed.</strong> {agentNote}</p>
        )}
      </section>

      <section aria-labelledby="recent-title">
        <h2 id="recent-title" className="section-title">Recent purchase orders</h2>
        {orders.length === 0 ? (
          <p className="empty">Nothing ordered yet. Try one of the example requests above.</p>
        ) : (
          <div className="po-list">
            {orders.slice(0, 8).map((o) => (
              <OrderCard key={o.id} order={o} fresh={o.id === freshId} onChange={onOrder} onError={onError} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
