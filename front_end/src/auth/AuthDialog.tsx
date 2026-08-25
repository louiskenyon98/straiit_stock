import { useEffect, useRef, useState, type FormEvent } from 'react'
import { CheckCircle2, X } from 'lucide-react'
import { buyerApi } from '../lib/api'
import type { AuthMode } from './auth-context'
import { useAuth } from './useAuth'

type DialogMode = AuthMode | 'forgot'

export function AuthDialog() {
  const auth = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [mode, setMode] = useState<DialogMode>('signin')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState<{ kind: 'application' | 'reset'; email: string; id?: number } | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (auth.dialogMode) {
      setMode(auth.dialogMode); setError(''); setMessage(null)
      if (!dialog.open) dialog.showModal()
    } else if (dialog.open) dialog.close()
  }, [auth.dialogMode])

  function switchMode(next: DialogMode) { setMode(next); setError(''); setMessage(null) }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setSubmitting(true); setError('')
    try {
      const login = mode === 'operator' ? auth.operatorLogin : auth.login
      await login(String(data.get('email')), String(data.get('password')))
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to sign in.') }
    finally { setSubmitting(false) }
  }

  async function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); const password = String(data.get('password'))
    if (password !== String(data.get('confirm_password'))) { setError('Passwords do not match.'); return }
    setSubmitting(true); setError('')
    try {
      const application = await auth.apply({ company: String(data.get('company')), registration_number: String(data.get('registration_number')), country: String(data.get('country')), email: String(data.get('email')), password })
      setMessage({ kind: 'application', ...application })
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to submit the application.') }
    finally { setSubmitting(false) }
  }

  async function forgotPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); const email = String(data.get('email')); setSubmitting(true); setError('')
    try { await buyerApi.requestPasswordReset(email); setMessage({ kind: 'reset', email }) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to request a reset link.') }
    finally { setSubmitting(false) }
  }

  return (
    <dialog ref={dialogRef} className="auth-dialog" onCancel={auth.closeDialog} onClose={auth.closeDialog}>
      <button className="dialog-close" type="button" aria-label="Close" onClick={auth.closeDialog}><X aria-hidden="true" /></button>
      <div className="auth-tabs" role="tablist" aria-label="Portal account">
        <button type="button" role="tab" aria-selected={mode === 'signin' || mode === 'operator' || mode === 'forgot'} onClick={() => switchMode(mode === 'operator' ? 'operator' : 'signin')}>{mode === 'operator' ? 'Operator sign in' : 'Sign in'}</button>
        <button type="button" role="tab" aria-selected={mode === 'apply'} onClick={() => switchMode('apply')}>Apply for an account</button>
      </div>
      {message ? (
        <div className="application-success" role="status">
          <CheckCircle2 aria-hidden="true" /><p className="eyebrow">{message.kind === 'reset' ? 'Check your email' : 'Application received'}</p>
          <h2>{message.kind === 'reset' ? 'Reset link requested' : 'Verification is pending'}</h2>
          <p>{message.kind === 'reset' ? `If an active account exists for ${message.email}, a one-time reset link has been queued for delivery.` : `Application #${message.id} for ${message.email} is waiting for approval. You can sign in after the trading desk verifies the company.`}</p>
          <button className="button button-secondary" onClick={message.kind === 'reset' ? () => switchMode('signin') : auth.closeDialog}>{message.kind === 'reset' ? 'Back to sign in' : 'Close'}</button>
        </div>
      ) : mode === 'signin' || mode === 'operator' ? (
        <form className="auth-form" onSubmit={signIn}>
          <p className="eyebrow">{mode === 'operator' ? 'Operator area' : 'Buyer area'}</p><h2>{mode === 'operator' ? 'Sign in to the trading desk' : 'Sign in to your account'}</h2><p>{mode === 'operator' ? 'Only operator accounts can access administration.' : 'Approved buyer accounts can submit and track stock requests.'}</p>
          <label className="field"><span>Work email</span><input autoFocus required name="email" type="email" autoComplete="username" /></label>
          <label className="field"><span>Password</span><input required minLength={12} name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" /></label>
          <label className="check-field"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} /> Show password</label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
          <button className="text-button" type="button" onClick={() => switchMode('forgot')}>Forgot your password?</button>
        </form>
      ) : mode === 'forgot' ? (
        <form className="auth-form" onSubmit={forgotPassword}>
          <p className="eyebrow">Account recovery</p><h2>Reset your password</h2><p>We will email a one-time link that expires after 30 minutes.</p>
          <label className="field"><span>Work email</span><input autoFocus required name="email" type="email" autoComplete="email" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>{submitting ? 'Requesting…' : 'Send reset link'}</button>
          <button className="text-button" type="button" onClick={() => switchMode('signin')}>Back to sign in</button>
        </form>
      ) : (
        <form className="auth-form" onSubmit={apply}>
          <p className="eyebrow">Buyer application</p><h2>Request portal access</h2><p>Applications are reviewed before the account can sign in.</p>
          <div className="form-grid">
            <label className="field"><span>Registered company name</span><input autoFocus required name="company" autoComplete="organization" /></label><label className="field"><span>VAT / import licence number</span><input name="registration_number" /></label>
            <label className="field"><span>Country of import</span><input required name="country" autoComplete="country-name" /></label><label className="field"><span>Work email</span><input required name="email" type="email" autoComplete="username" /></label>
            <label className="field"><span>Password</span><input required minLength={12} name="password" type="password" autoComplete="new-password" /></label><label className="field"><span>Confirm password</span><input required minLength={12} name="confirm_password" type="password" autoComplete="new-password" /></label>
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>{submitting ? 'Submitting…' : 'Send application'}</button>
        </form>
      )}
    </dialog>
  )
}
