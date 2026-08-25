import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { catalogueApi } from '../lib/api'
import { formatNumber } from '../lib/format'

export function BrandsPage() {
  const facetsQuery = useQuery({ queryKey: ['catalogue-facets'], queryFn: ({ signal }) => catalogueApi.facets(signal) })
  if (facetsQuery.isLoading) return <div className="page-shell"><LoadingState label="Loading brands" /></div>
  if (facetsQuery.isError) return <div className="page-shell"><ErrorState message={facetsQuery.error.message} retry={() => facetsQuery.refetch()} /></div>
  return (
    <div className="page-shell brands-page">
      <div className="page-heading"><div><p className="eyebrow">Portfolio</p><h1>Brands in the catalogue</h1></div><p>Names are merged case-insensitively from the imported supplier data.</p></div>
      <div className="brand-grid">
        {facetsQuery.data!.brands.map((brand) => (
          <Blueprint as="article" className="brand-card" key={brand.value}>
            <span className="eyebrow">Wholesale catalogue</span>
            <h2>{brand.label}</h2>
            <p><strong>{formatNumber(brand.count)}</strong> product offers</p>
            <Link className="button button-secondary" to={`/stock?brand=${encodeURIComponent(brand.value)}`}>View products <ArrowRight aria-hidden="true" /></Link>
          </Blueprint>
        ))}
      </div>
    </div>
  )
}
