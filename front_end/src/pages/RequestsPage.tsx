import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { StatusTag } from '../components/StatusTag'
import { buyerApi, catalogueApi } from '../lib/api'
import { formatMoney, formatNumber, productTitle } from '../lib/format'
import type { DemandRequest } from '../types'

export function RequestsPage() {
  const auth = useAuth()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<'mine' | 'wanted'>(params.get('new') === 'wanted' ? 'wanted' : 'mine')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const requestsQuery = useQuery({
    queryKey: ['buyer-requests', auth.user?.organization.id],
    queryFn: ({ signal }) => buyerApi.requests(signal),
    enabled: Boolean(auth.user),
  })
  const facetsQuery = useQuery({
    queryKey: ['catalogue-facets'],
    queryFn: ({ signal }) => catalogueApi.facets(signal),
    enabled: Boolean(auth.user),
  })

  if (auth.loading) return <div className="page-shell"><LoadingState label="Loading buyer account" /></div>
  if (!auth.user) {
    return (
      <div className="page-shell buyer-guest">
        <Blueprint>
          <p className="eyebrow">Buyer area</p>
          <h1>Sign in to manage requests.</h1>
          <p>Approved organisations can submit stock enquiries, post standing demand, and track request status from this page.</p>
          <div className="button-row"><button className="button button-primary" onClick={auth.openSignIn}>Sign in</button><button className="button button-secondary" onClick={auth.openApply}>Request access</button></div>
        </Blueprint>
      </div>
    )
  }
  const user = auth.user

  async function submitWanted(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setSubmitting(true)
    setError('')
    try {
      const request = await buyerApi.createRequest({
        request_type: 'wanted',
        brand: String(data.get('brand') || ''),
        category: String(data.get('category') || ''),
        quantity: Number(data.get('quantity')),
        target_price: data.get('target_price') ? Number(data.get('target_price')) : undefined,
        currency: String(data.get('currency') || 'EUR'),
        destination: String(data.get('destination')),
        notes: String(data.get('notes') || ''),
      }, user.csrf_token)
      form.reset()
      await queryClient.invalidateQueries({ queryKey: ['buyer-requests'] })
      setTab('mine')
      setParams({ created: request.reference })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to submit the request.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-shell requests-page">
      <div className="page-heading buyer-heading">
        <div><p className="eyebrow">{user.organization.name}</p><h1>Demand requests</h1></div>
        <div className="request-tabs" role="tablist"><button role="tab" aria-selected={tab === 'mine'} onClick={() => setTab('mine')}>My requests ({requestsQuery.data?.items.length ?? 0})</button><button role="tab" aria-selected={tab === 'wanted'} onClick={() => setTab('wanted')}><Plus aria-hidden="true" /> Request unlisted stock</button></div>
      </div>
      {params.get('created') && <div className="success-banner" role="status"><CheckCircle2 aria-hidden="true" /><span><strong>{params.get('created')}</strong> was submitted to the trading desk.</span><button aria-label="Dismiss" onClick={() => setParams({})}>×</button></div>}

      {tab === 'mine' ? (
        <>
          {requestsQuery.isLoading && <LoadingState label="Loading requests" />}
          {requestsQuery.isError && <ErrorState message={requestsQuery.error.message} retry={() => requestsQuery.refetch()} />}
          {requestsQuery.data?.items.length ? <RequestTable requests={requestsQuery.data.items} /> : requestsQuery.isSuccess ? <Blueprint className="empty-state"><h2>No demand requests yet</h2><p>Open a catalogue product or post a standing request for stock that is not listed.</p><button className="button button-primary" onClick={() => setTab('wanted')}>Post wanted stock</button></Blueprint> : null}
        </>
      ) : (
        <div className="wanted-grid">
          <Blueprint as="form" className="request-form wanted-form" onSubmit={submitWanted}>
            <p className="eyebrow">Standing demand</p><h2>Tell us what you are looking for</h2><p>Matching stock can be reviewed against this request when it enters the catalogue.</p>
            <div className="form-grid">
              <label className="field"><span>Brand or brand tier</span><input name="brand" placeholder="e.g. Gucci or European premium" /></label>
              <label className="field"><span>Category</span><select name="category" defaultValue=""><option value="">Any category</option>{facetsQuery.data?.categories.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}</select></label>
              <label className="field"><span>Quantity wanted</span><input required min="1" name="quantity" type="number" inputMode="numeric" /></label>
              <label className="field"><span>Target price per unit</span><span className="price-input"><select name="currency" defaultValue="EUR"><option>EUR</option><option>GBP</option></select><input min="0" step="0.01" name="target_price" type="number" inputMode="decimal" /></span></label>
              <label className="field form-span"><span>Destination port or city</span><input required name="destination" /></label>
              <label className="field form-span"><span>Detail</span><textarea rows={5} name="notes" placeholder="Grades, packaging, size curve, labelling or delivery window" /></label>
            </div>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button-primary" disabled={submitting}>{submitting ? 'Submitting…' : 'Submit demand request'}</button>
          </Blueprint>
          <div className="wanted-aside"><p className="eyebrow">Account</p><h2>{user.organization.name}</h2><dl><div><dt>Work email</dt><dd>{user.email}</dd></div><div><dt>Country</dt><dd>{user.organization.country}</dd></div>{user.organization.registration_number && <div><dt>Registration</dt><dd>{user.organization.registration_number}</dd></div>}</dl><p>Requests are visible to every authorised user in the same organisation.</p></div>
        </div>
      )}
    </div>
  )
}

function RequestTable({ requests }: { requests: DemandRequest[] }) {
  return (
    <Blueprint className="table-frame request-table"><div className="table-scroll" role="region" aria-label="Demand requests" tabIndex={0}><table><thead><tr><th>Reference</th><th>Type</th><th>Item</th><th>Quantity</th><th>Target</th><th>Destination</th><th>Raised</th><th>Status</th></tr></thead><tbody>{requests.map((request) => <tr key={request.id}><td className="request-reference">{request.reference}</td><td>{request.request_type === 'stock' ? 'Stock' : 'Wanted'}</td><td>{request.product ? <Link to={`/stock/${request.product.id}`}>{[request.product.brand, productTitle(request.product)].filter(Boolean).join(' · ')}</Link> : [request.brand, request.category].filter(Boolean).join(' · ')}</td><td>{formatNumber(request.quantity)}</td><td>{request.target_price == null ? 'Open' : formatMoney(request.target_price, request.currency)}</td><td>{request.destination}</td><td>{new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' }).format(new Date(request.created_at))}</td><td><StatusTag status={request.status.toUpperCase()} label={`${request.status.charAt(0).toUpperCase()}${request.status.slice(1).replace('_', ' ')}`} />{request.quote && <small className="quote-label">Quote {formatMoney(request.quote.amount, request.quote.currency)}</small>}</td></tr>)}</tbody></table></div></Blueprint>
  )
}
