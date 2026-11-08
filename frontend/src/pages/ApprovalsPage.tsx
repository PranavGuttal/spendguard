import { OrderCard } from '../components/OrderCard'
import type { Order } from '../types'

export function ApprovalsPage({ orders, onOrder, onError }: {
  orders: Order[]; onOrder: (o: Order) => void; onError: (m: string, status?: number) => void
}) {
  const pending = orders.filter((o) => o.status === 'PENDING_APPROVAL')
  return (
    <div className="page">
      <h2 className="page-title">Waiting for your OK</h2>
      <p className="page-lead">
        These orders broke a rule that needs a person, such as going over the auto-approve limit.
        Nothing is paid until you approve.
      </p>
      {pending.length === 0 ? (
        <p className="empty">No orders are waiting. Anything over your auto-approve limit will appear here.</p>
      ) : (
        <div className="po-list">
          {pending.map((o) => <OrderCard key={o.id} order={o} onChange={onOrder} onError={onError} />)}
        </div>
      )}
    </div>
  )
}
