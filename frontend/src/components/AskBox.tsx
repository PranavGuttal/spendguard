import { useState } from 'react'
import { api, ApiError } from '../api'

const SUGGESTIONS = [
  'How much have we spent this month, and with which suppliers?',
  'What is waiting for my approval?',
  'What did PayPal record for us in the last 7 days?',
]

const TOOL_LABEL: Record<string, string> = {
  spend_summary: 'monthly spend summary',
  list_orders: 'purchase orders',
  paypal_transactions: 'PayPal transactions',
}

export function AskBox({ onError }: { onError: (m: string, status?: number) => void }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState<{ text: string; used: string[] } | null>(null)

  async function ask(question: string) {
    const t = question.trim()
    if (t.length < 3 || busy) return
    setBusy(true)
    setAnswer(null)
    try {
      const r = await api.ask(t)
      setAnswer({ text: r.answer, used: [...new Set(r.tools_used)] })
    } catch (e) {
      onError((e as Error).message, e instanceof ApiError ? e.status : undefined)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ask" aria-labelledby="ask-title">
      <h3 id="ask-title" className="ask__title">Ask about spending</h3>
      <form className="ask__row" onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <label htmlFor="ask-q" className="sr-only">Question about spending</label>
        <input id="ask-q" className="ask__input" value={q} maxLength={300} onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. How much did we spend on carbide inserts this month?" />
        <button className="btn btn--primary" disabled={busy || q.trim().length < 3}>{busy ? 'Looking…' : 'Ask'}</button>
      </form>
      <div className="examples">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="chip" disabled={busy} onClick={() => { setQ(s); ask(s) }}>{s}</button>
        ))}
      </div>
      {answer && (
        <div className="ask__answer" role="status">
          <p>{answer.text}</p>
          {answer.used.length > 0 && (
            <p className="ask__used">Checked: {answer.used.map((u) => TOOL_LABEL[u] ?? u).join(', ')}. Read-only: asking never buys or pays.</p>
          )}
        </div>
      )}
    </section>
  )
}
