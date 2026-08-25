import { Link } from 'react-router-dom'
import { Blueprint } from '../components/Blueprint'

export function NotFoundPage() {
  return <div className="page-shell"><Blueprint className="empty-state"><p className="eyebrow">404</p><h1>Page not found</h1><p>The requested catalogue page does not exist.</p><Link className="button button-primary" to="/">Return to overview</Link></Blueprint></div>
}
