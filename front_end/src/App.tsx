import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AboutPage } from './pages/AboutPage'
import { AdminPage } from './pages/AdminPage'
import { BrandsPage } from './pages/BrandsPage'
import { CataloguePage } from './pages/CataloguePage'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProductPage } from './pages/ProductPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { RequestsPage } from './pages/RequestsPage'
import { SupportPage } from './pages/SupportPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="stock" element={<CataloguePage />} />
        <Route path="stock/:productId" element={<ProductPage />} />
        <Route path="brands" element={<BrandsPage />} />
        <Route path="requests" element={<RequestsPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="support" element={<SupportPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
