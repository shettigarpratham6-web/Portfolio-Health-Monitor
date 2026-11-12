import React, { useState, useEffect, useCallback, useRef, type CSSProperties } from 'react'
import {
  Lock,
  Cpu,
  Search,
  Database,
  ShieldCheck,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

export interface ArchitectureCard {
  step: string
  title: string
  tag: string
  desc: string
  badgeColor: string
  iconColor: string
  icon: React.ElementType
}

export const ARCHITECTURE_SLIDES: ArchitectureCard[] = [
  {
    step: '01',
    title: 'Input Guardrails',
    tag: 'Security & Sanitize',
    desc: 'Blocks prompt injection, SQL injection, and out-of-scope non-financial requests.',
    badgeColor: 'bg-emerald-100 text-emerald-800',
    iconColor: 'text-emerald-700',
    icon: Lock,
  },
  {
    step: '02',
    title: 'Supervisor & State',
    tag: 'Autonomous Multi-Agent',
    desc: 'Loads portfolio state, evaluates graph checkpoint, and dispatches to discovery agents.',
    badgeColor: 'bg-blue-100 text-blue-800',
    iconColor: 'text-blue-700',
    icon: Cpu,
  },
  {
    step: '03',
    title: 'Intelligence Discovery',
    tag: 'Market News & Filings',
    desc: 'Fetches live market news, 10-K filings, and verifies sources with deduplication.',
    badgeColor: 'bg-purple-100 text-purple-800',
    iconColor: 'text-purple-700',
    icon: Search,
  },
  {
    step: '04',
    title: 'Deterministic Math',
    tag: 'Deterministic Risk Engine',
    desc: 'Calculates exact portfolio exposure, concentration index (HHI), and supply chain matrices.',
    badgeColor: 'bg-rose-100 text-rose-800',
    iconColor: 'text-rose-700',
    icon: Database,
  },
  {
    step: '05',
    title: 'Alerts & Output Guard',
    tag: 'SEC Non-Advisory Notice',
    desc: 'Records active alerts securely and certifies non-advisory regulatory compliance.',
    badgeColor: 'bg-teal-100 text-teal-800',
    iconColor: 'text-teal-700',
    icon: ShieldCheck,
  },
]

// 3D Coverflow Constants
const PERSPECTIVE = 1600
const SCALE_STEP = 0.12
const MAX_VISIBLE = 2
const DEPTH = 220

interface Smooth3DSlideshowProps {
  cards?: ArchitectureCard[]
  autoplay?: boolean
  autoplayInterval?: number
}

export const Smooth3DArchitectureSlideshow: React.FC<Smooth3DSlideshowProps> = ({
  cards = ARCHITECTURE_SLIDES,
  autoplay = false,
  autoplayInterval = 3500,
}) => {
  const [active, setActive] = useState(0)
  const [cardWidth, setCardWidth] = useState(380)
  const [cardHeight, setCardHeight] = useState(320)
  const n = cards.length
  const lockRef = useRef(false)

  // Measure container for fluid responsiveness
  useEffect(() => {
    const updateDimensions = () => {
      const w = window.innerWidth
      if (w < 640) {
        setCardWidth(Math.min(320, w - 48))
        setCardHeight(330)
      } else if (w < 1024) {
        setCardWidth(350)
        setCardHeight(320)
      } else {
        setCardWidth(380)
        setCardHeight(320)
      }
    }
    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    return () => window.removeEventListener('resize', updateDimensions)
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

  // Autoplay support if enabled
  useEffect(() => {
    if (!autoplay || n < 2) return
    const id = window.setInterval(() => step(1), autoplayInterval)
    return () => window.clearInterval(id)
  }, [autoplay, autoplayInterval, n, step])

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
    <div className="w-full flex flex-col items-center select-none">
      {/* 3D Viewport */}
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
        aria-label="Architecture Pipeline Nodes"
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
          {cards.map((card, i) => {
            let rel = i - active
            // Loop normalization
            if (rel > n / 2) rel -= n
            if (rel < -n / 2) rel += n

            const ax = Math.abs(rel)
            const visible = ax <= MAX_VISIBLE
            const isActive = rel === 0
            const sc = Math.max(0.5, 1 - ax * SCALE_STEP)
            const tx = rel * (gap * 28)
            const tz = -ax * DEPTH
            const ry = -rel * tilt
            const rz = rel * sideTilt
            const Icon = card.icon

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
                key={card.step}
                style={cardStyle}
                onClick={() => handleCardClick(i)}
                aria-label={`Step ${card.step}: ${card.title}`}
                aria-hidden={!visible}
                className="bg-white border border-neutral-200/90 flex flex-col justify-between p-6 transition-colors"
              >
                {/* Card Top: Number + Icon */}
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-mono font-bold text-neutral-400 tracking-wider">
                      {card.step}
                    </span>
                    <div className={`p-2 rounded-2xl ${card.badgeColor} shadow-xs`}>
                      <Icon className="w-4 h-4" />
                    </div>
                  </div>

                  {/* Subtitle / Tag */}
                  <div className="text-[11px] font-bold text-neutral-500 uppercase tracking-wider mb-1.5 font-sans">
                    {card.tag}
                  </div>

                  {/* Title */}
                  <h4 className="text-xl font-extrabold text-neutral-950 font-sans tracking-tight">
                    {card.title}
                  </h4>

                  {/* Description */}
                  <p className="text-xs text-neutral-600 mt-3 leading-relaxed font-normal">
                    {card.desc}
                  </p>
                </div>

                {/* Card Footer: Status */}
                <div className="pt-4 border-t border-neutral-100 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-600">
                    <CheckCircle className="w-4 h-4" />
                    <span>Verified Active</span>
                  </div>
                  <span className="text-[10px] font-mono font-semibold text-neutral-400">
                    Node {card.step} / 05
                  </span>
                </div>

                {/* Inactive Overlay for 3D Depth Legibility */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background: '#000000',
                    opacity: isActive ? 0 : 0.08,
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

      {/* Navigation Controls: Arrows + Stage Pills */}
      <div className="flex items-center justify-center gap-4 mt-2">
        <button
          onClick={() => step(-1)}
          className="w-10 h-10 rounded-full bg-white hover:bg-neutral-100 text-neutral-700 border border-neutral-200 shadow-xs flex items-center justify-center transition-all cursor-pointer active:scale-95"
          aria-label="Previous Architecture Step"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 bg-[#f1eee7]/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-neutral-200/60 shadow-xs">
          {cards.map((c, idx) => (
            <button
              key={c.step}
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
              {c.step}
            </button>
          ))}
        </div>

        <button
          onClick={() => step(1)}
          className="w-10 h-10 rounded-full bg-white hover:bg-neutral-100 text-neutral-700 border border-neutral-200 shadow-xs flex items-center justify-center transition-all cursor-pointer active:scale-95"
          aria-label="Next Architecture Step"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  )
}

export default Smooth3DArchitectureSlideshow

