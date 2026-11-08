import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, savePassword } from './api'
import { BudgetBar } from './components/BudgetBar'
import { ApprovalsPage } from './pages/ApprovalsPage'
import { AuditPage } from './pages/AuditPage'
import { OrdersPage } from './pages/OrdersPage'
import { PurchasePage } from './pages/PurchasePage'
import { RulesPage } from './pages/RulesPage'
import type { Budget, Order } from './types'

type View = 'buy' | 'approvals' | 'orders' | 'audit' | 'rules'

export default function App() {
  const [view, setView] = useState<View>('buy')
  const [orders, setOrders] = useState<Order[]>([])
  const [budget, setBudget] = useState<Budget | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needPassword, setNeedPassword] = useState(false)
  const [version, setVersion] = useState(0)

  const onError = useCallback((msg: string, status?: number) => {
    if (status === 401) setNeedPassword(true)
    setError(msg)
  }, [])

  const reload = useCallback(async () => {
    try {
      const [o, b] = await Promise.all([api.orders(), api.budget()])
      setOrders(o)
      setBudget(b)
      setVersion((v) => v + 1)
    } catch (e) {
      onError((e as Error).message, e instanceof ApiError ? e.status : undefined)
    }
  }, [onError])

  useEffect(() => { reload() }, [reload])

  const onOrder = useCallback((o: Order) => {
    setOrders((prev) => [o, ...prev.filter((p) => p.id !== o.id)].sort((a, b) => b.id - a.id))
    setError(null)
    api.budget().then(setBudget).catch(() => undefined)
    setVersion((v) => v + 1)
  }, [])

  const pending = orders.filter((o) => o.status === 'PENDING_APPROVAL').length
  const nav: [View, string][] = [
    ['buy', 'Buy'],
    ['approvals', 'Approvals'],
    ['orders', 'Orders'],
    ['audit', 'Audit log'],
    ['rules', 'Rules'],
  ]

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="currentColor" />
            <path d="M9 16.5l4.5 4.5L23 11" stroke="#fff" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <h1 className="brand__name">SpendGuard</h1>
            <p className="brand__tag">The AI proposes. Your rules decide.</p>
          </div>
        </div>
        <nav aria-label="Sections">
          <ul className="nav">
            {nav.map(([key, label]) => (
              <li key={key}>
                <button className={`nav__item${view === key ? ' nav__item--on' : ''}`} aria-current={view === key ? 'page' : undefined}
                  onClick={() => { setView(key); if (key !== 'buy') reload() }}>
                  {label}
                  {key === 'approvals' && pending > 0 && <span className="badge" aria-label={`${pending} waiting`}>{pending}</span>}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <BudgetBar budget={budget} />
        <p className="rail__foot">Payments go through the PayPal sandbox. No real money moves.</p>
      </aside>

      <main className="main" id="main">
        {error && (
          <div className="alert" role="alert">
            <span>{error}</span>
            <button className="alert__close" onClick={() => setError(null)} aria-label="Dismiss message">×</button>
          </div>
        )}
        {needPassword && (
          <form className="pw" onSubmit={(e) => {
            e.preventDefault()
            const value = new FormData(e.currentTarget).get('pw')?.toString() ?? ''
            savePassword(value); setNeedPassword(false); setError(null); reload()
          }}>
            <label htmlFor="pw">This demo is protected. Enter the demo password from the project README.</label>
            <div className="pw__row">
              <input id="pw" name="pw" type="password" autoComplete="off" required />
              <button className="btn btn--primary" type="submit">Unlock demo</button>
            </div>
          </form>
        )}
        {view === 'buy' && <PurchasePage orders={orders} onOrder={onOrder} onError={onError} />}
        {view === 'approvals' && <ApprovalsPage orders={orders} onOrder={onOrder} onError={onError} />}
        {view === 'orders' && <OrdersPage orders={orders} onError={onError} />}
        {view === 'audit' && <AuditPage version={version} onError={onError} />}
        {view === 'rules' && <RulesPage onError={onError} />}
      </main>
    </div>
  )
}
