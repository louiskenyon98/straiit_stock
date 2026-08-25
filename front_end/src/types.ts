export interface Product {
  id: number
  brand: string | null
  name: string | null
  category: string | null
  model: string | null
  sku: string | null
  barcode: string | null
  description?: string | null
  color: string | null
  size: string | null
  gender: string | null
  material?: string | null
  quantity: number | null
  wholesale_price: number | null
  retail_price: number | null
  currency: string | null
  status: string | null
  status_label: string | null
  image_url: string | null
  offer_type: string | null
  origin: string | null
  grade: string | null
  collection: string | null
  has_quantity: boolean
}

export interface ProductDetail extends Product {
  description: string | null
  material: string | null
  hs_code: string | null
  model_year: string | null
  frame_color: string | null
  lens_color: string | null
  color_code: string | null
  material_code: string | null
  frame_material: string | null
  bridge_size: string | null
  branch_size: string | null
  uva_filter: string | null
  fitting: string | null
  release_code: string | null
  phase: string | null
  exceeding_quantity: number | null
  total_retail_value: number | null
  variants: ProductVariant[]
  images: ProductImage[]
  moq_tiers: MoqTier[]
}

export interface ProductVariant {
  id: number
  size: string
  quantity: number | null
  barcode: string | null
  sku: string | null
}

export interface ProductImage {
  id: number
  url: string | null
  mime_type: string | null
  is_primary: boolean
  sort_order: number
}

export interface MoqTier {
  minimum_quantity: number
  price: number
}

export interface Pagination {
  page: number
  page_size: number
  total: number
  pages: number
}

export interface ProductListResponse {
  items: Product[]
  pagination: Pagination
}

export interface Facet {
  value: string
  label: string
  count: number
}

export interface Facets {
  brands: Facet[]
  categories: Facet[]
  statuses: Facet[]
  genders: Facet[]
  currencies: Facet[]
}

export interface Summary {
  products: number
  brands: number
  explicit_units: number
  in_stock_products: number
  latest_product_id: number | null
  featured: Product[]
}

export interface ProductFilters {
  page: number
  page_size: number
  query: string
  brand: string
  category: string
  status: string
  gender: string
  currency: string
  in_stock: boolean
  sort: string
}

export interface BuyerUser {
  id: number
  email: string
  display_name: string | null
  organization: {
    id: number
    name: string
    country: string
    registration_number: string | null
  }
  csrf_token: string
}

export interface DemandRequest {
  id: number
  reference: string
  request_type: 'stock' | 'wanted'
  product_id: number | null
  product: Pick<Product, 'id' | 'brand' | 'name' | 'model' | 'sku' | 'category' | 'wholesale_price' | 'currency' | 'image_url'> | null
  brand: string | null
  category: string | null
  quantity: number
  target_price: number | null
  currency: string | null
  destination: string
  notes: string | null
  status: 'new' | 'reviewing' | 'sourcing' | 'quoted' | 'accepted' | 'closed' | 'rejected'
  created_at: string
  updated_at: string
  quote: {
    id: number
    amount: number
    currency: string
    valid_until: string | null
    terms: string | null
    status: string
  } | null
  history?: { status: string; note: string | null; created_at: string }[]
}

export interface RequestInput {
  request_type: 'stock' | 'wanted'
  product_id?: number
  brand?: string
  category?: string
  quantity: number
  target_price?: number
  currency?: string
  destination: string
  notes?: string
}
