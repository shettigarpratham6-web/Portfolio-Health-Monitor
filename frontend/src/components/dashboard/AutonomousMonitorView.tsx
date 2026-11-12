import React, { useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Download,
  ExternalLink,
  FileJson,
  FileText,
  Globe,
  Layers,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { listPortfolios, triggerMonitoring } from '../../api/portfolios'
import type { MonitoringRunResponse, PortfolioResponse } from '../../api/types'
import { useAuth } from '../../context/AuthContext'

interface AutonomousMonitorViewProps {
  initialPortfolioId?: string | null
  onNavigateToAlerts: (portfolioId: string) => void
}

type ReportTab = 'overview' | 'research' | 'verified' | 'impact' | 'alerts'

export const AutonomousMonitorView: React.FC<AutonomousMonitorViewProps> = ({
  initialPortfolioId,
  onNavigateToAlerts,
}) => {
  const { isAuthenticated, loginAsDemo } = useAuth()
  const [portfolios, setPortfolios] = useState<PortfolioResponse[]>([])
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string>(initialPortfolioId || '')

  // Options
  const [maxNews, setMaxNews] = useState<number>(3)
  const [includeFilings, setIncludeFilings] = useState<boolean>(true)
  const [includeNews, setIncludeNews] = useState<boolean>(true)
  const [persistAlerts, setPersistAlerts] = useState<boolean>(true)

  // State of execution
  const [isRunning, setIsRunning] = useState<boolean>(false)
  const [currentPhase, setCurrentPhase] = useState<string>('IDLE')
  const [runResult, setRunResult] = useState<MonitoringRunResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [activeReportTab, setActiveReportTab] = useState<ReportTab>('overview')

  useEffect(() => {
    if (isAuthenticated) {
      listPortfolios(1, 50).then((res) => {
        setPortfolios(res.items)
        if (res.items.length > 0 && !selectedPortfolioId) {
          setSelectedPortfolioId(res.items[0].id)
        }
      })
    }
  }, [isAuthenticated])

  const handleRun = async () => {
    if (!selectedPortfolioId) return
    setIsRunning(true)
    setRunError(null)
    setRunResult(null)
    setActiveReportTab('overview')

    // Visual sequence of execution phase states
    const phases = [
      'SUPERVISOR: Coordinating multi-agent execution sequence',
      'PORTFOLIO_AGENT: Ingesting active positions & base weights',
      'DISCOVERY_AGENT: Ingesting live market catalysts & official 10-K filings',
      'VERIFICATION_AGENT: Auditing source credibility & deduplication',
      'IMPACT_AGENT: Calculating deterministic financial risk matrices',
      'REPORTING_AGENT: Generating structured risk alerts & executive audit report',
    ]

    let pIndex = 0
    setCurrentPhase(phases[0])
    const phaseTimer = setInterval(() => {
      pIndex += 1
      if (pIndex < phases.length) {
        setCurrentPhase(phases[pIndex])
      }
    }, 1200)

    try {
      const result = await triggerMonitoring(selectedPortfolioId, {
        max_news_per_target: maxNews,
        max_filings_per_target: 2,
        include_filings: includeFilings,
        include_news: includeNews,
        persist_alerts: persistAlerts,
      })
      clearInterval(phaseTimer)
      setRunResult(result)
    } catch (err: any) {
      clearInterval(phaseTimer)
      setRunError(err.message || 'Execution failed during multi-agent surveillance pipeline.')
    } finally {
      setIsRunning(false)
    }
  }

  const handleExportReportTxt = () => {
    if (!runResult) return
    const targetPortfolio = portfolios.find(p => p.id === runResult.portfolio_id)
    const portfolioLabel = targetPortfolio?.name || (runResult.portfolio_id.includes('e555391f') ? 'My Investment Portfolio' : runResult.portfolio_id)
    
    let textContent = `================================================================================
PORTFOLIO HEALTH MONITOR — AUTONOMOUS SURVEILLANCE AUDIT REPORT
================================================================================
Generated At       : ${new Date().toISOString()}
Target Portfolio   : ${portfolioLabel}
Workflow Status    : ${runResult.status}
Completed At       : ${runResult.completed_at || 'N/A'}
Aggregate Risk     : ${runResult.aggregate_risk_level || 'LOW'}
Alerts Generated   : ${runResult.alerts_generated_count}
Persisted in DB    : ${runResult.persisted_alerts_count}
Exceptions Count   : ${runResult.errors.length}
--------------------------------------------------------------------------------
EXECUTIVE SUMMARY:
${runResult.executive_summary || 'No executive summary provided.'}

`

    if (runResult.discovered_events && runResult.discovered_events.length > 0) {
      textContent += `--------------------------------------------------------------------------------
1. INTERNET RESEARCH FINDINGS & SOURCES (${runResult.discovered_events.length} Items Discovered):
--------------------------------------------------------------------------------\n`
      runResult.discovered_events.forEach((ev, i) => {
        textContent += `[#${i + 1}] ${ev.title}\n`
        textContent += `     Target Holding : ${ev.ticker ? `${ev.ticker} (${ev.company_name || ''})` : 'General Market'}\n`
        textContent += `     Source / Date  : ${ev.source_name || 'Web'} | ${ev.publication_date || 'Recent'}\n`
        if (ev.url) textContent += `     Source URL     : ${ev.url}\n`
        if (ev.snippet) textContent += `     Gathered Intel : ${ev.snippet}\n`
        textContent += `\n`
      })
    }

    if (runResult.verified_events && runResult.verified_events.length > 0) {
      textContent += `--------------------------------------------------------------------------------
2. VERIFIED EVIDENCE & CORROBORATED INSIGHTS (${runResult.verified_events.length} Verified Events):
--------------------------------------------------------------------------------\n`
      runResult.verified_events.forEach((ev, i) => {
        textContent += `[#${i + 1}] ${ev.canonical_title}\n`
        textContent += `     Ticker / Sentiment: ${ev.ticker || 'N/A'} | ${ev.sentiment || 'NEUTRAL'} | Credibility: ${ev.credibility_score ? `${Math.round(ev.credibility_score * 100)}%` : 'Verified'}\n`
        textContent += `     Summary           : ${ev.verified_summary}\n`
        if (ev.primary_source_url) textContent += `     Primary Source    : ${ev.primary_source_url}\n`
        if (ev.facts && ev.facts.length > 0) {
          textContent += `     Corroborated Facts:\n`
          ev.facts.forEach(f => {
            const stmt = typeof f === 'string' ? f : f?.statement || JSON.stringify(f)
            textContent += `       * ${stmt}\n`
          })
        }
        textContent += `\n`
      })
    }

    if (runResult.holding_impacts && runResult.holding_impacts.length > 0) {
      textContent += `--------------------------------------------------------------------------------
3. ASSET EXPOSURE & IMPACT ANALYSIS (${runResult.holding_impacts.length} Evaluated Holdings):
--------------------------------------------------------------------------------\n`
      if (runResult.impact_summary) {
        textContent += `Overall Impact Summary: ${runResult.impact_summary}\n\n`
      }
      runResult.holding_impacts.forEach((imp, i) => {
        textContent += `[#${i + 1}] ${imp.ticker} (${imp.company_name})\n`
        textContent += `     Holding Weight : ${imp.holding_weight_pct ? `${imp.holding_weight_pct}%` : 'N/A'} | Market Value: $${imp.holding_market_value || 0}\n`
        textContent += `     Severity/Risk  : ${imp.impact_severity} | Direction: ${imp.impact_direction} | Score: ${imp.impact_score}\n`
        textContent += `     Analysis       : ${imp.deterministic_rationale || 'N/A'}\n\n`
      })
    }

    textContent += `--------------------------------------------------------------------------------
REGULATORY NON-ADVISORY MANDATE (SEC / FINRA):
${runResult.non_advisory_notice}
================================================================================
Verified by Autonomous Deterministic Execution Engine & Verified Protocols.
`
    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeFileId = runResult.portfolio_id.replace('port_e555391f', 'portfolio').slice(0, 8)
    link.download = `portfolio-audit-report-${safeFileId}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleExportAuditJson = () => {
    if (!runResult) return
    const blob = new Blob([JSON.stringify(runResult, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeFileId = runResult.portfolio_id.replace('port_e555391f', 'portfolio').slice(0, 8)
    link.download = `portfolio-audit-log-${safeFileId}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (!isAuthenticated) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto text-emerald-800">
          <Sparkles className="w-8 h-8" />
        </div>
        <h3 className="text-xl font-bold text-neutral-900 font-sans">
          Sign In to Run Autonomous Surveillance
        </h3>
        <p className="text-sm text-neutral-500 max-w-md mx-auto">
          The multi-agent intelligence workflow requires an authenticated investor session to access portfolio holdings.
        </p>
        <button
          onClick={loginAsDemo}
          className="bg-black hover:bg-neutral-800 text-white px-6 py-3 rounded-full text-xs font-semibold shadow-xs transition-all cursor-pointer"
        >
          1-Click Instant Demo Login
        </button>
      </div>
    )
  }

  const discoveredCount = runResult?.discovered_events?.length || 0
  const verifiedCount = runResult?.verified_events?.length || 0
  const impactsCount = runResult?.holding_impacts?.length || 0
  const alertsCount = runResult?.alerts?.length || runResult?.alerts_generated_count || 0

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-8 py-8 space-y-8 animate-in fade-in duration-300">
      
      {/* Title Bar */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1 rounded-full text-xs font-semibold">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Autonomous Multi-Agent Engine</span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-extrabold text-neutral-950 font-sans tracking-tight">
          Autonomous Portfolio Monitoring Workflow
        </h2>
        <p className="text-sm text-neutral-500 max-w-2xl">
          Dispatches all 6 specialized agents in sequence to identify market catalysts from the web,
          calculate mathematical asset exposure, and persist verified risk alerts.
        </p>
      </div>

      {/* Control Panel Card */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-neutral-200 shadow-sm space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-end">
          
          {/* Portfolio Target Selector */}
          <div className="md:col-span-5 space-y-2">
            <label className="block text-xs font-bold text-neutral-900 uppercase tracking-wider">
              Select Target Portfolio:
            </label>
            <select
              value={selectedPortfolioId}
              onChange={(e) => setSelectedPortfolioId(e.target.value)}
              disabled={isRunning || portfolios.length === 0}
              className="w-full px-4 py-3 bg-neutral-50 border border-neutral-200 rounded-2xl text-xs font-semibold text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
            >
              {portfolios.map((p) => {
                const showShortId = p.short_id && p.short_id !== 'port_e555391f'
                return (
                  <option key={p.id} value={p.id}>
                    {p.name}{showShortId ? ` (${p.short_id})` : ''} — {p.holdings_count} Holdings
                  </option>
                )
              })}
            </select>
          </div>

          {/* Max News slider/input */}
          <div className="md:col-span-3 space-y-2">
            <label className="block text-xs font-bold text-neutral-900 uppercase tracking-wider">
              News / Filings per Asset:
            </label>
            <input
              type="number"
              min={1}
              max={10}
              value={maxNews}
              onChange={(e) => setMaxNews(Number(e.target.value))}
              disabled={isRunning}
              className="w-full px-4 py-3 bg-neutral-50 border border-neutral-200 rounded-2xl text-xs font-semibold text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
            />
          </div>

          {/* Launch Button */}
          <div className="md:col-span-4">
            <button
              onClick={handleRun}
              disabled={isRunning || !selectedPortfolioId}
              className="w-full bg-black hover:bg-neutral-800 disabled:opacity-50 text-white py-3.5 rounded-2xl text-xs font-bold tracking-tight flex items-center justify-center gap-2 shadow-md transition-all active:scale-98 cursor-pointer"
            >
              {isRunning ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Agents Executing...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current text-emerald-400" />
                  <span>Start Autonomous Monitoring</span>
                </>
              )}
            </button>
          </div>

        </div>

        {/* Toggles Row */}
        <div className="flex flex-wrap items-center gap-6 pt-2 border-t border-neutral-100 text-xs font-medium text-neutral-700">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeFilings}
              onChange={(e) => setIncludeFilings(e.target.checked)}
              disabled={isRunning}
              className="w-4 h-4 accent-black rounded"
            />
            <span>Include SEC 10-K/10-Q Filings</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeNews}
              onChange={(e) => setIncludeNews(e.target.checked)}
              disabled={isRunning}
              className="w-4 h-4 accent-black rounded"
            />
            <span>Include Real-Time Financial News</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={persistAlerts}
              onChange={(e) => setPersistAlerts(e.target.checked)}
              disabled={isRunning}
              className="w-4 h-4 accent-black rounded"
            />
            <span>Persist Risk Alerts to History</span>
          </label>
        </div>
      </div>

      {/* Live Pipeline State Monitor Banner */}
      {isRunning && (
        <div className="bg-emerald-950 text-white rounded-3xl p-6 sm:p-8 space-y-4 shadow-xl border border-emerald-800 animate-in fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-300">
                Active Execution Stage
              </span>
            </div>
            <span className="text-xs font-mono text-emerald-400">
              State Checkpoint: Active
            </span>
          </div>

          <div className="text-base sm:text-lg font-bold font-mono text-white">
            {currentPhase}
          </div>

          <div className="w-full bg-emerald-900/60 h-2 rounded-full overflow-hidden">
            <div className="bg-emerald-400 h-full w-2/3 animate-pulse rounded-full" />
          </div>
        </div>
      )}

      {/* Error Banner */}
      {runError && (
        <div className="p-4 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-2xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">Workflow Failed</div>
            <div className="mt-0.5">{runError}</div>
          </div>
        </div>
      )}

      {/* Comprehensive Results Report */}
      {runResult && (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-neutral-200 shadow-xl space-y-8 animate-in fade-in slide-in-from-bottom-2">
          
          {/* Result Header & Status */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-6 border-b border-neutral-100 gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{runResult.status}</span>
                </span>
                <span className="text-xs text-neutral-400 font-mono flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Completed: {runResult.completed_at ? new Date(runResult.completed_at).toLocaleTimeString() : 'Just now'}</span>
                </span>
              </div>
              <h3 className="text-xl sm:text-2xl font-extrabold text-neutral-950 font-sans mt-2">
                Autonomous Intelligence Surveillance Report
              </h3>
              <p className="text-xs text-neutral-500 mt-0.5">
                Comprehensive evaluation of web intelligence, primary sources, verified evidence, and portfolio risk.
              </p>
            </div>

            <div className="flex items-center gap-2 bg-[#fbfaf7] px-4 py-2 rounded-2xl border border-neutral-200">
              <span className="text-xs font-bold text-neutral-500 uppercase tracking-wider">
                Aggregate Risk:
              </span>
              <span className={`px-3.5 py-1 rounded-full text-xs font-extrabold tracking-wider uppercase ${
                runResult.aggregate_risk_level === 'CRITICAL'
                  ? 'bg-rose-100 text-rose-800 border border-rose-300'
                  : runResult.aggregate_risk_level === 'HIGH'
                  ? 'bg-amber-100 text-amber-800 border border-amber-300'
                  : 'bg-emerald-100 text-emerald-800 border border-emerald-300'
              }`}>
                {runResult.aggregate_risk_level || 'LOW'}
              </span>
            </div>
          </div>

          {/* Metric Highlights Overview Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 bg-neutral-50 rounded-2xl border border-neutral-200/80">
              <div className="flex items-center justify-between text-neutral-400">
                <span className="text-[11px] font-semibold uppercase tracking-wider">Web Discoveries</span>
                <Globe className="w-4 h-4 text-purple-600" />
              </div>
              <div className="text-2xl font-black text-neutral-950 mt-1.5 font-sans">
                {discoveredCount}
              </div>
              <span className="text-[10px] text-neutral-400 font-medium">Catalysts & Filings</span>
            </div>

            <div className="p-4 bg-neutral-50 rounded-2xl border border-neutral-200/80">
              <div className="flex items-center justify-between text-neutral-400">
                <span className="text-[11px] font-semibold uppercase tracking-wider">Verified Evidence</span>
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-neutral-950 mt-1.5 font-sans">
                {verifiedCount}
              </div>
              <span className="text-[10px] text-neutral-400 font-medium">Corroborated Facts</span>
            </div>

            <div className="p-4 bg-neutral-50 rounded-2xl border border-neutral-200/80">
              <div className="flex items-center justify-between text-neutral-400">
                <span className="text-[11px] font-semibold uppercase tracking-wider">Holdings Analyzed</span>
                <Activity className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-2xl font-black text-neutral-950 mt-1.5 font-sans">
                {impactsCount}
              </div>
              <span className="text-[10px] text-neutral-400 font-medium">Deterministic Exposure</span>
            </div>

            <div className="p-4 bg-neutral-50 rounded-2xl border border-neutral-200/80">
              <div className="flex items-center justify-between text-neutral-400">
                <span className="text-[11px] font-semibold uppercase tracking-wider">Risk Alerts</span>
                <ShieldAlert className="w-4 h-4 text-rose-600" />
              </div>
              <div className="text-2xl font-black text-neutral-950 mt-1.5 font-sans">
                {alertsCount}
              </div>
              <span className="text-[10px] text-neutral-400 font-medium">Persisted to History</span>
            </div>
          </div>

          {/* Section Navigation Tabs */}
          <div className="flex flex-wrap items-center gap-2 border-b border-neutral-100 pb-3">
            <button
              onClick={() => setActiveReportTab('overview')}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeReportTab === 'overview'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-[#f1eee7]/80 text-neutral-700 hover:bg-[#e7e4dc]'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Executive Overview</span>
            </button>

            <button
              onClick={() => setActiveReportTab('research')}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeReportTab === 'research'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-[#f1eee7]/80 text-neutral-700 hover:bg-[#e7e4dc]'
              }`}
            >
              <Globe className="w-3.5 h-3.5" />
              <span>Internet Research Findings ({discoveredCount})</span>
            </button>

            <button
              onClick={() => setActiveReportTab('verified')}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeReportTab === 'verified'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-[#f1eee7]/80 text-neutral-700 hover:bg-[#e7e4dc]'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Verified Evidence & Insights ({verifiedCount})</span>
            </button>

            <button
              onClick={() => setActiveReportTab('impact')}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeReportTab === 'impact'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-[#f1eee7]/80 text-neutral-700 hover:bg-[#e7e4dc]'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5" />
              <span>Asset Exposure & Analysis ({impactsCount})</span>
            </button>

            <button
              onClick={() => setActiveReportTab('alerts')}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                activeReportTab === 'alerts'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-[#f1eee7]/80 text-neutral-700 hover:bg-[#e7e4dc]'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Risk Alerts ({alertsCount})</span>
            </button>
          </div>

          {/* TAB 1: EXECUTIVE OVERVIEW */}
          {activeReportTab === 'overview' && (
            <div className="space-y-6 animate-in fade-in duration-200">
              <div className="space-y-2">
                <div className="text-xs font-bold text-neutral-900 uppercase tracking-wider">
                  Executive Summary (Non-Advisory)
                </div>
                <div className="p-5 bg-[#fbfaf7] rounded-2xl border border-neutral-200/80 text-sm leading-relaxed text-neutral-800 font-sans whitespace-pre-line shadow-2xs">
                  {runResult.executive_summary}
                </div>
              </div>

              {/* Stage Summaries */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {runResult.discovery_summary && (
                  <div className="p-4 bg-purple-50/60 rounded-2xl border border-purple-200/70 space-y-1.5">
                    <div className="flex items-center gap-2 text-xs font-bold text-purple-900">
                      <Globe className="w-4 h-4 text-purple-700" />
                      <span>Web & Filing Discovery Intel</span>
                    </div>
                    <p className="text-xs text-purple-950 leading-relaxed">
                      {runResult.discovery_summary}
                    </p>
                  </div>
                )}

                {runResult.verification_summary && (
                  <div className="p-4 bg-emerald-50/60 rounded-2xl border border-emerald-200/70 space-y-1.5">
                    <div className="flex items-center gap-2 text-xs font-bold text-emerald-900">
                      <ShieldCheck className="w-4 h-4 text-emerald-700" />
                      <span>Verification & Corroboration Intel</span>
                    </div>
                    <p className="text-xs text-emerald-950 leading-relaxed">
                      {runResult.verification_summary}
                    </p>
                  </div>
                )}
              </div>

              {runResult.impact_summary && (
                <div className="p-4 bg-blue-50/60 rounded-2xl border border-blue-200/70 space-y-1.5">
                  <div className="flex items-center gap-2 text-xs font-bold text-blue-900">
                    <Activity className="w-4 h-4 text-blue-700" />
                    <span>Portfolio Exposure Summary</span>
                  </div>
                  <p className="text-xs text-blue-950 leading-relaxed">
                    {runResult.impact_summary}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: INTERNET RESEARCH FINDINGS & SOURCES */}
          {activeReportTab === 'research' && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-neutral-950">
                    Live Discovered Internet Catalysts & Regulatory Filings
                  </h4>
                  <p className="text-xs text-neutral-500">
                    Raw news articles, SEC disclosures, and financial press releases indexed live from the internet.
                  </p>
                </div>
                <span className="text-xs font-mono font-semibold text-neutral-400">
                  {discoveredCount} Sources Discovered
                </span>
              </div>

              {runResult.discovered_events && runResult.discovered_events.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {runResult.discovered_events.map((ev, idx) => (
                    <div
                      key={idx}
                      className="p-5 bg-[#fbfaf7] rounded-2xl border border-neutral-200/90 shadow-2xs hover:shadow-sm transition-all space-y-3 flex flex-col justify-between"
                    >
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            {ev.ticker && (
                              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-neutral-900 text-white font-mono">
                                {ev.ticker}
                              </span>
                            )}
                            <span className="text-xs font-semibold text-neutral-700 truncate">
                              {ev.company_name || 'Market Catalyst'}
                            </span>
                          </div>
                          {ev.event_category && (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-purple-100 text-purple-800 uppercase tracking-wider font-mono">
                              {ev.event_category}
                            </span>
                          )}
                        </div>

                        <h5 className="text-sm font-bold text-neutral-950 font-sans leading-snug">
                          {ev.title}
                        </h5>

                        {ev.snippet && (
                          <p className="text-xs text-neutral-600 leading-relaxed line-clamp-3 bg-white p-3 rounded-xl border border-neutral-200/60 font-sans">
                            "{ev.snippet}"
                          </p>
                        )}
                      </div>

                      <div className="pt-2 border-t border-neutral-200/60 flex items-center justify-between text-[11px] text-neutral-500 font-mono">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-neutral-800">
                            {ev.source_name || 'Online Source'}
                          </span>
                          {ev.publication_date && (
                            <span>· {ev.publication_date}</span>
                          )}
                        </div>

                        {ev.url && (
                          <a
                            href={ev.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-emerald-700 hover:text-emerald-900 font-semibold transition-colors"
                          >
                            <span>Inspect Source</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 bg-neutral-50 rounded-2xl border border-neutral-200 text-center text-xs text-neutral-500">
                  No external market catalysts met the critical relevance threshold during this execution pass.
                </div>
              )}
            </div>
          )}

          {/* TAB 3: VERIFIED EVIDENCE & INSIGHTS */}
          {activeReportTab === 'verified' && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-neutral-950">
                    Corroborated Evidence & Factual Cross-Examination
                  </h4>
                  <p className="text-xs text-neutral-500">
                    Audited facts separated from noise and unverified speculation with cryptographic deduplication.
                  </p>
                </div>
                <span className="text-xs font-mono font-semibold text-neutral-400">
                  {verifiedCount} Verified Events
                </span>
              </div>

              {runResult.verified_events && runResult.verified_events.length > 0 ? (
                <div className="space-y-4">
                  {runResult.verified_events.map((ev, idx) => {
                    const isBullish = ev.sentiment?.toUpperCase() === 'BULLISH' || ev.sentiment?.toUpperCase() === 'POSITIVE'
                    const isBearish = ev.sentiment?.toUpperCase() === 'BEARISH' || ev.sentiment?.toUpperCase() === 'NEGATIVE'
                    const credPct = ev.credibility_score ? Math.round(ev.credibility_score * 100) : 95

                    return (
                      <div
                        key={idx}
                        className="p-5 sm:p-6 bg-[#fbfaf7] rounded-2xl border border-neutral-200/90 shadow-2xs space-y-4"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-neutral-200/60">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              {ev.ticker && (
                                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-neutral-900 text-white font-mono">
                                  {ev.ticker}
                                </span>
                              )}
                              <span className="text-xs font-semibold text-neutral-600">
                                {ev.company_name || 'Corroborated Evidence'}
                              </span>
                              {ev.event_type && (
                                <span className="text-[10px] font-mono font-bold bg-neutral-200/80 text-neutral-700 px-2 py-0.5 rounded-full">
                                  {ev.event_type}
                                </span>
                              )}
                            </div>
                            <h5 className="text-base font-bold text-neutral-950 font-sans">
                              {ev.canonical_title}
                            </h5>
                          </div>

                          <div className="flex items-center gap-2">
                            {ev.sentiment && (
                              <span className={`px-3 py-1 rounded-full text-xs font-extrabold uppercase font-mono ${
                                isBullish
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : isBearish
                                  ? 'bg-rose-100 text-rose-800'
                                  : 'bg-blue-100 text-blue-800'
                              }`}>
                                {ev.sentiment}
                              </span>
                            )}
                            <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 font-mono">
                              {credPct}% Credibility
                            </span>
                          </div>
                        </div>

                        {/* Verified Narrative */}
                        <div className="space-y-1">
                          <span className="text-[11px] font-bold text-neutral-500 uppercase tracking-wider font-mono">
                            Verified Summary & Context
                          </span>
                          <p className="text-xs sm:text-sm text-neutral-800 leading-relaxed font-sans">
                            {ev.verified_summary}
                          </p>
                        </div>

                        {/* Corroborated Facts & Speculative Claims */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                          {ev.facts && ev.facts.length > 0 && (
                            <div className="p-3.5 bg-emerald-50/50 rounded-xl border border-emerald-200/60 space-y-2">
                              <span className="text-[11px] font-bold text-emerald-900 uppercase tracking-wider flex items-center gap-1 font-mono">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                                <span>Corroborated Facts</span>
                              </span>
                              <div className="space-y-1.5 text-xs text-emerald-950">
                                {ev.facts.map((fact, fIdx) => {
                                  const textVal = typeof fact === 'string' ? fact : fact?.statement || JSON.stringify(fact)
                                  return (
                                    <div key={fIdx} className="flex items-start gap-1.5">
                                      <span className="text-emerald-600 font-bold">•</span>
                                      <span>{textVal}</span>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          )}

                          {ev.speculative_claims && ev.speculative_claims.length > 0 && (
                            <div className="p-3.5 bg-amber-50/50 rounded-xl border border-amber-200/60 space-y-2">
                              <span className="text-[11px] font-bold text-amber-900 uppercase tracking-wider flex items-center gap-1 font-mono">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
                                <span>Unconfirmed / Speculative Claims</span>
                              </span>
                              <div className="space-y-1.5 text-xs text-amber-950">
                                {ev.speculative_claims.map((claim, cIdx) => (
                                  <div key={cIdx} className="flex items-start gap-1.5">
                                    <span className="text-amber-600 font-bold">•</span>
                                    <span>{claim}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Primary Source Citation */}
                        {ev.primary_source_url && (
                          <div className="pt-2 flex items-center justify-between text-xs text-neutral-500 font-mono">
                            <span>Primary Verified Source: {ev.source_name || 'Financial Wire'}</span>
                            <a
                              href={ev.primary_source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-emerald-700 hover:text-emerald-900 font-semibold"
                            >
                              <span>View Original Article</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="p-8 bg-neutral-50 rounded-2xl border border-neutral-200 text-center text-xs text-neutral-500">
                  No verified events were flagged for escalation in this monitoring window.
                </div>
              )}
            </div>
          )}

          {/* TAB 4: ASSET EXPOSURE & IMPACT ANALYSIS */}
          {activeReportTab === 'impact' && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-neutral-950">
                    Deterministic Asset Exposure & Portfolio Vulnerability
                  </h4>
                  <p className="text-xs text-neutral-500">
                    Mathematical mapping of verified catalysts across current portfolio asset positions.
                  </p>
                </div>
                <span className="text-xs font-mono font-semibold text-neutral-400">
                  {impactsCount} Positions Evaluated
                </span>
              </div>

              {runResult.impact_summary && (
                <div className="p-4 bg-neutral-50 rounded-2xl border border-neutral-200 text-xs text-neutral-800 font-sans leading-relaxed">
                  <span className="font-bold block mb-1">Impact Analysis Summary:</span>
                  {runResult.impact_summary}
                </div>
              )}

              {runResult.holding_impacts && runResult.holding_impacts.length > 0 ? (
                <div className="space-y-3">
                  {runResult.holding_impacts.map((imp, idx) => {
                    const isCrit = imp.impact_severity?.toUpperCase() === 'CRITICAL'
                    const isHigh = imp.impact_severity?.toUpperCase() === 'HIGH'
                    const isPositive = imp.impact_direction?.toUpperCase() === 'POSITIVE' || imp.impact_direction?.toUpperCase() === 'BULLISH'

                    return (
                      <div
                        key={idx}
                        className="p-5 bg-[#fbfaf7] rounded-2xl border border-neutral-200/90 shadow-2xs space-y-3"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            <span className="px-3 py-1 rounded-full text-xs font-bold bg-neutral-950 text-white font-mono">
                              {imp.ticker}
                            </span>
                            <span className="text-sm font-bold text-neutral-900 font-sans">
                              {imp.company_name}
                            </span>
                            {imp.holding_weight_pct && (
                              <span className="text-xs font-mono text-neutral-500 bg-white px-2 py-0.5 rounded-full border border-neutral-200">
                                {imp.holding_weight_pct}% Portfolio Weight
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono ${
                              isCrit
                                ? 'bg-rose-100 text-rose-800'
                                : isHigh
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-emerald-100 text-emerald-800'
                            }`}>
                              {imp.impact_severity}
                            </span>
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono ${
                              isPositive ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                            }`}>
                              {imp.impact_direction}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-neutral-100 text-neutral-700">
                              Score: {imp.impact_score || 0}
                            </span>
                          </div>
                        </div>

                        <div className="text-xs text-neutral-700 space-y-1">
                          <div className="font-semibold text-neutral-900">
                            Catalyst: {imp.event_title} ({imp.event_type})
                          </div>
                          <p className="leading-relaxed bg-white p-3 rounded-xl border border-neutral-200/60 font-sans text-neutral-800">
                            {imp.deterministic_rationale}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center justify-between pt-2 border-t border-neutral-200/60 text-[11px] font-mono text-neutral-500">
                          <span>
                            Exposure Channel: {imp.direct_exposure ? 'Direct Asset Holding' : `Indirect (${imp.indirect_exposure_reason || 'Supply Chain'})`}
                          </span>
                          <span>
                            Weighted Risk Factor: {imp.weighted_portfolio_risk ? imp.weighted_portfolio_risk.toFixed(2) : '0.00'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="p-8 bg-neutral-50 rounded-2xl border border-neutral-200 text-center text-xs text-neutral-500">
                  All holdings remain within normal mathematical risk parameters.
                </div>
              )}
            </div>
          )}

          {/* TAB 5: GENERATED RISK ALERTS */}
          {activeReportTab === 'alerts' && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-neutral-950">
                    Generated Risk Alerts & Incident Triage
                  </h4>
                  <p className="text-xs text-neutral-500">
                    Actionable incident records persisted into database storage.
                  </p>
                </div>
                <span className="text-xs font-mono font-semibold text-neutral-400">
                  {alertsCount} Structured Alerts
                </span>
              </div>

              {runResult.alerts && runResult.alerts.length > 0 ? (
                <div className="space-y-3">
                  {runResult.alerts.map((al, idx) => {
                    const isCrit = al.severity === 'CRITICAL'
                    const isHigh = al.severity === 'HIGH'
                    return (
                      <div
                        key={idx}
                        className={`p-5 rounded-2xl border space-y-2.5 transition-all ${
                          isCrit
                            ? 'bg-rose-50/50 border-rose-200/90'
                            : isHigh
                            ? 'bg-amber-50/50 border-amber-200/90'
                            : 'bg-white border-neutral-200/90'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono ${
                              isCrit
                                ? 'bg-rose-100 text-rose-800'
                                : isHigh
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-blue-100 text-blue-800'
                            }`}>
                              {al.severity}
                            </span>
                            {al.ticker && (
                              <span className="text-xs font-bold text-neutral-900 font-mono">
                                {al.ticker}
                              </span>
                            )}
                            <span className="text-xs font-bold text-neutral-950 font-sans">
                              {al.title}
                            </span>
                          </div>
                          <span className="text-[10px] font-mono text-neutral-500 bg-white px-2 py-0.5 rounded-full border border-neutral-200">
                            {al.alert_type}
                          </span>
                        </div>

                        <p className="text-xs text-neutral-800 leading-relaxed font-sans">
                          {al.message}
                        </p>

                        {al.affected_holdings && al.affected_holdings.length > 0 && (
                          <div className="flex items-center gap-2 pt-1 text-[11px] text-neutral-600">
                            <span className="font-semibold">Affected Holdings:</span>
                            <div className="flex gap-1.5">
                              {al.affected_holdings.map((h, hIdx) => (
                                <span key={hIdx} className="bg-white px-2 py-0.5 rounded-md border border-neutral-200 text-neutral-900 font-mono text-[10px] font-bold">
                                  {h}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="p-8 bg-neutral-50 rounded-2xl border border-neutral-200 text-center text-xs text-neutral-500">
                  {runResult.alerts_generated_count > 0
                    ? `${runResult.alerts_generated_count} alerts were generated and persisted to database.`
                    : 'No risk alerts triggered for this surveillance pass.'}
                </div>
              )}
            </div>
          )}

          {/* SEC Non-Advisory Notice */}
          <div className="p-4 bg-amber-50/70 border border-amber-200/80 rounded-2xl flex items-start gap-3 text-xs text-amber-900">
            <ShieldCheck className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold">SEC Regulatory Notice & Non-Advisory Mandate</div>
              <p className="mt-1 leading-relaxed opacity-90">
                {runResult.non_advisory_notice}
              </p>
            </div>
          </div>

          {/* Export & Action Footer */}
          <div className="pt-3 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleExportReportTxt}
                className="bg-[#f1eee7] hover:bg-[#e6e2d6] text-neutral-800 px-4 py-2 rounded-full text-xs font-semibold flex items-center gap-1.5 shadow-xs cursor-pointer transition-all"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download Detailed Audit (.txt)</span>
              </button>

              <button
                onClick={handleExportAuditJson}
                className="bg-[#f1eee7] hover:bg-[#e6e2d6] text-neutral-800 px-4 py-2 rounded-full text-xs font-semibold flex items-center gap-1.5 shadow-xs cursor-pointer transition-all"
              >
                <FileJson className="w-3.5 h-3.5" />
                <span>Export Full Data (.json)</span>
              </button>
            </div>

            <button
              onClick={() => onNavigateToAlerts(selectedPortfolioId)}
              className="bg-black hover:bg-neutral-800 text-white px-6 py-2.5 rounded-full text-xs font-semibold flex items-center gap-2 shadow-xs cursor-pointer transition-all"
            >
              <span>View Persisted Alerts</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

        </div>
      )}

    </div>
  )
}
