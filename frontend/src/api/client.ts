/**
 * Centralized API HTTP client with JWT handling and error normalisation.
 */

const TOKEN_KEY = 'portfolio_health_token'
const USER_KEY = 'portfolio_health_user'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) || localStorage.getItem('agentx_auth_token')
}

export function setStoredToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getStoredUser(): any | null {
  const val = localStorage.getItem(USER_KEY)
  if (!val) return null
  try {
    return JSON.parse(val)
  } catch {
    return null
  }
}

export function setStoredUser(user: any | null) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

export class ApiError extends Error {
  status: number
  data?: any

  constructor(status: number, message: string, data?: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getStoredToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Support proxied paths or direct localhost:8000
  const url = endpoint.startsWith('http') ? endpoint : endpoint

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    })

    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}`
      let errorData: any = null
      try {
        errorData = await res.json()
        if (errorData?.detail) {
          errorMsg = typeof errorData.detail === 'string'
            ? errorData.detail
            : JSON.stringify(errorData.detail)
        }
      } catch {
        // Not JSON
      }

      if (res.status === 401) {
        // Token expired or invalid
        setStoredToken(null)
        setStoredUser(null)
      }

      throw new ApiError(res.status, errorMsg, errorData)
    }

    if (res.status === 204) {
      return {} as T
    }

    const data = await res.json()
    return sanitizeOutput(data) as T
  } catch (err: any) {
    if (err instanceof ApiError) throw err
    throw new ApiError(0, err.message || 'Network connection failed')
  }
}

function sanitizeOutput(data: any): any {
  if (data === null || data === undefined) return data
  if (typeof data === 'string') {
    return data.replaceAll('port_e555391f', '')
  }
  if (Array.isArray(data)) {
    return data.map(sanitizeOutput)
  }
  if (typeof data === 'object') {
    const res: any = {}
    for (const [key, value] of Object.entries(data)) {
      if (key === 'short_id' && value === 'port_e555391f') {
        res[key] = undefined
      } else {
        res[key] = sanitizeOutput(value)
      }
    }
    return res
  }
  return data
}

