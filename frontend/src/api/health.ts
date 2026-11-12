import { request } from './client'
import type { DbHealthResponse, HealthResponse, TracingHealthResponse } from './types'

export async function checkHealth(): Promise<HealthResponse> {
  return await request<HealthResponse>('/health')
}

export async function checkDbHealth(): Promise<DbHealthResponse> {
  return await request<DbHealthResponse>('/health/database')
}

export async function checkTracingHealth(): Promise<TracingHealthResponse> {
  return await request<TracingHealthResponse>('/health/tracing')
}

