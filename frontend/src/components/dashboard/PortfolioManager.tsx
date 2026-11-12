import React, { useEffect, useState } from 'react'
import {
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  DollarSign,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  TrendingUp,
  X,
  Play,
  AlertCircle,
  Trash2,
} from 'lucide-react'
import {
  addHolding,
  createPortfolio,
  deleteHolding,
  getPortfolio,
  listPortfolios,
} from '../../api/portfolios'
import type { PortfolioDetailResponse, PortfolioResponse } from '../../api/types'
import { useAuth } from '../../context/AuthContext'

interface PortfolioManagerProps {
  selectedPortfolioId?: string | null
  onClearSelectedPortfolio: () => void
  onTriggerMonitor: (portfolioId: string) => void
}

export const PortfolioManager: React.FC<PortfolioManagerProps> = ({
  selectedPortfolioId,
  onClearSelectedPortfolio,
  onTriggerMonitor,
}) => {
  const { isAuthenticated, loginAsDemo } = useAuth()
  const [portfolios, setPortfolios] = useState<PortfolioResponse[]>([])
  const [detail, setDetail] = useState<PortfolioDetailResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [activePortfolioId, setActivePortfolioId] = useState<string | null>(selectedPortfolioId || null)
  
  // Create Portfolio Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newCurrency, setNewCurrency] = useState('USD')
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Add Position Modal
  const [isAddHoldingOpen, setIsAddHoldingOpen] = useState(false)
  const [holdingTicker, setHoldingTicker] = useState('')
  const [holdingName, setHoldingName] = useState('')
  const [holdingShares, setHoldingShares] = useState('')
  const [holdingPrice, setHoldingPrice] = useState('')
  const [holdingLoading, setHoldingLoading] = useState(false)
  const [holdingError, setHoldingError] = useState<string | null>(null)

  const quickTickers = [
    { ticker: 'NVDA', name: 'NVIDIA Corporation', defaultPrice: '135.00' },
    { ticker: 'AAPL', name: 'Apple Inc.', defaultPrice: '225.00' },
    { ticker: 'MSFT', name: 'Microsoft Corporation', defaultPrice: '420.00' },
    { ticker: 'TSLA', name: 'Tesla Inc.', defaultPrice: '245.00' },
    { ticker: 'GOOGL', name: 'Alphabet Inc.', defaultPrice: '175.00' },
    { ticker: 'AMZN', name: 'Amazon.com Inc.', defaultPrice: '185.00' },
    { ticker: 'META', name: 'Meta Platforms Inc.', defaultPrice: '580.00' },
    { ticker: 'TSM', name: 'Taiwan Semiconductor Mfg.', defaultPrice: '190.00' },
  ]

  const handleSelectQuickTicker = (item: { ticker: string; name: string; defaultPrice: string }) => {
    setHoldingTicker(item.ticker)
    setHoldingName(item.name)
    if (!holdingPrice) {
      setHoldingPrice(item.defaultPrice)
    }
  }

  const handleAddHolding = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activePortfolioId) return
    setHoldingError(null)
    setHoldingLoading(true)

    const sharesNum = parseFloat(holdingShares)
    const priceNum = parseFloat(holdingPrice)

    if (isNaN(sharesNum) || sharesNum <= 0) {
      setHoldingError('Please enter a valid positive number of shares.')
      setHoldingLoading(false)
      return
    }
    if (isNaN(priceNum) || priceNum <= 0) {
      setHoldingError('Please enter a valid purchase price per share.')
      setHoldingLoading(false)
      return
    }

    try {
      await addHolding(activePortfolioId, {
        ticker: holdingTicker.trim().toUpperCase(),
        company_name: holdingName.trim() || undefined,
        shares: sharesNum,
        average_buy_price: priceNum,
        current_price: priceNum,
      })
      setIsAddHoldingOpen(false)
      setHoldingTicker('')
      setHoldingName('')
      setHoldingShares('')
      setHoldingPrice('')
      await loadDetail(activePortfolioId)
      await loadPortfolios()
    } catch (err: any) {
      setHoldingError(err.message || 'Failed to add holding position.')
    } finally {
      setHoldingLoading(false)
    }
  }

  const handleDeleteHolding = async (holdingId: string, tickerName?: string | null) => {
    if (!activePortfolioId) return
    const confirmed = window.confirm(
      `Remove ${tickerName || 'this asset position'} from ${detail?.name || 'the portfolio'}?`
    )
    if (!confirmed) return

    try {
      await deleteHolding(activePortfolioId, holdingId)
      await loadDetail(activePortfolioId)
      await loadPortfolios()
    } catch (err: any) {
      alert(err.message || 'Failed to remove position.')
    }
  }

  const loadPortfolios = async () => {
    if (!isAuthenticated) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const res = await listPortfolios(1, 50)
      setPortfolios(res.items)
      if (res.items.length > 0 && !activePortfolioId) {
        setActivePortfolioId(res.items[0].id)
      }
    } catch (err) {
      console.error('Failed to load portfolios:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadDetail = async (id: string) => {
    try {
      const res = await getPortfolio(id)
      setDetail(res)
    } catch (err) {
      console.error('Failed to load portfolio detail:', err)
    }
  }

  useEffect(() => {
    loadPortfolios()
  }, [isAuthenticated])

  useEffect(() => {
    if (activePortfolioId) {
      loadDetail(activePortfolioId)
    } else {
      setDetail(null)
    }
  }, [activePortfolioId])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError(null)
    setCreateLoading(true)
    try {
      const res = await createPortfolio({
        name: newName,
        description: newDesc,
        currency: newCurrency,
      })
      setIsCreateOpen(false)
      setNewName('')
      setNewDesc('')
      await loadPortfolios()
      setActivePortfolioId(res.id)
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create portfolio.')
    } finally {
      setCreateLoading(false)
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-neutral-100 flex items-center justify-center mx-auto text-neutral-400">
          <BarChart3 className="w-8 h-8" />
        </div>
        <h3 className="text-xl font-bold text-neutral-900 font-sans">
          Sign In to Manage Portfolios
        </h3>
        <p className="text-sm text-neutral-500 max-w-md mx-auto">
          Portfolio holdings, calculated weights, and risk exposures are strictly scoped to authenticated user accounts.
        </p>
        <button
          onClick={loginAsDemo}
          className="bg-black hover:bg-neutral-800 text-white px-6 py-3 rounded-full text-xs font-semibold shadow-xs transition-all cursor-pointer"
        >
          1-Click Instant Demo Login
        </button>
      </div>
    )
  }

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-8 py-8 space-y-8 animate-in fade-in duration-300">
      
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-neutral-950 font-sans tracking-tight">
            Portfolio Management & Asset Weights
          </h2>
          <p className="text-sm text-neutral-500">
            Real-time equity holdings, allocation percentages, and valuation metrics
          </p>
        </div>

        <button
          onClick={() => setIsCreateOpen(true)}
          className="bg-black hover:bg-neutral-800 text-white px-5 py-2.5 rounded-full text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>New Portfolio</span>
        </button>
      </div>

      {/* Main Grid: Sidebar List + Detail View */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column (4 cols): Portfolio Cards */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-bold text-neutral-400 uppercase tracking-wider px-1">
            Your Portfolios ({portfolios.length})
          </div>

          {loading ? (
            <div className="space-y-2.5 animate-pulse">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="p-4 rounded-2xl border border-neutral-200/80 bg-white/70 space-y-2.5 shadow-xs"
                >
                  <div className="flex justify-between items-center">
                    <div className="h-4 bg-neutral-200 rounded-md w-2/3" />
                    <div className="h-4 bg-neutral-100 rounded-md w-12" />
                  </div>
                  <div className="flex gap-2">
                    <div className="h-3 bg-neutral-100 rounded w-16" />
                    <div className="h-3 bg-neutral-100 rounded w-20" />
                  </div>
                </div>
              ))}
            </div>
          ) : portfolios.length === 0 ? (
            <div className="p-6 bg-white rounded-3xl border border-neutral-200 text-center text-xs text-neutral-500">
              No portfolios yet. Click "New Portfolio" to create one.
            </div>
          ) : (
            <div className="space-y-2.5">
              {portfolios.map((p) => {
                const isSelected = activePortfolioId === p.id
                return (
                  <div
                    key={p.id}
                    onClick={() => setActivePortfolioId(p.id)}
                    className={`p-4 rounded-2xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-neutral-950 text-white border-neutral-950 shadow-md'
                        : 'bg-white hover:bg-neutral-50 border-neutral-200 text-neutral-900'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm font-sans truncate">{p.name}</span>
                      {p.short_id && p.short_id !== 'port_e555391f' && (
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                          isSelected ? 'bg-neutral-800 text-neutral-300' : 'bg-neutral-100 text-neutral-600'
                        }`}>
                          {p.short_id}
                        </span>
                      )}
                    </div>
                    <div className={`text-xs ${isSelected ? 'text-neutral-400' : 'text-neutral-500'}`}>
                      {p.holdings_count} active positions · {p.currency}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Right Column (8 cols): Selected Portfolio Detailed Holdings */}
        <div className="lg:col-span-8 bg-white rounded-3xl p-6 sm:p-8 border border-neutral-200 shadow-sm space-y-6">
          {detail ? (
            <>
              {/* Detail Header & Action */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-neutral-100 gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-xl font-extrabold text-neutral-950 font-sans">
                      {detail.name}
                    </h3>
                    {detail.short_id && detail.short_id !== 'port_e555391f' && (
                      <span className="text-xs font-mono bg-emerald-50 text-emerald-800 border border-emerald-200 px-2.5 py-0.5 rounded-full font-semibold">
                        {detail.short_id}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-neutral-500 mt-1">
                    {detail.description || 'Monitored under Portfolio Health Monitor multi-agent surveillance pipeline'}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsAddHoldingOpen(true)}
                    className="bg-black hover:bg-neutral-800 text-white px-4 py-2.5 rounded-full text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-all cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Position</span>
                  </button>
                  <button
                    onClick={() => onTriggerMonitor(detail.id)}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-full text-xs font-semibold flex items-center gap-2 shadow-xs transition-all cursor-pointer"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Run Agent Monitoring</span>
                  </button>
                </div>
              </div>

              {/* Allocation Weights Visual Bar */}
              {detail.holdings.length > 0 && (
                <div className="space-y-2 bg-[#fbfaf7] p-4 rounded-2xl border border-neutral-200/60">
                  <div className="flex items-center justify-between text-xs font-semibold text-neutral-700">
                    <span>Portfolio Asset Allocation</span>
                    <span className="text-neutral-400 font-mono">100.0% Total Weight</span>
                  </div>
                  <div className="w-full h-3 bg-neutral-200 rounded-full overflow-hidden flex">
                    {detail.holdings.map((h, i) => {
                      const colors = ['bg-emerald-500', 'bg-blue-500', 'bg-purple-500', 'bg-amber-500', 'bg-rose-500']
                      const w = Number(h.weight_pct) || 0
                      return (
                        <div
                          key={h.id}
                          style={{ width: `${w}%` }}
                          title={`${h.ticker || 'Asset'}: ${w}%`}
                          className={`${colors[i % colors.length]} h-full transition-all`}
                        />
                      )
                    })}
                  </div>
                  <div className="flex flex-wrap gap-4 pt-1 text-[11px] text-neutral-600">
                    {detail.holdings.map((h, i) => {
                      const colors = ['text-emerald-600', 'text-blue-600', 'text-purple-600', 'text-amber-600', 'text-rose-600']
                      return (
                        <div key={h.id} className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full bg-current ${colors[i % colors.length]}`} />
                          <span className="font-bold">{h.ticker || 'Holding'}:</span>
                          <span>{h.weight_pct ? `${Number(h.weight_pct)}%` : 'N/A'}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Holdings Table */}
              <div className="space-y-3">
                <div className="text-xs font-bold text-neutral-900">
                  Individual Asset Positions ({detail.holdings.length})
                </div>

                {detail.holdings.length === 0 ? (
                  <div className="p-8 text-center space-y-3 bg-neutral-50 rounded-2xl border border-dashed border-neutral-200">
                    <p className="text-xs text-neutral-500">
                      This portfolio currently has no holdings recorded.
                    </p>
                    <button
                      onClick={() => setIsAddHoldingOpen(true)}
                      className="bg-black hover:bg-neutral-800 text-white px-4 py-2 rounded-full text-xs font-semibold inline-flex items-center gap-1.5 shadow-xs transition-all cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Add First Position</span>
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-neutral-200 text-neutral-400 font-semibold text-[11px] uppercase tracking-wider">
                          <th className="py-2.5 px-3">Ticker</th>
                          <th className="py-2.5 px-3">Company Name</th>
                          <th className="py-2.5 px-3 text-right">Shares</th>
                          <th className="py-2.5 px-3 text-right">Avg Price</th>
                          <th className="py-2.5 px-3 text-right">Current Price</th>
                          <th className="py-2.5 px-3 text-right">Weight</th>
                          <th className="py-2.5 px-3 text-right">Market Value</th>
                          <th className="py-2.5 px-3 text-center">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {detail.holdings.map((h) => (
                          <tr key={h.id} className="hover:bg-neutral-50/70 transition-colors">
                            <td className="py-3 px-3 font-mono font-bold text-neutral-950">
                              {h.ticker || 'N/A'}
                            </td>
                            <td className="py-3 px-3 text-neutral-700">
                              {h.company_name || 'Verified Corporation'}
                            </td>
                            <td className="py-3 px-3 text-right font-mono text-neutral-900">
                              {Number(h.shares).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-right font-mono text-neutral-600">
                              ${Number(h.average_buy_price).toFixed(2)}
                            </td>
                            <td className="py-3 px-3 text-right font-mono text-neutral-900 font-semibold">
                              ${Number(h.current_price || h.average_buy_price).toFixed(2)}
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-bold text-emerald-700">
                              {h.weight_pct ? `${Number(h.weight_pct).toFixed(1)}%` : '—'}
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-bold text-neutral-950">
                              ${Number(h.market_value || 0).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-center">
                              <button
                                onClick={() => handleDeleteHolding(h.id, h.ticker)}
                                title="Remove position"
                                className="p-1.5 text-neutral-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-xs text-neutral-400">
              Select a portfolio from the left to view detailed holdings.
            </div>
          )}
        </div>

      </div>

      {/* Create Portfolio Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-neutral-200">
            <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
              <h3 className="font-bold text-base text-neutral-900 font-sans">
                Create New Portfolio
              </h3>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="w-7 h-7 rounded-full bg-neutral-100 flex items-center justify-center text-neutral-500 hover:bg-neutral-200"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {createError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-xl flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreate} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1">
                  Portfolio Name
                </label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Clean Energy Growth Strategy"
                  className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1">
                  Description / Thesis
                </label>
                <textarea
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Investment mandate and monitoring objectives..."
                  rows={3}
                  className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-neutral-700 mb-1">
                  Currency
                </label>
                <select
                  value={newCurrency}
                  onChange={(e) => setNewCurrency(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                >
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                  <option value="GBP">GBP (£)</option>
                </select>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-neutral-600 hover:text-neutral-900 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading}
                  className="bg-black hover:bg-neutral-800 disabled:opacity-50 text-white px-5 py-2.5 rounded-full text-xs font-semibold cursor-pointer shadow-xs"
                >
                  {createLoading ? 'Creating...' : 'Create Portfolio'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Position Modal */}
      {isAddHoldingOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-neutral-200">
            <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
              <div>
                <h3 className="font-bold text-base text-neutral-900 font-sans">
                  Add Asset Position
                </h3>
                <p className="text-[11px] text-neutral-500">
                  Target portfolio: <span className="font-semibold text-neutral-800">{detail?.name}</span>
                </p>
              </div>
              <button
                onClick={() => setIsAddHoldingOpen(false)}
                className="text-neutral-400 hover:text-neutral-900 p-1 rounded-full hover:bg-neutral-100 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Quick-Pick Popular Tickers */}
            <div>
              <label className="block text-[11px] font-semibold text-neutral-500 mb-1.5 uppercase tracking-wider">
                Quick Autocomplete Tickers
              </label>
              <div className="flex flex-wrap gap-1.5">
                {quickTickers.map((item) => (
                  <button
                    key={item.ticker}
                    type="button"
                    onClick={() => handleSelectQuickTicker(item)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium border transition-colors cursor-pointer ${
                      holdingTicker.toUpperCase() === item.ticker
                        ? 'bg-neutral-900 text-white border-neutral-900'
                        : 'bg-neutral-50 hover:bg-neutral-100 border-neutral-200 text-neutral-700'
                    }`}
                  >
                    {item.ticker}
                  </button>
                ))}
              </div>
            </div>

            {holdingError && (
              <div className="p-3 bg-rose-50 text-rose-700 rounded-xl text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{holdingError}</span>
              </div>
            )}

            <form onSubmit={handleAddHolding} className="space-y-3.5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-neutral-700 mb-1">
                    Ticker Symbol *
                  </label>
                  <input
                    type="text"
                    required
                    value={holdingTicker}
                    onChange={(e) => setHoldingTicker(e.target.value.toUpperCase())}
                    placeholder="e.g. NVDA"
                    className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs font-mono font-bold text-neutral-900 uppercase focus:outline-none focus:ring-2 focus:ring-black"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-neutral-700 mb-1">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={holdingName}
                    onChange={(e) => setHoldingName(e.target.value)}
                    placeholder="e.g. NVIDIA Corporation"
                    className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-neutral-700 mb-1">
                    Shares Owned *
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0.0001"
                    required
                    value={holdingShares}
                    onChange={(e) => setHoldingShares(e.target.value)}
                    placeholder="e.g. 100"
                    className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs font-mono text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-neutral-700 mb-1">
                    Purchase Price ($) *
                  </label>
                  <input
                    type="number"
                    step="any"
                    min="0.01"
                    required
                    value={holdingPrice}
                    onChange={(e) => setHoldingPrice(e.target.value)}
                    placeholder="e.g. 125.00"
                    className="w-full px-3.5 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-xs font-mono text-neutral-900 focus:outline-none focus:ring-2 focus:ring-black"
                  />
                </div>
              </div>

              {/* Total Investment Calculation Preview */}
              {parseFloat(holdingShares) > 0 && parseFloat(holdingPrice) > 0 && (
                <div className="p-3 bg-emerald-50/80 border border-emerald-200 rounded-xl flex items-center justify-between text-xs text-emerald-900">
                  <span className="font-medium">Total Position Investment:</span>
                  <span className="font-mono font-bold text-sm">
                    ${(parseFloat(holdingShares) * parseFloat(holdingPrice)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-neutral-100">
                <button
                  type="button"
                  onClick={() => setIsAddHoldingOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-neutral-600 hover:text-neutral-900 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={holdingLoading}
                  className="bg-black hover:bg-neutral-800 disabled:opacity-50 text-white px-5 py-2.5 rounded-full text-xs font-semibold cursor-pointer shadow-xs inline-flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{holdingLoading ? 'Saving...' : 'Add Position'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  )
}

