import type { OrderStatus } from '../types'

const LABEL: Record<OrderStatus, string> = {
  PAID: 'Paid',
  PAYING: 'Paying',
  PENDING_APPROVAL: 'Needs your OK',
  BLOCKED: 'Blocked',
  REJECTED: 'Rejected',
  FAILED: 'Payment failed',
}

export const statusLabel = (s: OrderStatus) => LABEL[s] ?? s

export function Stamp({ status }: { status: OrderStatus }) {
  return (
    <div className={`stamp stamp--${status.toLowerCase()}`} role="status" aria-label={`Status: ${LABEL[status]}`}>
      {LABEL[status]}
    </div>
  )
}
