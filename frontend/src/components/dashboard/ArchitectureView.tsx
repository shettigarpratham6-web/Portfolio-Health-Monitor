import React from 'react'
import {
  Code,
  Cpu,
  Database,
  ExternalLink,
  Layers,
  Lock,
  Search,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react'

export const ArchitectureView: React.FC = () => {
  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-8 py-8 space-y-8 animate-in fade-in duration-300">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-1.5 bg-[#f1eee7] px-3 py-1 rounded-full text-xs font-semibold text-neutral-800">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>System Architecture & Verification</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-neutral-950 font-sans tracking-tight">
            System Design & Multi-Agent Execution Blueprint
          </h2>
          <p className="text-sm text-neutral-500 max-w-2xl">
            Clean decoupling between AI reasoning, verified tool execution, deterministic financial math, and regulatory compliance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="bg-black hover:bg-neutral-800 text-white px-5 py-2.5 rounded-full text-xs font-semibold flex items-center gap-2 shadow-xs transition-all cursor-pointer"
          >
            <span>Swagger UI Docs</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* 4 Architectural Tiers */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-bold text-neutral-400">TIER 01</span>
            <Lock className="w-4 h-4 text-emerald-600" />
          </div>
          <h4 className="text-base font-bold text-neutral-950 font-sans">
            API & Guardrails
          </h4>
          <p className="text-xs text-neutral-600 leading-relaxed">
            Secure API with token-based authentication. Input guardrails actively block prompt injection,
            while output guardrails enforce statutory SEC non-advisory compliance.
          </p>
          <div className="text-[11px] font-mono text-neutral-500 pt-2 border-t border-neutral-100">
            Secure API · Token Auth · Strict Validation
          </div>
        </div>

        <div className="bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-bold text-neutral-400">TIER 02</span>
            <Cpu className="w-4 h-4 text-blue-600" />
          </div>
          <h4 className="text-base font-bold text-neutral-950 font-sans">
            Autonomous Agent Orchestrator
          </h4>
          <p className="text-xs text-neutral-600 leading-relaxed">
            Stateful directed workflow that orchestrates turn-taking across the 6 agents. Maintains an immutable
            typed state with bounded iteration protection (max 15 loops).
          </p>
          <div className="text-[11px] font-mono text-neutral-500 pt-2 border-t border-neutral-100">
            Multi-Agent Engine · State Coordination
          </div>
        </div>

        <div className="bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-bold text-neutral-400">TIER 03</span>
            <Zap className="w-4 h-4 text-purple-600" />
          </div>
          <h4 className="text-base font-bold text-neutral-950 font-sans">
            Domain Tool Protocol
          </h4>
          <p className="text-xs text-neutral-600 leading-relaxed">
            Standardized tool interface protocols. Agents never execute arbitrary database queries; all operations
            pass through parameter-validated tool interfaces with strict boundaries.
          </p>
          <div className="text-[11px] font-mono text-neutral-500 pt-2 border-t border-neutral-100">
            Tool Client Gateway · Market Feeds
          </div>
        </div>

        <div className="bg-white rounded-3xl p-6 border border-neutral-200/90 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-bold text-neutral-400">TIER 04</span>
            <Database className="w-4 h-4 text-amber-600" />
          </div>
          <h4 className="text-base font-bold text-neutral-950 font-sans">
            Persistence & Telemetry
          </h4>
          <p className="text-xs text-neutral-600 leading-relaxed">
            Enterprise relational database with structured records. Comprehensive distributed monitoring and execution logs.
          </p>
          <div className="text-[11px] font-mono text-neutral-500 pt-2 border-t border-neutral-100">
            Enterprise DB · Relational Models · Continuous Tracing
          </div>
        </div>

      </div>

      {/* Tool Servers Breakdown */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-neutral-200 shadow-sm space-y-6">
        <div>
          <h3 className="text-lg font-bold text-neutral-950 font-sans">
            Tool Service Ecosystem
          </h3>
          <p className="text-xs text-neutral-500 mt-0.5">
            Decoupled tool runners callable by agents via the in-process async gateway
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Database Server */}
          <div className="bg-[#fbfaf7] p-5 rounded-2xl border border-neutral-200/80 space-y-3">
            <div className="flex items-center gap-2 font-bold text-sm text-neutral-900 font-sans">
              <Database className="w-4 h-4 text-emerald-600" />
              <span>Database Service</span>
            </div>
            <div className="text-xs text-neutral-500 leading-relaxed">
              Provides parameterized queries for portfolio entities, allocations, and alerts.
            </div>
            <div className="space-y-1.5 pt-2">
              {[
                'get_portfolio',
                'get_company_profile',
                'save_monitoring_alert',
                'get_active_alerts',
                'save_research_event',
              ].map((tool) => (
                <div key={tool} className="text-xs font-mono bg-white px-2.5 py-1 rounded-lg border border-neutral-200/60 text-neutral-800">
                  {tool}
                </div>
              ))}
            </div>
          </div>

          {/* Research Server */}
          <div className="bg-[#fbfaf7] p-5 rounded-2xl border border-neutral-200/80 space-y-3">
            <div className="flex items-center gap-2 font-bold text-sm text-neutral-900 font-sans">
              <Search className="w-4 h-4 text-purple-600" />
              <span>Research Service</span>
            </div>
            <div className="text-xs text-neutral-500 leading-relaxed">
              Integrates real-time financial search and clean data parsing for market news and official regulatory filing indexing.
            </div>
            <div className="space-y-1.5 pt-2">
              {[
                'search_market_news',
                'search_company_news',
                'fetch_and_sanitize_webpage',
                'verify_source_credibility',
              ].map((tool) => (
                <div key={tool} className="text-xs font-mono bg-white px-2.5 py-1 rounded-lg border border-neutral-200/60 text-neutral-800">
                  {tool}
                </div>
              ))}
            </div>
          </div>

          {/* Analysis Server */}
          <div className="bg-[#fbfaf7] p-5 rounded-2xl border border-neutral-200/80 space-y-3">
            <div className="flex items-center gap-2 font-bold text-sm text-neutral-900 font-sans">
              <Cpu className="w-4 h-4 text-blue-600" />
              <span>Analysis Service</span>
            </div>
            <div className="text-xs text-neutral-500 leading-relaxed">
              Deterministic mathematical calculations for exposure percentages, concentration indexes, and deduplication.
            </div>
            <div className="space-y-1.5 pt-2">
              {[
                'calculate_portfolio_impact',
                'calculate_exposure',
                'detect_duplicate_events',
              ].map((tool) => (
                <div key={tool} className="text-xs font-mono bg-white px-2.5 py-1 rounded-lg border border-neutral-200/60 text-neutral-800">
                  {tool}
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>

    </div>
  )
}

