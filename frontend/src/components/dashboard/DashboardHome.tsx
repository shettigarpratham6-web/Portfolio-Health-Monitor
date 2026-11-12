import React, { useEffect, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  Layers,
  MessageSquare,
  Play,
  RefreshCw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { checkDbHealth, checkHealth, checkTracingHealth } from '../../api/health'
import { chatWithPortfolio, listPortfolios } from '../../api/portfolios'
import type {
  DbHealthResponse,
  HealthResponse,
  PortfolioChatResponse,
  PortfolioResponse,
  TracingHealthResponse,
} from '../../api/types'
import { useAuth } from '../../context/AuthContext'
import { AskCopilotButton } from '../common/AskCopilotButton'

interface DashboardHomeProps {
  onNavigate: (view: 'landing' | 'dashboard' | 'portfolios' | 'monitor' | 'alerts' | 'architecture') => void
  onSelectPortfolio: (id: string) => void
  onOpenAuth: (mode: 'login') => void
}

export const DashboardHome: React.FC<DashboardHomeProps> = ({
  onNavigate,
  onSelectPortfolio,
  onOpenAuth,
}) => {
  const { isAuthenticated, user, loginAsDemo } = useAuth()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [dbHealth, setDbHealth] = useState<DbHealthResponse | null>(null)
  const [tracingHealth, setTracingHealth] = useState<TracingHealthResponse | null>(null)
  const [portfolios, setPortfolios] = useState<PortfolioResponse[]>([])
  const [loading, setLoading] = useState<boolean>(true)

  // AI Portfolio Copilot Assistant State
  const [chatPortfolioId, setChatPortfolioId] = useState<string>('')
  const [chatQuery, setChatQuery] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatMessages, setChatMessages] = useState<
    Array<{ role: 'user' | 'assistant'; text: string; cited?: string[] }>
  >([
    {
      role: 'assistant',
      text: 'Hello! I am your Portfolio AI Copilot. Ask me anything about your holdings, supply chain bottlenecks, weight allocations, or active risk alerts.',
    },
  ])
  const [chatError, setChatError] = useState<string | null>(null)

  const quickPrompts = [
    'What are the biggest supply chain risks in my portfolio?',
    'Summarize total exposure and allocation weights.',
    'Explain why any holdings have active risk alerts.',
    'Which holding has the highest concentration risk?',
  ]

  const fetchData = async () => {
    setLoading(true)
    try {
      const [h, dbH, trH] = await Promise.allSettled([
        checkHealth(),
        checkDbHealth(),
        checkTracingHealth(),
      ])

      if (h.status === 'fulfilled') setHealth(h.value)
      if (dbH.status === 'fulfilled') setDbHealth(dbH.value)
      if (trH.status === 'fulfilled') setTracingHealth(trH.value)

      if (isAuthenticated) {
        const pRes = await listPortfolios(1, 10)
        setPortfolios(pRes.items)
        if (pRes.items.length > 0 && !chatPortfolioId) {
          setChatPortfolioId(pRes.items[0].id)
        }
      }
    } catch (err) {
      console.error('Dashboard data load error:', err)
    } finally {
      setLoading(false)
    }
  }

  // Client-side cache to avoid redundant network requests for identical queries
  const [queryCache, setQueryCache] = useState<Record<string, { answer: string; cited?: string[] }>>({})

  const handleSendChat = async (presetText?: string) => {
    const q = (presetText || chatQuery).trim()
    if (!q || !chatPortfolioId || chatLoading) return

    setChatMessages((prev) => [...prev, { role: 'user', text: q }])
    setChatQuery('')
    setChatError(null)

    const cacheKey = `${chatPortfolioId}:${q.toLowerCase()}`
    if (queryCache[cacheKey]) {
      const cached = queryCache[cacheKey]
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: cached.answer,
          cited: cached.cited,
        },
      ])
      return
    }

    setChatLoading(true)

    try {
      const res = await chatWithPortfolio(chatPortfolioId, { query: q })
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: res.answer,
          cited: res.cited_holdings,
        },
      ])
      setQueryCache((prev) => ({
        ...prev,
        [cacheKey]: { answer: res.answer, cited: res.cited_holdings },
      }))
    } catch (err: any) {
      setChatError(err.message || 'Failed to generate answer.')
    } finally {
      setChatLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [isAuthenticated])

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-8 py-8 space-y-8 animate-in fade-in duration-300">
      
      {/* Top Banner / Welcome */}
      <div className="bg-[#f2efe9] rounded-3xl p-6 sm:p-8 border border-neutral-200/80 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-xs">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-1.5 bg-white/80 px-3 py-1 rounded-full text-xs font-semibold text-neutral-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Autonomous Intelligence Engine Online</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-neutral-950 font-sans tracking-tight">
            Portfolio Health Command Center
          </h2>
          <p className="text-sm text-neutral-600 max-w-xl">
            {isAuthenticated
              ? `Logged in as ${user?.full_name || 'Pratham'}. Continuous filing and catalyst monitoring active.`
              : 'Sign in to access your investment portfolios, or test our live pipeline using a 1-click demo analyst session.'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {!isAuthenticated ? (
            <button
              onClick={loginAsDemo}
              className="bg-black hover:bg-neutral-800 text-white px-5 py-3 rounded-full text-xs font-semibold flex items-center gap-2 shadow-sm transition-all cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 text-lime-400" />
              <span>1-Click Demo Login</span>
            </button>
          ) : (
            <button
              onClick={() => onNavigate('monitor')}
              className="bg-black hover:bg-neutral-800 text-white px-5 py-3 rounded-full text-xs font-semibold flex items-center gap-2 shadow-sm transition-all cursor-pointer"
            >
              <Play className="w-3.5 h-3.5 fill-current text-emerald-400" />
              <span>Launch Live Monitor</span>
            </button>
          )}

          <button
            onClick={fetchData}
            title="Refresh System Health"
            className="w-10 h-10 bg-white hover:bg-neutral-100 rounded-full flex items-center justify-center text-neutral-700 border border-neutral-200 transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content Split: User Portfolios & Live Alert Highlights */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column (8 cols): Portfolios List */}
        <div className="lg:col-span-8 bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-100">
            <div className="flex items-center gap-2.5">
              <BarChart3 className="w-5 h-5 text-neutral-900" />
              <h3 className="text-lg font-bold text-neutral-950 font-sans">
                Active Investment Portfolios
              </h3>
            </div>
            <button
              onClick={() => onNavigate('portfolios')}
              className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 flex items-center gap-1 cursor-pointer"
            >
              <span>Manage all</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {!isAuthenticated ? (
            <div className="p-8 text-center bg-neutral-50 rounded-2xl border border-dashed border-neutral-200 space-y-3">
              <ShieldAlert className="w-8 h-8 text-neutral-400 mx-auto" />
              <div className="text-sm font-semibold text-neutral-800">Authentication Required</div>
              <p className="text-xs text-neutral-500 max-w-sm mx-auto">
                Sign in to view your real portfolio allocations, holding weights, and trigger agent evaluations.
              </p>
              <button
                onClick={loginAsDemo}
                className="bg-black text-white text-xs font-semibold px-5 py-2.5 rounded-full shadow-xs cursor-pointer hover:bg-neutral-800"
              >
                1-Click Instant Demo Login
              </button>
            </div>
          ) : portfolios.length === 0 ? (
            <div className="p-8 text-center bg-neutral-50 rounded-2xl border border-dashed border-neutral-200 space-y-2">
              <div className="text-sm font-semibold text-neutral-800">No portfolios created yet</div>
              <p className="text-xs text-neutral-500">Create your first portfolio to begin tracking live holdings.</p>
              <button
                onClick={() => onNavigate('portfolios')}
                className="bg-black text-white text-xs font-semibold px-5 py-2 rounded-full cursor-pointer"
              >
                Create Portfolio
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {portfolios.map((p) => (
                <div
                  key={p.id}
                  onClick={() => onSelectPortfolio(p.id)}
                  className="p-4 rounded-2xl border border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50/70 transition-all flex items-center justify-between cursor-pointer group"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-neutral-900 font-sans group-hover:text-black">
                        {p.name}
                      </span>
                      {p.short_id && p.short_id !== 'port_e555391f' && (
                        <span className="text-[10px] font-mono bg-neutral-100 text-neutral-600 px-2 py-0.5 rounded-full">
                          {p.short_id}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-neutral-500">
                      {p.description || 'Standard equity risk monitoring portfolio'}
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className="text-xs font-bold text-neutral-900">
                        {p.holdings_count} Holdings
                      </div>
                      <div className="text-[11px] text-neutral-500">
                        {p.currency}
                      </div>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-neutral-100 flex items-center justify-center text-neutral-500 group-hover:bg-neutral-950 group-hover:text-white transition-colors">
                      <ArrowRight className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column (4 cols): Quick Autonomous Launch & System Details */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Quick Monitor Action Card */}
          <div className="bg-[#f5f3ec] rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-neutral-500">
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>Autonomous Monitor</span>
            </div>
            <h4 className="text-lg font-bold text-neutral-950 font-sans leading-snug">
              Evaluate real-time filing & news impacts
            </h4>
            <p className="text-xs text-neutral-600 leading-relaxed">
              Triggers the 6-agent autonomous intelligence workflow to analyze recent regulatory filings,
              corroborate news credibility, and calculate portfolio exposure.
            </p>
            <button
              onClick={() => onNavigate('monitor')}
              className="w-full bg-black hover:bg-neutral-800 text-white py-3 rounded-2xl text-xs font-semibold flex items-center justify-center gap-2 shadow-xs transition-all cursor-pointer"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Launch Monitoring Pipeline</span>
            </button>
          </div>

          {/* Active Alerts Shortcut */}
          <div className="bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-neutral-900">Recent Alerts</span>
              <button
                onClick={() => onNavigate('alerts')}
                className="text-xs font-semibold text-emerald-700 hover:text-emerald-900"
              >
                View all →
              </button>
            </div>
            <div className="text-xs text-neutral-500 leading-relaxed">
              Persisted risk alerts are categorized by severity (CRITICAL, HIGH, MEDIUM)
              with deterministic exposure weights.
            </div>
          </div>

        </div>

      </div>

      {/* ================================================================ */}
      {/* AI PORTFOLIO RISK COPILOT ASSISTANT SECTION                     */}
      {/* ================================================================ */}
      {isAuthenticated && (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-neutral-200/90 shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-neutral-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-emerald-100 text-emerald-800 flex items-center justify-center shadow-xs">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-extrabold text-neutral-950 font-sans tracking-tight">
                    AI Portfolio Risk Copilot
                  </h3>
                  <span className="text-[10px] font-bold uppercase tracking-wider bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded-full">
                    Active Agent
                  </span>
                </div>
                <p className="text-xs text-neutral-500">
                  Ask natural language questions about your holdings, supply chain bottlenecks, and risk allocations.
                </p>
              </div>
            </div>

            {/* Target Portfolio Selector for Chat */}
            {portfolios.length > 0 && (
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <span className="text-xs font-semibold text-neutral-500 shrink-0">Context:</span>
                <select
                  value={chatPortfolioId}
                  onChange={(e) => setChatPortfolioId(e.target.value)}
                  className="px-3 py-1.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs font-semibold text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                >
                  {portfolios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.holdings_count} assets)
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Quick-Prompt Pills */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
              Suggested Questions
            </span>
            <div className="flex flex-wrap gap-2">
              {quickPrompts.map((prompt, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendChat(prompt)}
                  disabled={chatLoading || !chatPortfolioId}
                  className="bg-[#f5f3ec] hover:bg-[#eae6db] disabled:opacity-50 text-neutral-800 text-xs px-3.5 py-1.5 rounded-full border border-neutral-200/60 transition-colors cursor-pointer text-left"
                >
                  ⚡ {prompt}
                </button>
              ))}
            </div>
          </div>

          {/* Conversation Stream */}
          <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center shrink-0 text-xs font-bold shadow-xs">
                    <Sparkles className="w-4 h-4" />
                  </div>
                )}
                <div
                  className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-neutral-950 text-white rounded-br-xs shadow-xs'
                      : 'bg-[#faf9f5] text-neutral-900 border border-neutral-200/80 rounded-bl-xs'
                  }`}
                >
                  <p className="whitespace-pre-line">{msg.text}</p>
                  {msg.cited && msg.cited.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-neutral-200/60 flex items-center gap-1.5 text-[10px] text-neutral-500">
                      <span className="font-semibold text-neutral-700">Cited Holdings:</span>
                      {msg.cited.map((c) => (
                        <span
                          key={c}
                          className="bg-emerald-100 text-emerald-800 font-mono font-bold px-2 py-0.5 rounded-md"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {chatLoading && (
              <div className="flex items-center gap-3 text-xs text-neutral-500">
                <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center shrink-0 text-xs font-bold animate-pulse">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div className="bg-[#faf9f5] border border-neutral-200/80 rounded-2xl p-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                  <span>Synthesizing portfolio intelligence & SEC disclosures...</span>
                </div>
              </div>
            )}
          </div>

          {chatError && (
            <div className="p-3 bg-rose-50 text-rose-700 text-xs rounded-xl flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{chatError}</span>
            </div>
          )}

          {/* User Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleSendChat()
            }}
            className="flex items-center gap-2 pt-2"
          >
            <input
              type="text"
              value={chatQuery}
              onChange={(e) => setChatQuery(e.target.value)}
              disabled={chatLoading || !chatPortfolioId}
              placeholder={
                chatPortfolioId
                  ? 'Ask about your holdings, supply chain exposure, or alert ratings...'
                  : 'Select or create a portfolio to ask questions...'
              }
              className="flex-grow px-4 py-3 bg-neutral-50 border border-neutral-200 rounded-2xl text-xs text-neutral-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-black disabled:opacity-50"
            />
            <AskCopilotButton
              type="submit"
              disabled={chatLoading || !chatQuery.trim() || !chatPortfolioId}
            />
          </form>
        </div>
      )}

    </div>
  )
}

