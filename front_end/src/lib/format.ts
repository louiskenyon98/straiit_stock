export function formatNumber(value: number | null | undefined, maximumFractionDigits = 0) {
  if (value == null) return 'Not supplied'
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits }).format(value)
}

export function formatMoney(value: number | null | undefined, currency: string | null | undefined) {
  if (value == null) return 'Not supplied'
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: currency || 'EUR',
    maximumFractionDigits: 2,
  }).format(value)
}

export function productTitle(product: { name: string | null; model: string | null; sku: string | null }) {
  return product.name || product.model || product.sku || 'Untitled product'
}
