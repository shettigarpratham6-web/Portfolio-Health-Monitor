import React, { useState } from 'react'
import { X, Lock, Mail, User, Sparkles, AlertCircle, ArrowRight } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

interface AuthModalProps {
  isOpen: boolean
  initialMode?: 'login' | 'register'
  onClose: () => void
  onSuccess?: () => void
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  initialMode = 'login',
  onClose,
  onSuccess,
}) => {
  const { login, register, loginAsDemo } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await register(email, password, fullName)
      }
      onClose()
      if (onSuccess) onSuccess()
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleDemoLogin = async () => {
    setError(null)
    setLoading(true)
    try {
      await loginAsDemo()
      onClose()
      if (onSuccess) onSuccess()
    } catch (err: any) {
      setError(err.message || 'Demo session initialization failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-3xl max-w-md w-full shadow-2xl border border-neutral-200 overflow-hidden">
        
        {/* Header */}
        <div className="px-6 py-5 border-b border-neutral-100 flex items-center justify-between bg-[#fbfaf7]">
          <div className="flex items-center gap-2.5">
            <img
              src="/logo.png"
              alt="Portfolio Health Monitor Logo"
              className="w-8 h-8 rounded-full object-cover shadow-xs"
            />
            <div>
              <h3 className="text-lg font-bold text-neutral-900 font-sans">
                {mode === 'login' ? 'Sign in to Portfolio Health Monitor' : 'Create an Account'}
              </h3>
              <p className="text-xs text-neutral-500">
                {mode === 'login' ? 'Access your portfolio health workspace' : 'Begin autonomous portfolio risk monitoring'}
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

        {/* Form Body */}
        <div className="p-6 space-y-4">
          
          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-2xl flex items-start gap-2.5 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          {/* Quick 1-Click Demo Login Button */}
          <button
            type="button"
            onClick={handleDemoLogin}
            disabled={loading}
            className="w-full bg-[#f1eee7] hover:bg-[#e6e2d6] text-neutral-900 py-3 rounded-2xl text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-98 border border-neutral-300/60 shadow-xs cursor-pointer"
          >
            <Sparkles className="w-4 h-4 text-emerald-600 fill-emerald-600" />
            <span>1-Click Instant Demo Login (Lead Risk Officer)</span>
          </button>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-neutral-200" />
            <span className="flex-shrink mx-4 text-neutral-400 text-[11px] uppercase tracking-wider font-semibold">
              Or with email
            </span>
            <div className="flex-grow border-t border-neutral-200" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {mode === 'register' && (
              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1">
                  Full Name
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-neutral-400 absolute left-3.5 top-3" />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Jane Doe"
                    className="w-full pl-10 pr-4 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-black"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">
                Email Address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-neutral-400 absolute left-3.5 top-3" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-black"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-neutral-400 absolute left-3.5 top-3" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                  className="w-full pl-10 pr-4 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-black"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-black hover:bg-neutral-800 disabled:opacity-50 text-white py-3 rounded-2xl text-xs font-semibold tracking-tight transition-all active:scale-98 shadow-md mt-2 flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>{loading ? 'Authenticating...' : mode === 'login' ? 'Sign In' : 'Create Account'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>

          {/* Toggle login / register */}
          <div className="text-center pt-2">
            {mode === 'login' ? (
              <p className="text-xs text-neutral-500">
                Don't have an account?{' '}
                <button
                  onClick={() => {
                    setMode('register')
                    setError(null)
                  }}
                  className="font-bold text-neutral-900 hover:underline"
                >
                  Register here
                </button>
              </p>
            ) : (
              <p className="text-xs text-neutral-500">
                Already registered?{' '}
                <button
                  onClick={() => {
                    setMode('login')
                    setError(null)
                  }}
                  className="font-bold text-neutral-900 hover:underline"
                >
                  Sign in
                </button>
              </p>
            )}
          </div>

        </div>

      </div>
    </div>
  )
}

