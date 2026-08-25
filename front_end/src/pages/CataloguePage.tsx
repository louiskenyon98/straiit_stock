import { useQuery } from '@tanstack/react-query'
import { RotateCcw, Search } from 'lucide-react'
import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { ProductCard } from '../components/ProductCard'
import { catalogueApi } from '../lib/api'
import { formatNumber } from '../lib/format'
import type { ProductFilters } from '../types'

const defaults: ProductFilters = {
  page: 1,
  page_size: 24,
  query: '',
  brand: '',
  category: '',
  status: '',
  gender: '',
  currency: '',
  in_stock: false,
  sort: 'name',
}

export function CataloguePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo<ProductFilters>(() => ({
    ...defaults,
    page: Math.max(1, Number(searchParams.get('page')) || 1),
    query: searchParams.get('query') ?? '',
    brand: searchParams.get('brand') ?? '',
    category: searchParams.get('category') ?? '',
    status: searchParams.get('status') ?? '',
    gender: searchParams.get('gender') ?? '',
    currency: searchParams.get('currency') ?? '',
    in_stock: searchParams.get('in_stock') === 'true',
    sort: searchParams.get('sort') ?? 'name',
  }), [searchParams])

  const productsQuery = useQuery({
    queryKey: ['products', filters],
    queryFn: ({ signal }) => catalogueApi.products(filters, signal),
  })
  const facetsQuery = useQuery({
    queryKey: ['catalogue-facets'],
    queryFn: ({ signal }) => catalogueApi.facets(signal),
  })

  function setFilter(key: keyof ProductFilters, value: string | boolean | number) {
    const next = new URLSearchParams(searchParams)
    if (value === '' || value === false || (key === 'page' && value === 1)) next.delete(key)
    else next.set(key, String(value))
    if (key !== 'page') next.delete('page')
    setSearchParams(next)
  }

  const facets = facetsQuery.data
  const result = productsQuery.data

  return (
    <div className="page-shell catalogue-page">
      <div className="page-heading">
        <div><p className="eyebrow">Stock list</p><h1>Product offers</h1></div>
        {result && <p>{formatNumber(result.pagination.total)} matching products<br />Page {result.pagination.page} of {result.pagination.pages}</p>}
      </div>

      <Blueprint className="filter-panel">
        <label className="field search-field">
          <span>Search brand, model, SKU or barcode</span>
          <span className="input-with-icon"><Search aria-hidden="true" /><input value={filters.query} onChange={(event) => setFilter('query', event.target.value)} placeholder="e.g. Gucci or SKU" /></span>
        </label>
        <Filter label="Brand" value={filters.brand} onChange={(value) => setFilter('brand', value)} options={facets?.brands} />
        <Filter label="Category" value={filters.category} onChange={(value) => setFilter('category', value)} options={facets?.categories} />
        <Filter label="Status" value={filters.status} onChange={(value) => setFilter('status', value)} options={facets?.statuses} />
        <label className="field">
          <span>Sort</span>
          <select value={filters.sort} onChange={(event) => setFilter('sort', event.target.value)}>
            <option value="name">Product name</option>
            <option value="brand">Brand A–Z</option>
            <option value="quantity_desc">Largest quantity</option>
            <option value="price_asc">Lowest wholesale price</option>
            <option value="price_desc">Highest wholesale price</option>
            <option value="newest">Newest import</option>
          </select>
        </label>
        <label className="check-field"><input type="checkbox" checked={filters.in_stock} onChange={(event) => setFilter('in_stock', event.target.checked)} /><span>Explicit stock only</span></label>
        <button className="button button-secondary reset-button" type="button" onClick={() => setSearchParams({})}><RotateCcw aria-hidden="true" /> Reset</button>
      </Blueprint>

      {productsQuery.isLoading && <LoadingState label="Loading product offers" />}
      {productsQuery.isError && <ErrorState message={productsQuery.error.message} retry={() => productsQuery.refetch()} />}
      {result && result.items.length > 0 && (
        <>
          <div className="product-grid catalogue-grid">{result.items.map((product) => <ProductCard key={product.id} product={product} />)}</div>
          <Pagination page={result.pagination.page} pages={result.pagination.pages} onChange={(page) => setFilter('page', page)} />
        </>
      )}
      {result && result.items.length === 0 && (
        <Blueprint className="empty-state"><h2>No products match these filters</h2><p>Try a broader search or clear the current filters.</p><button className="button button-secondary" onClick={() => setSearchParams({})}>Clear filters</button></Blueprint>
      )}
    </div>
  )
}

function Filter({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options?: { value: string; label: string; count: number }[] }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All {label.toLowerCase()}s</option>
        {options?.map((option) => <option key={option.value} value={option.value}>{option.label} ({formatNumber(option.count)})</option>)}
      </select>
    </label>
  )
}

function Pagination({ page, pages, onChange }: { page: number; pages: number; onChange: (page: number) => void }) {
  if (pages <= 1) return null
  return (
    <nav className="pagination" aria-label="Product pages">
      <button className="button button-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
      <span>Page {page} of {pages}</span>
      <button className="button button-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button>
    </nav>
  )
}
