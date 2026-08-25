import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { buyerApi } from '../lib/api'
import type { ProductDetail } from '../types'
import { Blueprint } from './Blueprint'

export function StockRequestForm({ product }: { product: ProductDetail }) {
  const auth = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!auth.user) {
      auth.openSignIn()
      return
    }
    const form = event.currentTarget
    const data = new FormData(form)
    setSubmitting(true)
    setError('')
    try {
      const request = await buyerApi.createRequest({
        request_type: 'stock',
        product_id: product.id,
        quantity: Number(data.get('quantity')),
        target_price: data.get('target_price') ? Number(data.get('target_price')) : undefined,
        currency: product.currency || 'EUR',
        destination: String(data.get('destination')),
        notes: String(data.get('notes') || ''),
      }, auth.user.csrf_token)
      navigate(`/requests?created=${request.reference}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to submit this request.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-section request-section">
      <div>
        <p className="eyebrow">Buyer request</p>
        <h2>Ask about this stock</h2>
        <p>State the quantity, target price and destination. The trading desk will review the request against the current supplier offer.</p>
      </div>
      <Blueprint as="form" className="request-form" onSubmit={submit}>
        {!auth.user && <div className="auth-notice">Sign in with an approved buyer account to submit this request.</div>}
        <div className="form-grid">
          <label className="field"><span>Quantity wanted</span><input required min="1" name="quantity" type="number" inputMode="numeric" /></label>
          <label className="field"><span>Target price per unit ({product.currency || 'EUR'})</span><input min="0" step="0.01" name="target_price" type="number" inputMode="decimal" /></label>
          <label className="field form-span"><span>Destination port or city</span><input required name="destination" /></label>
          <label className="field form-span"><span>Notes</span><textarea name="notes" rows={4} placeholder="Packaging, size mix, labelling or delivery requirements" /></label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary" disabled={submitting}>{submitting ? 'Submitting…' : auth.user ? 'Submit demand request' : 'Sign in to continue'}</button>
      </Blueprint>
    </section>
  )
}
