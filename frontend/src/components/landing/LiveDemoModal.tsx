import React, { useState } from 'react'
import { X, Play, CheckCircle2, AlertTriangle, ShieldCheck, Database, Search, Cpu, Sparkles } from 'lucide-react'

interface LiveDemoModalProps {
  isOpen: boolean
  onClose: () => void
  onNavigateToMonitor: () => void
}

interface Step {
  id: number
  agent: string
  tool: string
  status: 'pending' | 'running' | 'completed'
  output: string
  icon: any
  badgeColor: string
}

export const LiveDemoModal: React.FC<LiveDemoModalProps> = ({
  isOpen,
  onClose,
  onNavigateToMonitor,
}) => {
  const [selectedScenario, setSelectedScenario] = useState<string>('nvda')
  const [isRunning, setIsRunning] = useState<boolean>(false)
  const [activeStepIndex, setActiveStepIndex] = useState<number>(-1)

  const scenarios: Record<string, { title: string; query: string; steps: Step[] }> = {
    nvda: {
      title: 'NVIDIA Supply Chain Bottleneck Analysis',
      query: 'Evaluate impact of Taiwan earthquake semiconductor delay on NVDA holding',
      steps: [
        {
          id: 1,
          agent: 'Supervisor Agent',
          tool: 'Multi-Agent Coordinator',
          status: 'pending',
          output: 'Formulated 5-stage sequential execution plan with active safeguards.',
          icon: Cpu,
          badgeColor: 'bg-emerald-500 text-white',
        },
        {
          id: 2,
          agent: 'Portfolio Intelligence Agent',
          tool: 'get_portfolio (Portfolio Intelligence Engine)',
          status: 'pending',
          output: 'Extracted position NVDA: 300 shares @ $125.00 ($37,500 market value). Portfolio weight: 25.0%.',
          icon: Database,
          badgeColor: 'bg-blue-500 text-white',
        },
        {
          id: 3,
          agent: 'News & Filing Discovery Agent',
          tool: 'search_market_news (Real-Time Financial News Stream)',
          status: 'pending',
          output: 'Discovered TSMC fab disruption report & NVDA Form 8-K disclosures regarding packaging backlog.',
          icon: Search,
          badgeColor: 'bg-purple-500 text-white',
        },
        {
          id: 4,
          agent: 'Research Verification Agent',
          tool: 'verify_news_credibility & detect_duplicate_events',
          status: 'pending',
          output: 'Event verified from 2 corroborating primary sources. Credibility score: 0.94. Verified integrity hash generated.',
          icon: ShieldCheck,
          badgeColor: 'bg-amber-500 text-white',
        },
        {
          id: 5,
          agent: 'Portfolio Impact Agent',
          tool: 'calculate_exposure (Deterministic Risk Engine)',
          status: 'pending',
          output: 'Direct position exposure: 25.00%. Supply chain bottleneck coefficient: 0.72. Risk level: CRITICAL.',
          icon: AlertTriangle,
          badgeColor: 'bg-rose-500 text-white',
        },
        {
          id: 6,
          agent: 'Alert & Reporting Agent',
          tool: 'create_alert (Secure Persistence Engine)',
          status: 'pending',
          output: 'Saved high severity risk alert to database. Formatted non-advisory executive brief for portfolio manager.',
          icon: Sparkles,
          badgeColor: 'bg-teal-500 text-white',
        },
      ],
    },
    aapl: {
      title: 'Apple Enterprise AI Corroboration',
      query: 'Verify Apple enterprise neural processor announcement & market sentiment',
      steps: [
        {
          id: 1,
          agent: 'Supervisor Agent',
          tool: 'Multi-Agent Coordinator',
          status: 'pending',
          output: 'Routing initial phase to Portfolio Agent for Apple asset allocation retrieval.',
          icon: Cpu,
          badgeColor: 'bg-emerald-500 text-white',
        },
        {
          id: 2,
          agent: 'Portfolio Intelligence Agent',
          tool: 'get_portfolio (Portfolio Intelligence Engine)',
          status: 'pending',
          output: 'AAPL: 400 shares @ $150.00 ($60,000 market value). Largest holding at 40.0% weight.',
          icon: Database,
          badgeColor: 'bg-blue-500 text-white',
        },
        {
          id: 3,
          agent: 'News & Filing Discovery Agent',
          tool: 'search_company_news (Real-Time Financial News Stream)',
          status: 'pending',
          output: 'Found press release and tech analyst reviews on Apple enterprise neural compute silicon.',
          icon: Search,
          badgeColor: 'bg-purple-500 text-white',
        },
        {
          id: 4,
          agent: 'Research Verification Agent',
          tool: 'verify_news_credibility',
          status: 'pending',
          output: 'Corroborated across 3 verified publications. Sentiment: BULLISH. Verification status: VERIFIED.',
          icon: ShieldCheck,
          badgeColor: 'bg-amber-500 text-white',
        },
        {
          id: 5,
          agent: 'Portfolio Impact Agent',
          tool: 'calculate_portfolio_impact',
          status: 'pending',
          output: 'Positive operational catalyst. Affected portfolio allocation: 40.0%. Severity: MEDIUM.',
          icon: CheckCircle2,
          badgeColor: 'bg-emerald-500 text-white',
        },
        {
          id: 6,
          agent: 'Alert & Reporting Agent',
          tool: 'create_alert & format_report',
          status: 'pending',
          output: 'Created informational update alert. Non-advisory notice appended.',
          icon: Sparkles,
          badgeColor: 'bg-teal-500 text-white',
        },
      ],
    },
  }

  const currentScenario = scenarios[selectedScenario] || scenarios.nvda

  const runSimulation = () => {
    setIsRunning(true)
    setActiveStepIndex(0)

    let current = 0
    const interval = setInterval(() => {
      current += 1
      if (current >= currentScenario.steps.length) {
        clearInterval(interval)
        setIsRunning(false)
        setActiveStepIndex(currentScenario.steps.length)
      } else {
        setActiveStepIndex(current)
      }
    }, 700)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-neutral-200 overflow-hidden">
        
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-neutral-100 flex items-center justify-between bg-[#fbfaf7]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-neutral-900 font-sans">
                Interactive Agent Execution Trace
              </h3>
              <p className="text-xs text-neutral-500">
                Observe intelligent agent coordination, parameter analysis, and deterministic calculations
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-neutral-100 hover:bg-neutral-200 text-neutral-500 flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Scenario Selector */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mr-2">
              Select Scenario:
            </span>
            <button
              onClick={() => {
                setSelectedScenario('nvda')
                setActiveStepIndex(-1)
              }}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all ${
                selectedScenario === 'nvda'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
              }`}
            >
              NVDA Taiwan Disruption (Critical)
            </button>
            <button
              onClick={() => {
                setSelectedScenario('aapl')
                setActiveStepIndex(-1)
              }}
              className={`px-4 py-2 rounded-full text-xs font-semibold transition-all ${
                selectedScenario === 'aapl'
                  ? 'bg-neutral-950 text-white shadow-xs'
                  : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
              }`}
            >
              AAPL Enterprise Silicon (Medium)
            </button>
          </div>

          {/* User Query Banner */}
          <div className="bg-[#f5f3ec] p-4 rounded-2xl border border-neutral-200/80">
            <div className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
              Trigger Prompt / Catalyst
            </div>
            <div className="text-sm font-semibold text-neutral-900 mt-1 font-mono">
              "{currentScenario.query}"
            </div>
          </div>

          {/* Stepped Timeline */}
          <div className="space-y-3">
            {currentScenario.steps.map((step, idx) => {
              const isPast = activeStepIndex > idx
              const isCurrent = activeStepIndex === idx
              const IconComp = step.icon

              return (
                <div
                  key={step.id}
                  className={`p-3.5 rounded-2xl border transition-all duration-300 ${
                    isCurrent
                      ? 'bg-emerald-50/70 border-emerald-300 ring-2 ring-emerald-400/20 shadow-sm'
                      : isPast
                      ? 'bg-white border-neutral-200'
                      : 'bg-neutral-50/60 border-neutral-200/50 opacity-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${step.badgeColor}`}>
                        Step {step.id}
                      </span>
                      <span className="text-xs font-bold text-neutral-900 font-sans">
                        {step.agent}
                      </span>
                      <span className="text-[11px] text-neutral-400 font-mono hidden sm:inline">
                        via {step.tool}
                      </span>
                    </div>

                    {isPast && (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Verified</span>
                      </span>
                    )}
                    {isCurrent && (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-blue-600 animate-pulse">
                        <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping" />
                        <span>Running...</span>
                      </span>
                    )}
                  </div>

                  <div className="mt-2 text-xs text-neutral-700 font-sans pl-1">
                    {isPast || isCurrent ? step.output : 'Waiting in graph queue...'}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 bg-[#fbfaf7] border-t border-neutral-100 flex items-center justify-between">
          <button
            onClick={onClose}
            className="text-xs font-medium text-neutral-600 hover:text-neutral-900 px-4 py-2"
          >
            Close
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={runSimulation}
              disabled={isRunning}
              className="bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white px-5 py-2.5 rounded-full text-xs font-semibold flex items-center gap-1.5 transition-all shadow-xs cursor-pointer"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isRunning ? 'Running Agent Steps...' : 'Re-run Simulation'}</span>
            </button>

            <button
              onClick={() => {
                onClose()
                onNavigateToMonitor()
              }}
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-full text-xs font-semibold flex items-center gap-1.5 transition-all shadow-xs cursor-pointer"
            >
              <span>Launch Live Monitor</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}

