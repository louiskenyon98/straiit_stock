import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { buyerApi } from '../lib/api'
import { AuthContext, type AuthContextValue, type AuthMode } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [dialogMode, setDialogMode] = useState<AuthMode | null>(null)
  const authQuery = useQuery({
    queryKey: ['buyer-session'],
    queryFn: ({ signal }) => buyerApi.me(signal),
    retry: false,
    staleTime: 30_000,
  })
  const user = authQuery.data?.user ?? null

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading: authQuery.isLoading,
    dialogMode,
    openSignIn: () => setDialogMode('signin'),
    openOperatorSignIn: () => setDialogMode('operator'),
    openApply: () => setDialogMode('apply'),
    closeDialog: () => setDialogMode(null),
    login: async (email, password) => {
      const result = await buyerApi.login(email, password)
      queryClient.setQueryData(['buyer-session'], result)
      setDialogMode(null)
    },
    operatorLogin: async (email, password) => {
      const result = await buyerApi.operatorLogin(email, password)
      queryClient.setQueryData(['buyer-session'], result)
      setDialogMode(null)
    },
    apply: async (input) => {
      const result = await buyerApi.apply(input)
      return { id: result.id, email: result.email }
    },
    logout: async () => {
      if (user) await buyerApi.logout(user.csrf_token)
      queryClient.setQueryData(['buyer-session'], { user: null })
      queryClient.removeQueries({ queryKey: ['buyer-requests'] })
    },
  }), [authQuery.isLoading, dialogMode, queryClient, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
