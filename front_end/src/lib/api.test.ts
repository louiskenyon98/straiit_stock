import { afterEach, describe, expect, it, vi } from 'vitest'
import { buyerApi } from './api'

describe('buyer API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('treats an unauthenticated session as a guest', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'Authentication required' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })))
    await expect(buyerApi.me()).resolves.toEqual({ user: null })
  })

  it('sends the session CSRF token with a request mutation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    await buyerApi.createRequest({
      request_type: 'wanted', brand: 'Gucci', quantity: 100, destination: 'London',
    }, 'csrf-test-token')
    expect(fetchMock).toHaveBeenCalledWith('/api/requests', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-test-token' }),
    }))
  })
})
