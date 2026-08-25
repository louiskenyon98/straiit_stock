import { describe, expect, it } from 'vitest'
import { formatMoney, formatNumber, productTitle } from './format'

describe('catalogue formatting', () => {
  it('keeps missing values explicit', () => {
    expect(formatNumber(null)).toBe('Not supplied')
    expect(formatMoney(undefined, 'EUR')).toBe('Not supplied')
  })

  it('formats money in its supplied currency', () => {
    expect(formatMoney(29, 'EUR')).toContain('29.00')
    expect(formatMoney(29, 'GBP')).toContain('29.00')
  })

  it('uses model and SKU as title fallbacks', () => {
    expect(productTitle({ name: null, model: 'MODEL-1', sku: 'SKU-1' })).toBe('MODEL-1')
    expect(productTitle({ name: null, model: null, sku: 'SKU-1' })).toBe('SKU-1')
  })
})
