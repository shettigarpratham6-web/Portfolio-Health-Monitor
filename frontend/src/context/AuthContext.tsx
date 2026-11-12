import React, { createContext, useContext, useEffect, useState } from 'react'
import { getCurrentUser, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/auth'
import { getStoredToken, getStoredUser, setStoredToken, setStoredUser } from '../api/client'
import type { UserResponse } from '../api/types'

interface AuthContextType {
  user: UserResponse | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, pass: string) => Promise<void>
  register: (email: string, pass: string, name?: string) => Promise<void>
  loginAsDemo: () => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(getStoredToken())
  const [user, setUser] = useState<UserResponse | null>(getStoredUser())
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const refreshUser = async () => {
    const curToken = getStoredToken()
    if (!curToken) {
      setUser(null)
      setIsLoading(false)
      return
    }
    try {
      const u = await getCurrentUser()
      setUser(u)
    } catch {
      setUser(null)
      setToken(null)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
  }, [])

  const handleLogin = async (email: string, pass: string) => {
    const res = await apiLogin(email, pass)
    setToken(res.access_token)
    const u = await getCurrentUser()
    setUser(u)
  }

  const handleRegister = async (email: string, pass: string, name?: string) => {
    await apiRegister(email, pass, name)
    await handleLogin(email, pass)
  }

  const handleLoginAsDemo = async () => {
    // Generate an ephemeral demo account or log into development user
    const demoEmail = `investor_${Math.floor(Math.random() * 90000 + 10000)}@portfoliohealth.local`
    const demoPass = 'DemoPassword123!'
    try {
      await handleRegister(demoEmail, demoPass, 'Risk Analyst')
    } catch {
      // If registration fails, attempt standard login with default development account
      await handleLogin('investor@example.com', 'testpass')
    }
  }

  const handleLogout = () => {
    apiLogout()
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login: handleLogin,
        register: handleRegister,
        loginAsDemo: handleLoginAsDemo,
        logout: handleLogout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}

