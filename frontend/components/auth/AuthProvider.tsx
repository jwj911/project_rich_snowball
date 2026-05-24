'use client'

import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, User } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'

interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<User>
  register: (username: string, email: string, password: string) => Promise<void>
  refreshUser: () => Promise<void>
  logout: () => void
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const logout = useCallback(() => {
    captureMessage(`用户退出登录`, 'info')
    api.logout()
    setUser(null)
    setError(null)
  }, [])

  const refreshUser = useCallback(async () => {
    const token = api.getToken()
    if (!token) {
      setUser(null)
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    try {
      const currentUser = await api.getMe()
      setUser(currentUser)
      setError(null)
    } catch (err) {
      api.logout()
      setUser(null)
      setError(err instanceof Error ? err.message : '登录状态已失效')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshUser()
  }, [refreshUser])

  const login = useCallback(async (username: string, password: string) => {
    setIsLoading(true)
    setError(null)
    try {
      await api.login(username, password)
      const currentUser = await api.getMe()
      setUser(currentUser)
      return currentUser
    } catch (err) {
      const message = err instanceof Error ? err.message : '登录失败'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  const register = useCallback(async (username: string, email: string, password: string) => {
    setIsLoading(true)
    setError(null)
    try {
      await api.register(username, email, password)
    } catch (err) {
      const message = err instanceof Error ? err.message : '注册失败'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isAuthenticated: Boolean(user),
    isLoading,
    error,
    login,
    register,
    refreshUser,
    logout,
    clearError: () => setError(null),
  }), [error, isLoading, login, logout, refreshUser, register, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
