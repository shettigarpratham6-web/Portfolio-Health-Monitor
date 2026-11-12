import React, { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { Navbar } from './components/common/Navbar'
import { Footer } from './components/common/Footer'
import { HeroSection } from './components/landing/HeroSection'
import { WorkflowVisualizer } from './components/landing/WorkflowVisualizer'
import { LiveDemoModal } from './components/landing/LiveDemoModal'
import { AuthModal } from './components/auth/AuthModal'
import { DashboardHome } from './components/dashboard/DashboardHome'
import { PortfolioManager } from './components/dashboard/PortfolioManager'
import { AutonomousMonitorView } from './components/dashboard/AutonomousMonitorView'
import { AlertsManager } from './components/dashboard/AlertsManager'
import { ArchitectureView } from './components/dashboard/ArchitectureView'
import { Loader } from './components/common/Loader'
type ViewMode = 'landing' | 'dashboard' | 'portfolios' | 'monitor' | 'alerts' | 'architecture'

const AppContent: React.FC = () => {
  const { isLoading } = useAuth()
  const [currentView, setCurrentView] = useState<ViewMode>('landing')
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null)
  const [isAuthOpen, setIsAuthOpen] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [isLiveDemoOpen, setIsLiveDemoOpen] = useState(false)

  // Initial 8-second loader for the first launch in the session
  const [showInitialLoader, setShowInitialLoader] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return !sessionStorage.getItem('phm_initial_loader_shown')
  })

  useEffect(() => {
    if (showInitialLoader) {
      const timer = setTimeout(() => {
        sessionStorage.setItem('phm_initial_loader_shown', 'true')
        setShowInitialLoader(false)
      }, 8000)
      return () => clearTimeout(timer)
    }
  }, [showInitialLoader])

  if (showInitialLoader) {
    return (
      <div className="min-h-screen w-full bg-[#031410] flex flex-col items-center justify-center p-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.12)_0%,transparent_70%)] pointer-events-none" />
        <Loader />
      </div>
    )
  }

  const handleOpenAuth = (mode: 'login' | 'register') => {
    setAuthMode(mode)
    setIsAuthOpen(true)
  }

  const handleSelectPortfolio = (id: string) => {
    setSelectedPortfolioId(id)
    setCurrentView('portfolios')
  }

  const handleTriggerMonitorFromPortfolio = (id: string) => {
    setSelectedPortfolioId(id)
    setCurrentView('monitor')
  }

  const handleNavigateToAlerts = (id: string) => {
    setSelectedPortfolioId(id)
    setCurrentView('alerts')
  }

  return (
    <div className="min-h-screen w-full bg-[#faf9f5] flex flex-col justify-between overflow-x-hidden text-neutral-900">
      {/* Navigation Bar */}
      <Navbar
        currentView={currentView}
        setCurrentView={setCurrentView}
        onOpenAuth={handleOpenAuth}
        onOpenLiveDemo={() => setIsLiveDemoOpen(true)}
      />

      {/* Dynamic Page Views */}
      <main className="flex-grow w-full">
          {currentView === 'landing' && (
            <div className="space-y-4">
              <HeroSection
                onLaunchMonitor={() => setCurrentView('monitor')}
                onOpenLiveDemo={() => setIsLiveDemoOpen(true)}
                onBookDemo={() => handleOpenAuth('register')}
              />
              <WorkflowVisualizer />
            </div>
          )}

          {currentView === 'dashboard' && (
            <DashboardHome
              onNavigate={setCurrentView}
              onSelectPortfolio={handleSelectPortfolio}
              onOpenAuth={handleOpenAuth}
            />
          )}

          {currentView === 'portfolios' && (
            <PortfolioManager
              selectedPortfolioId={selectedPortfolioId}
              onClearSelectedPortfolio={() => setSelectedPortfolioId(null)}
              onTriggerMonitor={handleTriggerMonitorFromPortfolio}
            />
          )}

          {currentView === 'monitor' && (
            <AutonomousMonitorView
              initialPortfolioId={selectedPortfolioId}
              onNavigateToAlerts={handleNavigateToAlerts}
            />
          )}

          {currentView === 'alerts' && (
            <AlertsManager
              initialPortfolioId={selectedPortfolioId}
              onNavigateToMonitor={() => setCurrentView('monitor')}
            />
          )}

          {currentView === 'architecture' && <ArchitectureView />}
        </main>

        {/* Global Footer */}
        <Footer onNavigate={setCurrentView} />

      {/* Modals */}
      <LiveDemoModal
        isOpen={isLiveDemoOpen}
        onClose={() => setIsLiveDemoOpen(false)}
        onNavigateToMonitor={() => {
          setIsLiveDemoOpen(false)
          setCurrentView('monitor')
        }}
      />

      <AuthModal
        isOpen={isAuthOpen}
        initialMode={authMode}
        onClose={() => setIsAuthOpen(false)}
        onSuccess={() => {
          setIsAuthOpen(false)
          if (currentView === 'landing') {
            setCurrentView('dashboard')
          }
        }}
      />
    </div>
  )
}

export function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
