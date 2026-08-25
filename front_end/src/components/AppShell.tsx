import { Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AuthDialog } from '../auth/AuthDialog'
import { useAuth } from '../auth/useAuth'

const navigation = [
  ['/', 'Overview'],
  ['/stock', 'Stock list'],
  ['/brands', 'Brands'],
  ['/requests', 'Demand requests'],
  ['/about', 'About'],
  ['/support', 'Support'],
] as const

export function AppShell() {
  const auth = useAuth()
  const [open, setOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setOpen(false)
    window.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="nav-shell">
          <NavLink className="brand" to="/">STRAIIT <span>STOCK PORTAL</span></NavLink>
          <button
            className="menu-button"
            type="button"
            aria-label={open ? 'Close navigation' : 'Open navigation'}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
          <nav className={open ? 'site-nav is-open' : 'site-nav'} aria-label="Primary navigation">
            {navigation.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === '/'}>{label}</NavLink>
            ))}
            {auth.user?.role === 'operator' && <NavLink to="/admin">Trading desk</NavLink>}
            <div className="mobile-account-actions">
              {auth.user ? <button className="button button-secondary" type="button" onClick={() => void auth.logout()}>Sign out</button> : <><button className="button button-secondary" type="button" onClick={auth.openSignIn}>Sign in</button><button className="button button-primary" type="button" onClick={auth.openApply}>Request access</button></>}
            </div>
          </nav>
          <div className="account-nav">
            {auth.user ? (
              <>
                <NavLink className="account-company" to={auth.user.role === 'operator' ? '/admin' : '/requests'}>{auth.user.organization.name}</NavLink>
                <button className="button button-secondary nav-account-button" type="button" onClick={() => void auth.logout()}>Sign out</button>
              </>
            ) : (
              <>
                <button className="button button-secondary nav-account-button" type="button" onClick={auth.openSignIn}>Sign in</button>
                <button className="button button-primary nav-account-button" type="button" onClick={auth.openApply}>Request access</button>
              </>
            )}
          </div>
        </div>
      </header>
      <main id="main-content"><Outlet /></main>
      <footer className="site-footer">
        <div className="footer-shell">
          <p>STRAIIT STOCK PORTAL · Wholesale product catalogue</p>
          <div>
            <NavLink to="/about">About</NavLink>
            <NavLink to="/support">Support</NavLink>
            <NavLink to="/stock">Stock list</NavLink>
          </div>
        </div>
      </footer>
      <AuthDialog />
    </div>
  )
}
