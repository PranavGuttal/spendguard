import { AgGridReact } from 'ag-grid-react'
import type { ColDef } from 'ag-grid-community'
import { useMemo } from 'react'
import { inr, usd, when } from '../api'
import { AskBox } from '../components/AskBox'
import { statusLabel } from '../components/Stamp'
import { gridTheme } from '../gridTheme'
import type { Order } from '../types'

interface Row {
  id: number; created: string; supplier: string; items: string; total: number; status: string; statusKey: string; payout: string
}

export function OrdersPage({ orders, onError }: { orders: Order[]; onError: (m: string, status?: number) => void }) {
  const rows: Row[] = useMemo(() => orders.map((o) => ({
    id: o.id,
    created: when(o.created_at),
    supplier: o.supplier.name,
    items: o.lines.map((l) => `${l.qty} × ${l.name}`).join(', '),
    total: o.total_inr,
    status: statusLabel(o.status),
    statusKey: o.status.toLowerCase(),
    payout: o.payment ? `${usd(o.payment.amount_usd)} · ${o.payment.status}` : '',
  })), [orders])

  const cols: ColDef<Row>[] = useMemo(() => [
    { field: 'id', headerName: 'PO', width: 76, sort: 'desc' },
    { field: 'created', headerName: 'When', width: 148 },
    { field: 'supplier', headerName: 'Supplier', flex: 1, minWidth: 170, filter: true, tooltipField: 'supplier' },
    { field: 'items', headerName: 'Items', flex: 1.4, minWidth: 200, tooltipField: 'items' },
    { field: 'total', headerName: 'Total', width: 112, type: 'rightAligned', valueFormatter: (p) => inr(p.value ?? 0) },
    { field: 'status', headerName: 'Status', width: 160, filter: true,
      cellRenderer: (p: { value: string; data?: Row }) => <span className={`pill pill--${p.data?.statusKey}`}>{p.value}</span> },
    { field: 'payout', headerName: 'PayPal payout', width: 168 },
  ], [])

  return (
    <div className="page page--wide">
      <h2 className="page-title">All purchase orders</h2>
      <p className="page-lead">Every order the agent proposed, with what happened to it. Sort or filter any column.</p>
      <AskBox onError={onError} />
      <div className="grid-wrap" style={{ height: Math.min(560, 56 + Math.max(rows.length, 3) * 44) }}>
        <AgGridReact<Row> theme={gridTheme} rowData={rows} columnDefs={cols} rowHeight={44}
          overlayNoRowsTemplate="No purchase orders yet." />
      </div>
    </div>
  )
}
