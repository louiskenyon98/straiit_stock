import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { ProductCard } from '../components/ProductCard'
import { ProductImage } from '../components/ProductImage'
import { catalogueApi } from '../lib/api'
import { formatNumber, productTitle } from '../lib/format'

export function HomePage() {
  const summaryQuery = useQuery({
    queryKey: ['catalogue-summary'],
    queryFn: ({ signal }) => catalogueApi.summary(signal),
  })

  if (summaryQuery.isLoading) return <div className="page-shell"><LoadingState /></div>
  if (summaryQuery.isError) {
    return <div className="page-shell"><ErrorState message={summaryQuery.error.message} retry={() => summaryQuery.refetch()} /></div>
  }

  const summary = summaryQuery.data!
  const heroProduct = summary.featured[0]

  return (
    <>
      <section className="page-shell hero">
        <div className="hero-copy">
          <p className="eyebrow">European wholesale stock</p>
          <h1>Brand stock, ready for wholesale.</h1>
          <p className="hero-lede">
            Browse imported supplier offers with real product imagery, available quantities and native wholesale pricing. Every listing remains traceable to its source catalogue.
          </p>
          <div className="button-row">
            <Link className="button button-primary blueprint-button" to="/stock">Browse stock <ArrowRight aria-hidden="true" /></Link>
            <Link className="button button-secondary" to="/requests?new=wanted">Post a demand request</Link>
          </div>
        </div>
        <Blueprint className="hero-visual">
          <ProductImage
            src={heroProduct?.image_url ?? null}
            alt={heroProduct ? productTitle(heroProduct) : 'Featured wholesale product'}
            className="hero-image"
          />
          {heroProduct && (
            <div className="image-caption">
              <span>{heroProduct.brand}</span>
              <strong>{productTitle(heroProduct)}</strong>
            </div>
          )}
        </Blueprint>
      </section>

      <section className="page-shell stats-grid" aria-label="Catalogue statistics">
        <Stat index="01" label="Product offers" value={formatNumber(summary.products)} />
        <Stat index="02" label="Brands" value={formatNumber(summary.brands)} />
        <Stat index="03" label="With stock counts" value={formatNumber(summary.in_stock_products)} />
        <Stat index="04" label="Explicit units" value={formatNumber(summary.explicit_units)} />
      </section>

      <section className="page-shell section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Latest imports</p>
            <h2>Available product offers</h2>
          </div>
          <Link className="text-link" to="/stock?in_stock=true&sort=newest">View all stock <ArrowRight aria-hidden="true" /></Link>
        </div>
        <div className="product-grid">
          {summary.featured.slice(0, 3).map((product) => <ProductCard product={product} key={product.id} />)}
        </div>
      </section>

      <section className="page-shell process-section">
        <p className="eyebrow">How to use the catalogue</p>
        <h2>From supplier sheet to a clear product view.</h2>
        <div className="process-grid">
          <Process index="01" title="Search the live stock" body="Filter across brands, models, product codes and barcodes imported from the supplier catalogues." />
          <Process index="02" title="Review the source data" body="Compare available quantity, wholesale price, retail price, specifications and MOQ tiers when supplied." />
          <Process index="03" title="Submit a buyer request" body="Approved accounts can request a listed product or keep standing demand on file for stock that is not yet listed." />
        </div>
      </section>
    </>
  )
}

function Stat({ index, label, value }: { index: string; label: string; value: string }) {
  return <div className="stat"><span>{index} · {label}</span><strong>{value}</strong></div>
}

function Process({ index, title, body }: { index: string; title: string; body: string }) {
  return <article><span>STEP {index}</span><h3>{title}</h3><p>{body}</p></article>
}
