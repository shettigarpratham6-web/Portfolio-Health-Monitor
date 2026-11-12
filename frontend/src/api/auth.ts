import { request, setStoredToken, setStoredUser } from './client'
import type { TokenResponse, UserResponse } from './types'

export async function login(email: string, password: string): Promise<TokenResponse> {
  const data = await request<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setStoredToken(data.access_token)
  return data
}

export async function register(email: string, password: string, fullName?: string): Promise<UserResponse> {
  const data = await request<UserResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName }),
  })
  return data
}

export async function getCurrentUser(): Promise<UserResponse> {
  const user = await request<UserResponse>('/api/v1/auth/me', {
    method: 'GET',
  })
  setStoredUser(user)
  return user
}

export function logout() {
  setStoredToken(null)
  setStoredUser(null)
}

