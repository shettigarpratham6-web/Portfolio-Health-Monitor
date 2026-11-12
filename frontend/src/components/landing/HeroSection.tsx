import React from 'react'
import { Calendar, Zap, Check, ArrowRight, Play, ShieldAlert, Sparkles } from 'lucide-react'
import { AgentCanvas3D } from '../3d/AgentCanvas3D'

interface HeroSectionProps {
  onLaunchMonitor: () => void
  onOpenLiveDemo: () => void
  onBookDemo: () => void
}

export const HeroSection: React.FC<HeroSectionProps> = ({
  onLaunchMonitor,
  onOpenLiveDemo,
  onBookDemo,
}) => {
  return (
    <section className="relative w-full pt-6 md:pt-14 pb-16 px-4 sm:px-8 max-w-7xl mx-auto overflow-hidden">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
        
        {/* ============================================================== */}
        {/* LEFT COLUMN: Large Compelling Headline & CTAs                  */}
        {/* ============================================================== */}
        <div className="lg:col-span-6 space-y-6 md:space-y-8 z-10">
          
          <div className="space-y-4">
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-neutral-950 font-sans leading-[1.08]">
              AI agents you can <br className="hidden sm:inline" />
              see right through
            </h1>

            <p className="text-neutral-600 text-base sm:text-lg leading-relaxed max-w-xl font-normal">
              Portfolio Health Monitor gives investment teams AI agents for portfolio monitoring, 
              filing discovery and risk impact that plug into the tools you already use. 
              Every step they take is visible, so you always know what happened and why.
            </p>
          </div>

          {/* CTA Buttons Row */}
          <div className="flex flex-wrap items-center gap-3 sm:gap-4 pt-1">
            <button
              onClick={onBookDemo}
              className="bg-black hover:bg-neutral-800 text-white px-7 py-3.5 rounded-full text-sm font-semibold tracking-tight shadow-md hover:shadow-lg transition-all duration-200 active:scale-95 flex items-center gap-2 cursor-pointer"
            >
              <span>Book a demo</span>
            </button>

            <button
              onClick={onOpenLiveDemo}
              className="bg-[#f2efe9] hover:bg-[#e7e3d9] text-neutral-900 px-7 py-3.5 rounded-full text-sm font-semibold transition-all duration-200 active:scale-95 flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <span>See an agent work</span>
              <Play className="w-3.5 h-3.5 fill-current text-neutral-700" />
            </button>
          </div>
        </div>

        {/* ============================================================== */}
        {/* RIGHT COLUMN: 3D Mascot Character & Floating Reference Cards   */}
        {/* ============================================================== */}
        <div className="lg:col-span-6 relative flex items-center justify-center min-h-[460px] md:min-h-[520px]">
          
          {/* Soft Ethereal Mint Radial Glow Backdrop */}
          <div className="absolute inset-0 bg-radial from-emerald-200/50 via-teal-100/25 to-transparent rounded-full filter blur-3xl -z-10 pointer-events-none transform scale-90" />

          {/* Central Three.js 3D Interactive Mascot */}
          <div className="relative w-full max-w-[420px] aspect-square flex items-center justify-center">
            <AgentCanvas3D />
          </div>

          {/* ------------------------------------------------------------ */}
          {/* FLOATING BADGE 1: Top-Right Dark Pill Badge                  */}
          {/* ------------------------------------------------------------ */}
          <div className="absolute top-2 right-0 sm:right-4 z-20 animate-in fade-in slide-in-from-top-4 duration-700 pointer-events-none select-none">
            <div className="bg-black/95 text-white pl-2.5 pr-4 py-2 rounded-full text-xs flex items-center gap-2.5 shadow-xl border border-neutral-800 backdrop-blur-md">
              <div className="w-7 h-7 rounded-full bg-emerald-400 text-neutral-950 flex items-center justify-center shrink-0">
                <ShieldAlert className="w-3.5 h-3.5" />
              </div>
              <div className="leading-tight">
                <div className="font-medium text-white text-[12px]">
                  Risk alert generated for NVDA
                </div>
                <div className="text-[10px] text-neutral-400">
                  just now · Portfolio Impact Agent
                </div>
              </div>
            </div>
          </div>

          {/* ------------------------------------------------------------ */}
          {/* FLOATING BADGE 2: Mid-Left Dark Pill Badge                   */}
          {/* ------------------------------------------------------------ */}
          <div className="absolute top-1/3 -left-2 sm:left-2 z-20 animate-in fade-in slide-in-from-left-4 duration-700 pointer-events-none select-none">
            <div className="bg-black/95 text-white pl-2 pr-4 py-2 rounded-full text-xs flex items-center gap-2.5 shadow-xl border border-neutral-800 backdrop-blur-md">
              <div className="w-7 h-7 rounded-full bg-lime-400 text-neutral-950 flex items-center justify-center font-bold text-xs shrink-0">
                <Zap className="w-3.5 h-3.5 fill-current" />
              </div>
              <div className="leading-tight text-[11px] sm:text-[12px]">
                <span className="font-bold text-white mr-1.5">2,189</span>
                <span className="text-neutral-300">steps executed · Verified & Audited</span>
              </div>
            </div>
          </div>

          {/* ------------------------------------------------------------ */}
          {/* FLOATING CARD 3: Bottom-Right Chat & Step Progress Card     */}
          {/* ------------------------------------------------------------ */}
          <div className="absolute bottom-0 right-0 sm:right-2 z-20 max-w-[320px] w-full animate-in fade-in slide-in-from-bottom-4 duration-700 pointer-events-none select-none">
            <div className="bg-white/95 backdrop-blur-md rounded-2xl p-3.5 shadow-2xl border border-neutral-200/80 space-y-2.5">
              {/* User Query Pill */}
              <div className="bg-neutral-100/90 text-neutral-800 text-[11px] font-medium px-3 py-1.5 rounded-xl w-fit">
                Taiwan earthquake: TSMC supplier impact on NVDA?
              </div>

              {/* Progress Steps */}
              <div className="space-y-1.5 text-[11px] text-neutral-600">
                <div className="flex items-center gap-1.5 bg-neutral-50 px-2.5 py-1 rounded-lg">
                  <Check className="w-3 h-3 text-emerald-600 shrink-0" />
                  <span>Found TSMC fab delay report (Credibility 0.94)</span>
                </div>
                <div className="flex items-center gap-1.5 bg-neutral-50 px-2.5 py-1 rounded-lg">
                  <Check className="w-3 h-3 text-emerald-600 shrink-0" />
                  <span>Calculated 25.0% direct weight exposure</span>
                </div>
              </div>

              {/* Agent Reply Bubble */}
              <div className="bg-neutral-950 text-white text-[11px] leading-relaxed p-3 rounded-xl shadow-xs">
                Critical risk detected. 10-K supplier bottleneck identified; notification dispatched.
              </div>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}

