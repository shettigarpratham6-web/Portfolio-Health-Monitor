/**
 * Portfolio Health Monitor TypeScript Data Contracts.
 */

export interface UserResponse {
  id: string
  short_id?: string | null
  email: string
  full_name?: string | null
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface HoldingSummary {
  id: string
  short_id?: string | null
  company_id: string
  ticker?: string | null
  company_name?: string | null
  shares: number | string
  average_buy_price: number | string
  current_price?: number | string | null
  market_value?: number | string | null
  weight_pct?: number | string | null
}

export interface PortfolioResponse {
  id: string
  short_id?: string | null
  user_id: string
  name: string
  description?: string | null
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
  holdings_count: number
  total_market_value?: number | string | null
}

export interface PortfolioDetailResponse extends PortfolioResponse {
  holdings: HoldingSummary[]
}

export interface PaginatedPortfolioResponse {
  items: PortfolioResponse[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface PortfolioCreatePayload {
  name: string
  description?: string
  currency?: string
}

export interface MonitoringTriggerRequest {
  specific_tickers?: string[] | null
  max_news_per_target?: number
  max_filings_per_target?: number
  include_filings?: boolean
  include_news?: boolean
  persist_alerts?: boolean
}

export interface DiscoveredEventItem {
  company_name?: string | null
  ticker?: string | null
  title: string
  url?: string | null
  source_name?: string | null
  publication_date?: string | null
  snippet?: string | null
  event_category?: string | null
  relevance_score?: number | null
}

export interface VerifiedEventItem {
  company_name?: string | null
  ticker?: string | null
  canonical_title: string
  verified_summary: string
  event_type?: string | null
  sentiment?: string | null
  verification_status?: string | null
  credibility_score?: number | null
  primary_source_url?: string | null
  source_name?: string | null
  published_date?: string | null
  facts?: any[]
  speculative_claims?: any[]
}

export interface HoldingImpactItem {
  ticker: string
  company_name: string
  holding_weight_pct?: number | null
  holding_market_value?: number | null
  direct_exposure: boolean
  indirect_exposure_reason?: string | null
  event_title: string
  event_type: string
  impact_direction: string
  impact_severity: string
  impact_score?: number | null
  weighted_portfolio_risk?: number | null
  deterministic_rationale?: string | null
}

export interface StructuredAlertSummaryItem {
  alert_id?: string | null
  ticker?: string | null
  title: string
  alert_type: string
  severity: string
  message: string
  affected_holdings: string[]
  evidence_sources: string[]
  confidence: number
}

export interface MonitoringRunResponse {
  status: string
  portfolio_id: string
  completed_at?: string | null
  executive_summary?: string | null
  aggregate_risk_level?: string | null
  alerts_generated_count: number
  persisted_alerts_count: number
  errors: string[]
  non_advisory_notice: string
  discovery_summary?: string | null
  verification_summary?: string | null
  impact_summary?: string | null
  discovered_events?: DiscoveredEventItem[]
  verified_events?: VerifiedEventItem[]
  holding_impacts?: HoldingImpactItem[]
  alerts?: StructuredAlertSummaryItem[]
}

export interface HoldingCreatePayload {
  ticker: string
  company_name?: string
  shares: number
  average_buy_price: number
  current_price?: number
  notes?: string
}

export interface AlertStatusUpdateRequest {
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED'
}

export interface MonitoringAlertResponse {
  id: string
  short_id?: string | null
  portfolio_id: string
  company_id?: string | null
  research_event_id?: string | null
  alert_type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED' | 'DISMISSED' | string
  title: string
  message: string
  acknowledged_at?: string | null
  resolved_at?: string | null
  created_at: string
}

export interface PortfolioChatRequest {
  query: string
  history?: Array<{ role: string; content: string }>
}

export interface PortfolioChatResponse {
  portfolio_id: string
  portfolio_name: string
  query: string
  answer: string
  cited_holdings: string[]
  confidence: string
  non_advisory_notice: string
}

export interface HealthResponse {
  status: string
  project: string
  version: string
  environment: string
}

export interface DbHealthResponse {
  connected: boolean
  database: string
  latency_ms?: number
  error?: string
}

export interface TracingHealthResponse {
  configured: boolean
  tracing_enabled: boolean
  project?: string
  endpoint?: string
}

