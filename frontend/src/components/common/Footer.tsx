import React from 'react'
import { ShieldCheck, Heart } from 'lucide-react'

export const Footer: React.FC<{
  onNavigate: (view: 'landing' | 'dashboard' | 'portfolios' | 'monitor' | 'alerts' | 'architecture') => void
}> = ({ onNavigate }) => {
  return (
    <footer className="w-full border-t border-neutral-200/60 bg-[#fbfaf7] py-12 px-4 sm:px-8 mt-12">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6 text-sm text-neutral-500">
        
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <img
            src="/logo.png"
            alt="Portfolio Health Monitor Logo"
            className="w-6 h-6 rounded-full object-cover shadow-xs"
          />
          <span className="font-bold text-neutral-900 font-sans tracking-tight">Portfolio Health Monitor</span>
          <span className="text-xs text-neutral-400">© 2026 Portfolio Health Monitor. Non-Advisory Portfolio System.</span>
        </div>

        {/* Links */}
        <div className="flex flex-wrap items-center gap-6 text-xs font-medium text-neutral-600">
          <button onClick={() => onNavigate('landing')} className="hover:text-black transition-colors">
            Home
          </button>
          <button onClick={() => onNavigate('dashboard')} className="hover:text-black transition-colors">
            Dashboard
          </button>
          <button onClick={() => onNavigate('portfolios')} className="hover:text-black transition-colors">
            Portfolios
          </button>
          <button onClick={() => onNavigate('monitor')} className="hover:text-black transition-colors">
            Autonomous Monitor
          </button>
          <button onClick={() => onNavigate('alerts')} className="hover:text-black transition-colors">
            Risk Alerts
          </button>
        </div>

        {/* SEC Disclaimer Pill */}
        <div className="flex items-center gap-2 text-xs bg-neutral-200/60 px-3.5 py-1.5 rounded-full text-neutral-600">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Non-Advisory Mandate Certified</span>
        </div>

      </div>
    </footer>
  )
}

