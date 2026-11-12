import React, { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react'
import {
  Sparkles,
  Cpu,
  Bot,
  Layers,
  Bell,
  ShieldCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Zap,
} from 'lucide-react'

interface FeatureItem {
  id: string
  category: string
  title: string
  desc: string
  icon: React.ElementType
  badgeColor: string
  accentColor: string
  highlights: string[]
  metric: string
  metricLabel: string
}

const PLATFORM_FEATURES: FeatureItem[] = [
  {
    id: 'swarm',
    category: 'Autonomous Intelligence',
    title: 'Multi-Agent Autonomous Swarm',
    desc: 'Orchestrates 6 specialized intelligent agents to autonomously monitor your investment holdings, ingest official regulatory filings, and scan real-time market catalysts without human intervention.',
    icon: Sparkles,
    badgeColor: 'bg-emerald-100 text-emerald-800',
    accentColor: 'text-emerald-600',
    highlights: ['Continuous State Memory', 'Real-Time Market Intelligence', 'Automated Regulatory Filing Analysis'],
    metric: '6 Agents',
    metricLabel: 'Continuous Execution',
  },
  {
    id: 'math',
    category: 'Quantitative Analytics',
    title: 'Deterministic Financial Risk Engine',
    desc: 'Eliminates estimation errors by isolating financial calculations into deterministic mathematical algorithms. Computes exact exposure ratios, Herfindahl-Hirschman Concentration Index (HHI), and supply chain bottleneck matrices.',
    icon: Cpu,
    badgeColor: 'bg-blue-100 text-blue-800',
    accentColor: 'text-blue-600',
    highlights: ['100% Calculation Reliability', 'Concentration Index (HHI)', 'Deterministic Exposure Weights'],
    metric: '100%',
    metricLabel: 'Mathematical Precision',
  },
  {
    id: 'copilot',
    category: 'Conversational Risk Copilot',
    title: 'AI Portfolio Risk Copilot',
    desc: 'Interactive AI risk assistant designed for rapid, highly accurate answers. Ask natural language questions regarding single-stock concentration, supply chain vulnerabilities, and active market catalysts with cited evidence.',
    icon: Bot,
    badgeColor: 'bg-purple-100 text-purple-800',
    accentColor: 'text-purple-600',
    highlights: ['Dual-Layer Response Caching', 'Sub-100ms Fast-Path Queries', 'Intelligent Context Optimization'],
    metric: '< 100ms',
    metricLabel: 'Fast-Path Valuation',
  },
  {
    id: 'portfolios',
    category: 'Portfolio Management',
    title: 'Dynamic Asset & Holdings Tracking',
    desc: 'Create, monitor, and rebalance custom portfolios with real-time valuation calculations. Add positions using instant ticker chips, customize share counts and buy prices, and view consolidated capital allocation.',
    icon: Layers,
    badgeColor: 'bg-amber-100 text-amber-800',
    accentColor: 'text-amber-600',
    highlights: ['User-Scoped Portfolio Isolation', 'Interactive Ticker Autocomplete', 'Real-Time Market Value & Weights'],
    metric: 'Multi-Asset',
    metricLabel: 'Real-Time Valuation',
  },
  {
    id: 'alerts',
    category: 'Incident Lifecycle',
    title: 'Intelligent Risk Alerts & Triage',
    desc: 'Maintains structured risk alerts categorized by severity (Low, Medium, High, Critical) with full lifecycle state transitions. Acknowledge, investigate, and resolve alerts with permanent audit timestamps.',
    icon: Bell,
    badgeColor: 'bg-rose-100 text-rose-800',
    accentColor: 'text-rose-600',
    highlights: ['Enterprise Audit Persistence', 'Active, Acknowledged & Resolved States', 'Severity-Based Filtering'],
    metric: '4 Tiers',
    metricLabel: 'Severity Classification',
  },
  {
    id: 'compliance',
    category: 'Regulatory Compliance',
    title: 'Audit Exports & SEC Non-Advisory Mandate',
    desc: 'Certified statutory non-advisory compliance framework guaranteeing factual risk intelligence without prohibited trade recommendations. Export executive audit reports in formatted Text and machine-readable JSON with 1 click.',
    icon: ShieldCheck,
    badgeColor: 'bg-teal-100 text-teal-800',
    accentColor: 'text-teal-600',
    highlights: ['1-Click Audit Export (.txt / .json)', 'SEC / FINRA Mandate Disclaimers', 'Verified Integrity & Deduplication'],
    metric: 'SEC / FINRA',
    metricLabel: 'Compliant Architecture',
  },
]

// 3D Coverflow Constants
const PERSPECTIVE = 1600
const SCALE_STEP = 0.12
const MAX_VISIBLE = 2
const DEPTH = 220

export const WorkflowVisualizer: React.FC = () => {
  const [active, setActive] = useState(0)
  const [cardWidth, setCardWidth] = useState(380)
  const [cardHeight, setCardHeight] = useState(390)
  const n = PLATFORM_FEATURES.length
  const lockRef = useRef(false)

  // Fluid responsive dimensions
  useEffect(() => {
    const handleResize = () => {
      const w = window.innerWidth
      if (w < 640) {
        setCardWidth(Math.min(320, w - 48))
        setCardHeight(420)
      } else if (w < 1024) {
        setCardWidth(350)
        setCardHeight(400)
      } else {
        setCardWidth(380)
        setCardHeight(390)
      }
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const lock = useCallback(() => {
    lockRef.current = true
    window.setTimeout(() => {
      lockRef.current = false
    }, 450)
  }, [])

  const step = useCallback(
    (dir: number) => {
      if (lockRef.current) return
      lock()
      setActive((a) => (((a + dir) % n) + n) % n)
    },
    [n, lock]
  )

  const handleCardClick = useCallback(
    (i: number) => {
      if (lockRef.current) return
      lock()
      setActive((a) => (i === a ? (a + 1) % n : i))
    },
    [n, lock]
  )

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        step(1)
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        step(-1)
      }
    },
    [step]
  )

  const dur = 0.6
  const ease = 'cubic-bezier(0.22, 1, 0.36, 1)'
  const transitionCss = `transform ${dur}s ${ease}, opacity ${dur}s ${ease}, box-shadow ${dur}s ${ease}`

  const tilt = 12
  const sideTilt = 6
  const gap = 8

  return (
    <section className="w-full py-16 sm:py-20 px-4 sm:px-8 max-w-7xl mx-auto border-t border-neutral-200/60 select-none">
      
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto space-y-4 mb-10">
        <div className="inline-flex items-center gap-2 bg-[#f1eee7] text-neutral-800 px-4 py-1.5 rounded-full text-xs font-semibold">
          <Zap className="w-3.5 h-3.5 text-emerald-600" />
          <span>Platform Capabilities & Features</span>
        </div>
        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-neutral-950 font-sans tracking-tight">
          Intelligent Portfolio Health Monitoring
        </h2>
        <p className="text-neutral-600 text-sm sm:text-base max-w-2xl mx-auto leading-relaxed">
          Explore the core capabilities powering continuous risk discovery, deterministic financial modeling,
          autonomous multi-agent surveillance, and regulatory audit compliance.
        </p>
      </div>

      {/* Interactive Category Jump Pills */}
      <div className="flex flex-wrap items-center justify-center gap-2 mb-8">
        <button
          onClick={() => setActive(0)}
          className={`px-4 py-2 rounded-full text-xs font-semibold transition-all duration-200 cursor-pointer ${
            active === 0
              ? 'bg-neutral-950 text-white shadow-xs scale-102'
              : 'bg-[#f1eee7]/90 text-neutral-700 hover:text-neutral-950 hover:bg-[#e7e4dc]'
          }`}
        >
          All Platform Features
        </button>
        {PLATFORM_FEATURES.map((feat, idx) => (
          <button
            key={feat.id}
            onClick={() => {
              if (lockRef.current) return
              lock()
              setActive(idx)
            }}
            className={`px-4 py-2 rounded-full text-xs font-semibold transition-all duration-200 cursor-pointer ${
              active === idx
                ? 'bg-neutral-950 text-white shadow-xs scale-102'
                : 'bg-[#f1eee7]/90 text-neutral-700 hover:text-neutral-950 hover:bg-[#e7e4dc]'
            }`}
          >
            {feat.category}
          </button>
        ))}
      </div>

      {/* 3D Coverflow Viewport */}
      <div
        className="w-full relative flex items-center justify-center focus:outline-none"
        style={{
          height: `${cardHeight + 120}px`,
          perspective: `${PERSPECTIVE}px`,
          perspectiveOrigin: 'center 48%',
        }}
        tabIndex={0}
        role="region"
        aria-roledescription="3D Coverflow Carousel"
        aria-label="Platform Feature Cards"
        onKeyDown={onKeyDown}
      >
        <div
          style={{
            position: 'relative',
            width: cardWidth,
            height: cardHeight,
            transformStyle: 'preserve-3d',
          }}
        >
          {PLATFORM_FEATURES.map((feat, i) => {
            let rel = i - active
            // Loop normalization
            if (rel > n / 2) rel -= n
            if (rel < -n / 2) rel += n

            const ax = Math.abs(rel)
            const visible = ax <= MAX_VISIBLE
            const isActive = rel === 0
            const sc = Math.max(0.48, 1 - ax * SCALE_STEP)
            const tx = rel * (gap * 28)
            const tz = -ax * DEPTH
            const ry = -rel * tilt
            const rz = rel * sideTilt
            const Icon = feat.icon

            const cardStyle: CSSProperties = {
              position: 'absolute',
              left: '50%',
              top: '50%',
              width: cardWidth,
              height: cardHeight,
              borderRadius: '24px',
              overflow: 'hidden',
              transformStyle: 'preserve-3d',
              transformOrigin: 'center center',
              transform: `translate(-50%, -50%) translateX(${tx}px) translateZ(${tz}px) rotateY(${ry}deg) rotateZ(${rz}deg) scale(${sc})`,
              transition: transitionCss,
              opacity: visible ? (isActive ? 1 : 0.68) : 0,
              cursor: isActive ? 'default' : 'pointer',
              pointerEvents: visible ? 'auto' : 'none',
              zIndex: isActive ? 30 : 20 - ax,
              boxShadow: isActive
                ? '0 25px 50px -12px rgba(0, 0, 0, 0.18), 0 0 0 1px rgba(0, 0, 0, 0.08)'
                : '0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.05)',
            }

            return (
              <div
                key={feat.id}
                style={cardStyle}
                onClick={() => handleCardClick(i)}
                aria-label={feat.title}
                aria-hidden={!visible}
                className="bg-white border border-neutral-200/90 flex flex-col justify-between p-6 sm:p-7 transition-colors"
              >
                {/* Card Top: Icon, Metric & Category */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className={`p-2.5 rounded-2xl ${feat.badgeColor} shadow-xs`}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-extrabold text-neutral-950 font-mono">
                        {feat.metric}
                      </span>
                      <span className="block text-[10px] text-neutral-400 font-medium">
                        {feat.metricLabel}
                      </span>
                    </div>
                  </div>

                  <div className="text-[11px] font-bold text-neutral-500 uppercase tracking-wider mb-1.5 font-sans">
                    {feat.category}
                  </div>

                  <h3 className="text-lg sm:text-xl font-bold text-neutral-950 font-sans tracking-tight">
                    {feat.title}
                  </h3>

                  <p className="text-xs text-neutral-600 mt-2.5 leading-relaxed font-normal">
                    {feat.desc}
                  </p>
                </div>

                {/* Card Bottom: Highlights List */}
                <div className="space-y-2 pt-4 border-t border-neutral-100">
                  {feat.highlights.map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2 text-xs text-neutral-700">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      <span className="font-medium">{item}</span>
                    </div>
                  ))}
                </div>

                {/* Inactive Overlay for 3D Depth Legibility */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background: '#000000',
                    opacity: isActive ? 0 : 0.06,
                    transition: `opacity ${dur}s ${ease}`,
                    pointerEvents: 'none',
                    borderRadius: 'inherit',
                  }}
                />
              </div>
            )
          })}
        </div>
      </div>

      {/* Navigation Controls: Arrows + Stage Indicators */}
      <div className="flex items-center justify-center gap-4 mt-2">
        <button
          onClick={() => step(-1)}
          className="w-10 h-10 rounded-full bg-white hover:bg-neutral-100 text-neutral-700 border border-neutral-200 shadow-xs flex items-center justify-center transition-all cursor-pointer active:scale-95"
          aria-label="Previous Feature Card"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 bg-[#f1eee7]/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-200/60 shadow-xs">
          {PLATFORM_FEATURES.map((feat, idx) => (
            <button
              key={feat.id}
              onClick={() => {
                if (lockRef.current) return
                lock()
                setActive(idx)
              }}
              className={`text-xs font-mono font-bold px-3 py-1 rounded-full transition-all cursor-pointer ${
                active === idx
                  ? 'bg-neutral-950 text-white shadow-xs scale-105'
                  : 'text-neutral-600 hover:text-neutral-950 hover:bg-neutral-200/50'
              }`}
            >
              0{idx + 1}
            </button>
          ))}
        </div>

        <button
          onClick={() => step(1)}
          className="w-10 h-10 rounded-full bg-white hover:bg-neutral-100 text-neutral-700 border border-neutral-200 shadow-xs flex items-center justify-center transition-all cursor-pointer active:scale-95"
          aria-label="Next Feature Card"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

    </section>
  )
}

export default WorkflowVisualizer
