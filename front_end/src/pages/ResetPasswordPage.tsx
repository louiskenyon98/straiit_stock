import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { Blueprint } from '../components/Blueprint'
import { buyerApi } from '../lib/api'

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get('password'))
    if (password !== String(data.get('confirm_password'))) { setError('Passwords do not match.'); return }
    setSubmitting(true); setError('')
    try { await buyerApi.resetPassword(token, password); setComplete(true) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to reset your password.') }
    finally { setSubmitting(false) }
  }

  return <section className="page-shell static-page recovery-page"><Blueprint>
    {complete ? <div className="application-success"><CheckCircle2 aria-hidden="true" /><p className="eyebrow">Password changed</p><h1>Your account is secure</h1><p>All previous sessions have been signed out. You can now sign in with your new password.</p><Link className="button button-primary" to="/requests">Continue to sign in</Link></div>
      : <form className="auth-form" onSubmit={submit}><p className="eyebrow">Account recovery</p><h1>Choose a new password</h1><p>The reset link is one-time use and expires after 30 minutes.</p>{!token && <p className="form-error" role="alert">The reset token is missing.</p>}<label className="field"><span>New password</span><input required minLength={12} name="password" type="password" autoComplete="new-password" /></label><label className="field"><span>Confirm password</span><input required minLength={12} name="confirm_password" type="password" autoComplete="new-password" /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="button button-primary button-wide" disabled={!token || submitting}>{submitting ? 'Resetting…' : 'Reset password'}</button></form>}
  </Blueprint></section>
}
