import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiFetch } from '@/lib/api'

export type Role = 'viewer' | 'analyst' | 'admin'

export interface User {
  id: string
  email: string
  name: string
  role: Role
}

interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  user: User
}

interface AuthState {
  token: string | null
  user: User | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const ROLE_RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 }

export function hasRole(user: User | null, minimum: Role): boolean {
  return user !== null && ROLE_RANK[user.role] >= ROLE_RANK[minimum]
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      async login(email, password) {
        const result = await apiFetch<LoginResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
        set({ token: result.access_token, user: result.user })
      },
      logout() {
        set({ token: null, user: null })
      },
    }),
    { name: 't2s-auth', partialize: ({ token, user }) => ({ token, user }) },
  ),
)
