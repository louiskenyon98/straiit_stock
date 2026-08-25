import { AlertTriangle, LoaderCircle } from 'lucide-react'
import { Blueprint } from './Blueprint'

export function LoadingState({ label = 'Loading catalogue' }: { label?: string }) {
  return (
    <div className="async-state" role="status">
      <LoaderCircle className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Blueprint className="async-state async-error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <strong>Catalogue unavailable</strong>
        <p>{message}</p>
      </div>
      {retry && <button className="button button-secondary" onClick={retry}>Try again</button>}
    </Blueprint>
  )
}
