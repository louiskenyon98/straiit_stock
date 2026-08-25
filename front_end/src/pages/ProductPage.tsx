import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Mail } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/AsyncState'
import { Blueprint } from '../components/Blueprint'
import { ProductCard } from '../components/ProductCard'
import { ProductImage } from '../components/ProductImage'
import { StatusTag } from '../components/StatusTag'
import { StockRequestForm } from '../components/StockRequestForm'
import { catalogueApi } from '../lib/api'
import { formatMoney, formatNumber, productTitle } from '../lib/format'

export function ProductPage() {
  const productId = Number(useParams().productId)
  const validId = Number.isInteger(productId) && productId > 0
  const productQuery = useQuery({
    queryKey: ['product', productId],
    queryFn: ({ signal }) => catalogueApi.product(productId, signal),
    enabled: validId,
  })
  const relatedQuery = useQuery({
    queryKey: ['related-products', productId],
    queryFn: ({ signal }) => catalogueApi.related(productId, signal),
    enabled: validId && productQuery.isSuccess,
  })

  if (!validId) return <div className="page-shell"><ErrorState message="This product reference is invalid." /></div>
  if (productQuery.isLoading) return <div className="page-shell"><LoadingState label="Loading product" /></div>
  if (productQuery.isError) return <div className="page-shell"><ErrorState message={productQuery.error.message} retry={() => productQuery.refetch()} /></div>

  const product = productQuery.data!
  const title = productTitle(product)
  const primary = product.images.find((image) => image.is_primary)?.url || product.image_url
  const specs = [
    ['Model', product.model], ['SKU', product.sku], ['Barcode', product.barcode],
    ['Category', product.category], ['Colour', product.color], ['Size', product.size],
    ['Gender', product.gender], ['Material', product.material], ['Origin', product.origin],
    ['Grade', product.grade], ['Collection', product.collection], ['Model year', product.model_year],
    ['Frame colour', product.frame_color], ['Lens colour', product.lens_color],
    ['Frame material', product.frame_material], ['Bridge size', product.bridge_size],
    ['Branch size', product.branch_size], ['Fitting', product.fitting], ['UVA filter', product.uva_filter],
    ['HS code', product.hs_code], ['Release code', product.release_code], ['Phase', product.phase],
  ].filter(([, value]) => value != null && value !== '')

  return (
    <div className="page-shell product-page">
      <Link className="back-link" to="/stock"><ArrowLeft aria-hidden="true" /> Back to stock list</Link>
      <section className="product-hero">
        <Blueprint className="product-gallery">
          <ProductImage src={primary} alt={title} />
          {product.images.length > 1 && <span className="gallery-count">{product.images.length} images</span>}
        </Blueprint>
        <div className="product-summary">
          <div className="summary-tags"><span className="eyebrow">{product.brand || 'Brand not supplied'}</span><StatusTag status={product.status} label={product.status_label} />{product.category && <span className="tag tag-outline">{product.category}</span>}</div>
          <h1>{title}</h1>
          <p className="product-reference">Product {product.id}{product.sku ? ` · ${product.sku}` : ''}</p>
          {product.description && <p className="product-description">{product.description}</p>}
          <dl className="commercial-facts">
            <div><dt>Available quantity</dt><dd>{product.has_quantity ? formatNumber(product.quantity) : 'Not supplied'}</dd></div>
            <div><dt>Wholesale price</dt><dd>{formatMoney(product.wholesale_price, product.currency)}</dd></div>
            <div><dt>Retail price</dt><dd>{formatMoney(product.retail_price, product.currency)}</dd></div>
            {product.offer_type && <div><dt>Offer type</dt><dd>{product.offer_type}</dd></div>}
          </dl>
          <Link className="button button-primary button-wide" to={`/support?product=${product.id}${product.sku ? `&sku=${encodeURIComponent(product.sku)}` : ''}`}><Mail aria-hidden="true" /> Ask about this product</Link>
        </div>
      </section>

      {specs.length > 0 && <section className="detail-section"><div className="section-heading"><div><p className="eyebrow">Specification</p><h2>Product details</h2></div></div><Blueprint as="dl" className="spec-grid">{specs.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</Blueprint></section>}

      {product.moq_tiers.length > 0 && <section className="detail-section"><p className="eyebrow">Volume pricing</p><h2>Supplier MOQ tiers</h2><Blueprint className="table-frame"><div className="table-scroll"><table><thead><tr><th>Minimum quantity</th><th>Wholesale price</th></tr></thead><tbody>{product.moq_tiers.map((tier) => <tr key={tier.minimum_quantity}><td>{formatNumber(tier.minimum_quantity)} pcs</td><td>{formatMoney(tier.price, product.currency)}</td></tr>)}</tbody></table></div></Blueprint></section>}

      {product.variants.length > 0 && <section className="detail-section"><p className="eyebrow">Stock breakdown</p><h2>Available variants</h2><Blueprint className="table-frame"><div className="table-scroll" role="region" aria-label="Product variants" tabIndex={0}><table><thead><tr><th>Size</th><th>Quantity</th><th>SKU</th><th>Barcode</th></tr></thead><tbody>{product.variants.map((variant) => <tr key={variant.id}><td>{variant.size}</td><td>{formatNumber(variant.quantity)}</td><td>{variant.sku || '—'}</td><td>{variant.barcode || '—'}</td></tr>)}</tbody></table></div></Blueprint></section>}

      <StockRequestForm product={product} />

      {relatedQuery.data?.items.length ? <section className="detail-section"><div className="section-heading"><div><p className="eyebrow">Continue browsing</p><h2>Related products</h2></div></div><div className="product-grid">{relatedQuery.data.items.slice(0, 3).map((item) => <ProductCard key={item.id} product={item} />)}</div></section> : null}
    </div>
  )
}
