import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { CheckCircle2, RefreshCw, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth/useAuth'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { StatusTag } from '../components/StatusTag'
import { adminApi } from '../lib/api'
import { formatMoney, formatNumber } from '../lib/format'
import type { AdminRequest } from '../types'

const statuses = ['new', 'reviewing', 'sourcing', 'quoted', 'accepted', 'closed', 'rejected']

export function AdminPage() {
  const { user, loading, logout, openOperatorSignIn } = useAuth()
  const query = useQuery({ queryKey: ['admin-overview'], queryFn: ({ signal }) => adminApi.overview(signal), enabled: user?.role === 'operator' })
  const [actionError, setActionError] = useState('')
  const [working, setWorking] = useState('')
  if (loading) return <LoadingState label="Checking operator access" />
  if (!user) return <section className="page-shell buyer-guest"><Blueprint><p className="eyebrow">Operator access</p><h1>Sign in to the trading desk.</h1><p>This area is restricted to operator accounts.</p><div className="button-row"><button className="button button-primary" onClick={openOperatorSignIn}>Sign in as operator</button></div></Blueprint></section>
  if (user.role !== 'operator') return <section className="page-shell buyer-guest"><Blueprint><p className="eyebrow">Operator access</p><h1>Switch to an operator account.</h1><p>You are currently signed in as {user.email}, which is a buyer account.</p><div className="button-row"><button className="button button-primary" onClick={() => void logout().then(openOperatorSignIn)}>Sign out and switch account</button></div></Blueprint></section>

  async function perform(key: string, action: () => Promise<unknown>) {
    setWorking(key); setActionError('')
    try { await action(); await query.refetch() }
    catch (caught) { setActionError(caught instanceof Error ? caught.message : 'The operator action failed.') }
    finally { setWorking('') }
  }

  if (query.isLoading) return <LoadingState label="Loading trading desk" />
  if (query.isError || !query.data) return <ErrorState message={query.error instanceof Error ? query.error.message : 'Unable to load the trading desk.'} retry={() => void query.refetch()} />
  const pending = query.data.applications.filter((item) => item.status === 'pending')
  return <section className="page-shell admin-page">
    <div className="page-heading"><div><p className="eyebrow">Internal operations</p><h1>Trading desk</h1></div><button className="button button-secondary" onClick={() => void query.refetch()}><RefreshCw aria-hidden="true" /> Refresh</button></div>
    {actionError && <p className="form-error" role="alert">{actionError}</p>}
    <div className="admin-metrics"><Blueprint><span>Pending applications</span><strong>{pending.length}</strong></Blueprint><Blueprint><span>Open demand</span><strong>{query.data.requests.filter((item) => !['closed', 'rejected'].includes(item.status)).length}</strong></Blueprint><Blueprint><span>Active reservations</span><strong>{query.data.reservations.filter((item) => ['held', 'confirmed'].includes(item.status)).length}</strong></Blueprint><Blueprint><span>Email queue</span><strong>{query.data.emails.filter((item) => item.status !== 'sent').length}</strong></Blueprint></div>

    <section className="admin-section"><p className="eyebrow">Access control</p><h2>Buyer applications</h2>{pending.length ? <div className="admin-card-grid">{pending.map((item) => <Blueprint className="admin-card" key={item.id}><ShieldCheck aria-hidden="true" /><h3>{item.company_name}</h3><p>{item.email}<br />{item.country}{item.registration_number ? ` · ${item.registration_number}` : ''}</p><div className="button-row"><button className="button button-primary" disabled={!!working} onClick={() => void perform(`approve-${item.id}`, () => adminApi.approveApplication(item.id, user.csrf_token))}>{working === `approve-${item.id}` ? 'Approving…' : 'Approve'}</button><button className="button button-secondary" disabled={!!working} onClick={() => void perform(`reject-${item.id}`, () => adminApi.rejectApplication(item.id, 'Application declined by trading desk', user.csrf_token))}>Reject</button></div></Blueprint>)}</div> : <p className="admin-empty"><CheckCircle2 aria-hidden="true" /> No applications awaiting review.</p>}</section>

    <section className="admin-section"><p className="eyebrow">Commercial workflow</p><h2>Demand requests</h2><div className="admin-request-list">{query.data.requests.map((request) => <RequestEditor key={request.id} request={request} csrf={user.csrf_token} working={working} perform={perform} />)}</div></section>

    <section className="admin-section"><p className="eyebrow">Allocated inventory</p><h2>Reservations</h2><Blueprint className="table-frame"><div className="table-scroll"><table><thead><tr><th>Request</th><th>Organisation</th><th>Product</th><th>Quantity</th><th>Reservation</th><th>Deadline</th><th>Action</th></tr></thead><tbody>{query.data.reservations.map((item) => <tr key={item.id}><td>{item.reference}</td><td>{item.organization_name}</td><td>#{item.product_id}</td><td>{formatNumber(item.quantity)}</td><td><StatusTag status={item.status.toUpperCase()} label={item.status} /></td><td>{item.expires_at ? new Date(item.expires_at).toLocaleDateString('en-GB') : 'Firm'}</td><td><div className="inline-actions">{item.status === 'held' && <button className="text-button" disabled={!!working} onClick={() => void perform(`confirm-${item.id}`, () => adminApi.confirmReservation(item.id, 'Offline payment confirmed', user.csrf_token))}>Confirm payment</button>}{['held', 'confirmed'].includes(item.status) && <button className="text-button" disabled={!!working} onClick={() => void perform(`release-${item.id}`, () => adminApi.releaseReservation(item.id, 'Released by trading desk', user.csrf_token))}>Release</button>}</div></td></tr>)}</tbody></table></div></Blueprint></section>

    <section className="admin-section"><p className="eyebrow">Delivery audit</p><h2>Recent email</h2><Blueprint className="table-frame"><div className="table-scroll"><table><thead><tr><th>Recipient</th><th>Subject</th><th>Status</th><th>Attempts</th></tr></thead><tbody>{query.data.emails.map((item) => <tr key={item.id}><td>{item.to_email}</td><td>{item.subject}</td><td><StatusTag status={item.status.toUpperCase()} label={item.status} /></td><td>{item.attempts}{item.last_error ? ` · ${item.last_error}` : ''}</td></tr>)}</tbody></table></div></Blueprint></section>
  </section>
}

function RequestEditor({ request, csrf, working, perform }: { request: AdminRequest; csrf: string; working: string; perform: (key: string, action: () => Promise<unknown>) => Promise<void> }) {
  function statusSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); void perform(`status-${request.id}`, () => adminApi.setRequestStatus(request.reference, String(data.get('status')), String(data.get('note')), csrf)) }
  function quoteSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); void perform(`quote-${request.id}`, () => adminApi.issueQuote(request.reference, { amount: Number(data.get('amount')), currency: String(data.get('currency')), valid_until: String(data.get('valid_until')), terms: String(data.get('terms')) }, csrf)) }
  return <Blueprint className="admin-request"><div><p className="eyebrow">{request.reference} · {request.organization_name}</p><h3>{request.product_id ? `Catalogue product #${request.product_id}` : [request.brand, request.category].filter(Boolean).join(' · ')}</h3><p>{formatNumber(request.quantity)} units to {request.destination} · {request.created_by_email}</p>{request.target_price != null && <small>Buyer target: {formatMoney(request.target_price, request.currency)}</small>}{request.product_id && request.status === 'quoted' && <button className="button button-primary admin-hold" disabled={!!working} onClick={() => void perform(`hold-${request.id}`, () => adminApi.holdStock(request.reference, csrf))}>{working === `hold-${request.id}` ? 'Holding…' : 'Place stock on hold'}</button>}</div><form onSubmit={statusSubmit}><label className="field"><span>Status</span><select name="status" defaultValue={request.status}>{statuses.map((status) => <option key={status}>{status}</option>)}</select></label><label className="field"><span>Buyer note</span><input name="note" placeholder="Optional update" /></label><button className="button button-secondary" disabled={!!working}>{working === `status-${request.id}` ? 'Saving…' : 'Update'}</button></form><form onSubmit={quoteSubmit}><label className="field"><span>Total quote</span><input name="amount" min="0.01" step="0.01" type="number" required /></label><label className="field"><span>Currency</span><input name="currency" maxLength={3} defaultValue={request.currency ?? 'EUR'} required /></label><label className="field"><span>Payment deadline</span><input name="valid_until" type="date" required /></label><label className="field"><span>Offline payment terms</span><input name="terms" placeholder="Bank transfer details / invoice terms" /></label><button className="button button-primary" disabled={!!working}>{working === `quote-${request.id}` ? 'Issuing…' : 'Issue quote'}</button></form></Blueprint>
}
