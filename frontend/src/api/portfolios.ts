import { request } from './client'
import type {
  AlertStatusUpdateRequest,
  HoldingCreatePayload,
  HoldingSummary,
  MonitoringAlertResponse,
  MonitoringRunResponse,
  MonitoringTriggerRequest,
  PaginatedPortfolioResponse,
  PortfolioChatRequest,
  PortfolioChatResponse,
  PortfolioCreatePayload,
  PortfolioDetailResponse,
  PortfolioResponse,
} from './types'

export async function listPortfolios(
  page: number = 1,
  pageSize: number = 20,
  isActive?: boolean
): Promise<PaginatedPortfolioResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  })
  if (typeof isActive === 'boolean') {
    params.set('is_active', isActive.toString())
  }
  return await request<PaginatedPortfolioResponse>(`/api/v1/portfolios?${params.toString()}`)
}

export async function getPortfolio(portfolioId: string): Promise<PortfolioDetailResponse> {
  return await request<PortfolioDetailResponse>(`/api/v1/portfolios/${portfolioId}`)
}

export async function createPortfolio(payload: PortfolioCreatePayload): Promise<PortfolioResponse> {
  return await request<PortfolioResponse>('/api/v1/portfolios', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function triggerMonitoring(
  portfolioId: string,
  payload: MonitoringTriggerRequest = {}
): Promise<MonitoringRunResponse> {
  return await request<MonitoringRunResponse>(`/api/v1/portfolios/${portfolioId}/monitor`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getPortfolioAlerts(
  portfolioId: string,
  severity?: string,
  limit: number = 50
): Promise<MonitoringAlertResponse[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  })
  if (severity) {
    params.set('severity', severity)
  }
  return await request<MonitoringAlertResponse[]>(`/api/v1/portfolios/${portfolioId}/alerts?${params.toString()}`)
}

export async function addHolding(
  portfolioId: string,
  payload: HoldingCreatePayload
): Promise<HoldingSummary> {
  return await request<HoldingSummary>(`/api/v1/portfolios/${portfolioId}/holdings`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteHolding(
  portfolioId: string,
  holdingId: string
): Promise<{ status: string; message: string; deleted_id: string }> {
  return await request<{ status: string; message: string; deleted_id: string }>(
    `/api/v1/portfolios/${portfolioId}/holdings/${holdingId}`,
    {
      method: 'DELETE',
    }
  )
}

export async function updateAlertStatus(
  portfolioId: string,
  alertId: string,
  payload: AlertStatusUpdateRequest
): Promise<MonitoringAlertResponse> {
  return await request<MonitoringAlertResponse>(
    `/api/v1/portfolios/${portfolioId}/alerts/${alertId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  )
}

export async function chatWithPortfolio(
  portfolioId: string,
  payload: PortfolioChatRequest
): Promise<PortfolioChatResponse> {
  return await request<PortfolioChatResponse>(`/api/v1/portfolios/${portfolioId}/chat`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}



