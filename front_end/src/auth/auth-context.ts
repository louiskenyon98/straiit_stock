import { createContext } from 'react'
import type { BuyerUser } from '../types'

export type AuthMode = 'signin' | 'apply'

export interface AuthContextValue {
  user: BuyerUser | null
  loading: boolean
  dialogMode: AuthMode | null
  openSignIn: () => void
  openApply: () => void
  closeDialog: () => void
  login: (email: string, password: string) => Promise<void>
  apply: (input: { company: string; registration_number: string; country: string; email: string; password: string }) => Promise<{ id: number; email: string }>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
