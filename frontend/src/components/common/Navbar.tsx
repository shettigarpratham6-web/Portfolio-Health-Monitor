import React from 'react'
import { Sparkles, LogOut, Activity, BarChart3, Bell } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

interface NavbarProps {
  currentView: 'landing' | 'dashboard' | 'portfolios' | 'monitor' | 'alerts' | 'architecture'
  setCurrentView: (view: 'landing' | 'dashboard' | 'portfolios' | 'monitor' | 'alerts' | 'architecture') => void
  onOpenAuth: (mode: 'login' | 'register') => void
  onOpenLiveDemo: () => void
}

export const Navbar: React.FC<NavbarProps> = ({
  currentView,
  setCurrentView,
  onOpenAuth,
  onOpenLiveDemo,
}) => {
  const { user, isAuthenticated, logout } = useAuth()

  return (
    <header className="w-full pt-4 pb-2 px-4 sm:px-8 max-w-7xl mx-auto flex items-center justify-between z-30 relative select-none">
      {/* 1. Left Brand / Logo */}
      <button
        onClick={() => setCurrentView('landing')}
        className="flex items-center gap-2.5 group focus:outline-none"
      >
        <img
          src="/logo.png"
          alt="Portfolio Health Monitor Logo"
          className="w-8 h-8 rounded-full object-cover shadow-xs group-hover:scale-105 transition-transform duration-200"
        />
        <span className="text-xl font-bold tracking-tight text-neutral-950 font-sans">
          Portfolio Health Monitor
        </span>
      </button>

      {/* 2. Center Pill Navigation Container */}
      <nav className="hidden md:flex items-center gap-1 bg-[#f1eee7]/90 backdrop-blur-md px-2 py-1.5 rounded-full border border-neutral-200/60 shadow-xs">
        <button
          onClick={() => setCurrentView('dashboard')}
          className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors flex items-center gap-1.5 ${currentView === 'dashboard'
            ? 'bg-white text-neutral-950 shadow-xs'
            : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-200/50'
            }`}
        >
          <Activity className="w-3.5 h-3.5 text-emerald-600" />
          <span>Dashboard</span>
        </button>

        <button
          onClick={() => setCurrentView('portfolios')}
          className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors flex items-center gap-1.5 ${currentView === 'portfolios'
            ? 'bg-white text-neutral-950 shadow-xs'
            : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-200/50'
            }`}
        >
          <BarChart3 className="w-3.5 h-3.5 text-neutral-500" />
          <span>Portfolios</span>
        </button>

        <button
          onClick={() => setCurrentView('monitor')}
          className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors flex items-center gap-1.5 ${currentView === 'monitor'
            ? 'bg-white text-neutral-950 shadow-xs'
            : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-200/50'
            }`}
        >
          <Sparkles className="w-3.5 h-3.5 text-lime-600" />
          <span>Live Monitor</span>
        </button>

        <button
          onClick={() => setCurrentView('alerts')}
          className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors flex items-center gap-1.5 ${currentView === 'alerts'
            ? 'bg-white text-neutral-950 shadow-xs'
            : 'text-neutral-700 hover:text-neutral-950 hover:bg-neutral-200/50'
            }`}
        >
          <Bell className="w-3.5 h-3.5 text-amber-500" />
          <span>Alerts</span>
        </button>
      </nav>

      {/* 3. Right Action CTA / User Profile */}
      <div className="flex items-center gap-2 sm:gap-3">
        {isAuthenticated && user ? (
          <div className="flex items-center gap-2 bg-[#f1eee7]/80 backdrop-blur pl-3 pr-1 py-1 rounded-full border border-neutral-200">
            <span className="text-xs font-semibold text-neutral-800 hidden sm:inline">
              {user.full_name || 'Pratham'}
            </span>
            <button
              onClick={logout}
              title="Sign Out"
              className="w-7 h-7 bg-white rounded-full flex items-center justify-center text-neutral-600 hover:text-rose-600 shadow-xs transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => onOpenAuth('login')}
              className="text-sm font-medium text-neutral-700 hover:text-neutral-950 px-3.5 py-2 transition-colors hidden sm:inline"
            >
              Sign In
            </button>
            <button
              onClick={() => onOpenAuth('register')}
              className="bg-neutral-950 hover:bg-neutral-800 text-white px-5 py-2.5 rounded-full text-sm font-medium tracking-tight shadow-sm hover:shadow transition-all duration-200 active:scale-95"
            >
              Book a demo
            </button>
          </>
        )}
      </div>
    </header>
  )
}

