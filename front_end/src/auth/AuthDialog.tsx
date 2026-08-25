import { useEffect, useRef, useState, type FormEvent } from 'react'
import { CheckCircle2, X } from 'lucide-react'
import type { AuthMode } from './auth-context'
import { useAuth } from './useAuth'

export function AuthDialog() {
  const auth = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [mode, setMode] = useState<AuthMode>('signin')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [application, setApplication] = useState<{ id: number; email: string } | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (auth.dialogMode) {
      setMode(auth.dialogMode)
      setError('')
      setApplication(null)
      if (!dialog.open) dialog.showModal()
    } else if (dialog.open) {
      dialog.close()
    }
  }, [auth.dialogMode])

  function switchMode(next: AuthMode) {
    setMode(next)
    setError('')
    setApplication(null)
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setSubmitting(true)
    setError('')
    try {
      await auth.login(String(data.get('email')), String(data.get('password')))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to sign in.')
    } finally {
      setSubmitting(false)
    }
  }

  async function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get('password'))
    if (password !== String(data.get('confirm_password'))) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      setApplication(await auth.apply({
        company: String(data.get('company')),
        registration_number: String(data.get('registration_number')),
        country: String(data.get('country')),
        email: String(data.get('email')),
        password,
      }))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to submit the application.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <dialog ref={dialogRef} className="auth-dialog" onCancel={auth.closeDialog} onClose={auth.closeDialog}>
      <button className="dialog-close" type="button" aria-label="Close" onClick={auth.closeDialog}><X aria-hidden="true" /></button>
      <div className="auth-tabs" role="tablist" aria-label="Buyer account">
        <button type="button" role="tab" aria-selected={mode === 'signin'} onClick={() => switchMode('signin')}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === 'apply'} onClick={() => switchMode('apply')}>Apply for an account</button>
      </div>
      {mode === 'signin' ? (
        <form className="auth-form" onSubmit={signIn}>
          <p className="eyebrow">Buyer area</p>
          <h2>Sign in to your account</h2>
          <p>Approved buyer accounts can submit and track stock requests.</p>
          <label className="field"><span>Work email</span><input autoFocus required name="email" type="email" autoComplete="username" /></label>
          <label className="field"><span>Password</span><input required minLength={12} name="password" type="password" autoComplete="current-password" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
      ) : application ? (
        <div className="application-success" role="status">
          <CheckCircle2 aria-hidden="true" />
          <p className="eyebrow">Application received</p>
          <h2>Verification is pending</h2>
          <p>Application #{application.id} for {application.email} is waiting for approval. You can sign in after the trading desk verifies the company.</p>
          <button className="button button-secondary" onClick={auth.closeDialog}>Close</button>
        </div>
      ) : (
        <form className="auth-form" onSubmit={apply}>
          <p className="eyebrow">Buyer application</p>
          <h2>Request portal access</h2>
          <p>Applications are reviewed before the account can sign in.</p>
          <div className="form-grid">
            <label className="field"><span>Registered company name</span><input autoFocus required name="company" autoComplete="organization" /></label>
            <label className="field"><span>VAT / import licence number</span><input name="registration_number" /></label>
            <label className="field"><span>Country of import</span><input required name="country" autoComplete="country-name" /></label>
            <label className="field"><span>Work email</span><input required name="email" type="email" autoComplete="username" /></label>
            <label className="field"><span>Password</span><input required minLength={12} name="password" type="password" autoComplete="new-password" /></label>
            <label className="field"><span>Confirm password</span><input required minLength={12} name="confirm_password" type="password" autoComplete="new-password" /></label>
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" disabled={submitting}>{submitting ? 'Submitting…' : 'Send application'}</button>
        </form>
      )}
    </dialog>
  )
}
