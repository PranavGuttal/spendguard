import { AgGridReact } from 'ag-grid-react'
import type { ColDef } from 'ag-grid-community'
import { useEffect, useMemo, useState } from 'react'
import { api, when } from '../api'
import { gridTheme } from '../gridTheme'
import type { AuditRow } from '../types'

const OUTCOME: Record<string, string> = { APPROVE: 'Approved', NEEDS_APPROVAL: 'Held for owner', BLOCK: 'Blocked', REJECT: 'Rejected' }

export function AuditPage({ version, onError }: { version: number; onError: (m: string) => void }) {
  const [rows, setRows] = useState<AuditRow[]>([])
  useEffect(() => { api.audit().then(setRows).catch((e) => onError(e.message)) }, [version, onError])

  const data = useMemo(() => rows.map((r) => ({
    at: when(r.at),
    po: r.order_id,
    by: r.decided_by === 'policy' ? 'Rules' : 'Owner',
    outcome: OUTCOME[r.outcome] ?? r.outcome,
    key: r.outcome.toLowerCase(),
    reasons: r.rules_fired.length ? r.rules_fired.map((x) => x.message).join(' ') : (r.note || (r.decided_by === 'policy' ? 'Passed every rule.' : r.outcome === 'APPROVE' ? 'Approved by you, so PayPal paid it.' : 'Rejected by you, so nothing was paid.')),
  })), [rows])

  const cols: ColDef<(typeof data)[number]>[] = useMemo(() => [
    { field: 'at', headerName: 'When', width: 140 },
    { field: 'po', headerName: 'PO', width: 80 },
    { field: 'by', headerName: 'Decided by', width: 136, filter: true },
    { field: 'outcome', headerName: 'Decision', width: 150, filter: true,
      cellRenderer: (p: { value: string; data?: { key: string } }) => <span className={`pill pill--d-${p.data?.key}`}>{p.value}</span> },
    { field: 'reasons', headerName: 'Reasons', flex: 1, minWidth: 260, wrapText: true, autoHeight: true,
      cellStyle: { lineHeight: '1.45', paddingTop: '10px', paddingBottom: '10px' } },
  ], [])

  return (
    <div className="page page--wide">
      <h2 className="page-title">Audit log</h2>
      <p className="page-lead">Every decision, by the rules or by you, with the exact reasons. Nothing is paid without a line here.</p>
      <div className="grid-wrap" style={{ height: 520 }}>
        <AgGridReact theme={gridTheme} rowData={data} columnDefs={cols} overlayNoRowsTemplate="No decisions yet." />
      </div>
    </div>
  )
}
