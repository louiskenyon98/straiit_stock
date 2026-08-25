import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Product } from '../types'
import { formatMoney, formatNumber, productTitle } from '../lib/format'
import { Blueprint } from './Blueprint'
import { ProductImage } from './ProductImage'
import { StatusTag } from './StatusTag'

export function ProductCard({ product }: { product: Product }) {
  const title = productTitle(product)
  return (
    <Blueprint as="article" className="product-card">
      <Link className="product-card-image" to={`/stock/${product.id}`} tabIndex={-1} aria-hidden="true">
        <ProductImage src={product.image_url} alt="" />
      </Link>
      <div className="product-card-content">
        <div className="card-topline">
          <span className="eyebrow">{product.brand || 'Brand not supplied'}</span>
          <StatusTag status={product.status} label={product.status_label} />
        </div>
        <h3><Link to={`/stock/${product.id}`}>{title}</Link></h3>
        <p className="product-reference">
          {[product.sku, product.category, product.color].filter(Boolean).join(' · ') || `Product ${product.id}`}
        </p>
        <dl className="card-facts">
          <div>
            <dt>Available quantity</dt>
            <dd>{product.has_quantity ? formatNumber(product.quantity) : 'Not supplied'}</dd>
          </div>
          <div>
            <dt>Wholesale</dt>
            <dd>{formatMoney(product.wholesale_price, product.currency)}</dd>
          </div>
        </dl>
        <div className="card-footer">
          {product.retail_price != null ? <span>RRP {formatMoney(product.retail_price, product.currency)}</span> : <span>RRP not supplied</span>}
          <Link className="button button-primary button-small" to={`/stock/${product.id}`}>
            View offer <ArrowUpRight aria-hidden="true" />
          </Link>
        </div>
      </div>
    </Blueprint>
  )
}
