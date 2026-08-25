import type {
  BuyerUser,
  DemandRequest,
  Facets,
  Product,
  ProductDetail,
  ProductFilters,
  ProductListResponse,
  RequestInput,
  Summary,
} from '../types'

const API_ROOT = import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

interface RequestOptions {
  signal?: AbortSignal
  method?: 'GET' | 'POST'
  body?: unknown
  csrfToken?: string
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    method: options.method ?? 'GET',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.csrfToken ? { 'X-CSRF-Token': options.csrfToken } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: string } | null
    throw new ApiError(body?.error ?? `Request failed (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

function paramsFor(filters: ProductFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== false) params.set(key, String(value))
  })
  return params
}

export const catalogueApi = {
  summary: (signal?: AbortSignal) => request<Summary>('/api/catalogue/summary', { signal }),
  facets: (signal?: AbortSignal) => request<Facets>('/api/catalogue/facets', { signal }),
  products: (filters: ProductFilters, signal?: AbortSignal) =>
    request<ProductListResponse>(`/api/products?${paramsFor(filters)}`, { signal }),
  product: (id: number, signal?: AbortSignal) => request<ProductDetail>(`/api/products/${id}`, { signal }),
  related: (id: number, signal?: AbortSignal) =>
    request<{ items: Product[] }>(`/api/products/${id}/related`, { signal }),
}

export const buyerApi = {
  me: async (signal?: AbortSignal) => {
    try {
      return await request<{ user: BuyerUser }>('/api/auth/me', { signal })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return { user: null }
      throw error
    }
  },
  login: (email: string, password: string) => request<{ user: BuyerUser }>('/api/auth/login', {
    method: 'POST', body: { email, password },
  }),
  apply: (input: { company: string; registration_number: string; country: string; email: string; password: string }) =>
    request<{ id: number; status: string; email: string }>('/api/auth/applications', { method: 'POST', body: input }),
  logout: (csrfToken: string) => request<{ status: string }>('/api/auth/logout', {
    method: 'POST', body: {}, csrfToken,
  }),
  requests: (signal?: AbortSignal) => request<{ items: DemandRequest[] }>('/api/requests', { signal }),
  createRequest: (input: RequestInput, csrfToken: string) => request<DemandRequest>('/api/requests', {
    method: 'POST', body: input, csrfToken,
  }),
}
