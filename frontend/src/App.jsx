import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = 'http://localhost:8000'
const REFRESH_SECONDS = 60
const VOLUME_FILTERS = [
  { label: 'Any', value: 0 },
  { label: '$100K', value: 100000 },
  { label: '$500K', value: 500000 },
  { label: '$1M', value: 1000000 },
  { label: '$5M', value: 5000000 },
]

function capitalizeExchange(name) {
  if (!name) {
    return '-'
  }

  return name.charAt(0).toUpperCase() + name.slice(1)
}

function formatPrice(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '-'
  }

  return number.toLocaleString('en-US', {
    maximumSignificantDigits: 8,
  })
}

function formatPercent(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '0.00%'
  }

  return `${number.toFixed(2)}%`
}

function formatVolume(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '$0'
  }

  return number.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

function formatDateTime(value) {
  if (!value) {
    return 'Waiting for data'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Waiting for data'
  }

  return date.toLocaleString()
}

function getExchangeOptions(data) {
  const exchanges = new Set()

  data.forEach((opportunity) => {
    if (opportunity.buy_exchange) {
      exchanges.add(opportunity.buy_exchange)
    }

    if (opportunity.sell_exchange) {
      exchanges.add(opportunity.sell_exchange)
    }
  })

  return Array.from(exchanges).sort()
}

function getBaseToken(symbol) {
  if (!symbol) {
    return ''
  }

  return String(symbol).split('/')[0].split(':')[0]
}

function getCoinLink(symbol, coinSlugs) {
  const baseToken = getBaseToken(symbol).toUpperCase()
  const slug = coinSlugs[baseToken]

  if (slug) {
    return `https://www.coingecko.com/en/coins/${encodeURIComponent(slug)}`
  }

  return `https://coinmarketcap.com/search/?q=${encodeURIComponent(baseToken)}`
}

function App() {
  const [opportunities, setOpportunities] = useState([])
  const [coinSlugs, setCoinSlugs] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isInitialLoading, setIsInitialLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [secondsUntilRefresh, setSecondsUntilRefresh] = useState(REFRESH_SECONDS)
  const [deselectedExchanges, setDeselectedExchanges] = useState([])
  const [minSpread, setMinSpread] = useState(0)
  const [minVolume, setMinVolume] = useState(0)

  useEffect(() => {
    let isMounted = true

    async function fetchDashboardData() {
      if (!isMounted) {
        return
      }

      setIsRefreshing(true)

      try {
        const [opportunitiesResponse, marketsResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/opportunities`),
          fetch(`${API_BASE_URL}/api/markets`),
        ])

        if (!opportunitiesResponse.ok) {
          throw new Error(`Opportunities request failed: ${opportunitiesResponse.status}`)
        }

        if (!marketsResponse.ok) {
          throw new Error(`Markets request failed: ${marketsResponse.status}`)
        }

        const opportunitiesData = await opportunitiesResponse.json()
        const marketsData = await marketsResponse.json()

        if (!isMounted) {
          return
        }

        setOpportunities(opportunitiesData.opportunities || [])
        setLastUpdated(opportunitiesData.last_updated || marketsData.last_updated || null)
        setError('')
        setSecondsUntilRefresh(REFRESH_SECONDS)
      } catch (fetchError) {
        if (!isMounted) {
          return
        }

        setError(fetchError.message || 'Unable to refresh dashboard data')
      } finally {
        if (isMounted) {
          setIsInitialLoading(false)
          setIsRefreshing(false)
        }
      }
    }

    fetchDashboardData()

    const refreshTimer = window.setInterval(fetchDashboardData, REFRESH_SECONDS * 1000)
    const countdownTimer = window.setInterval(() => {
      setSecondsUntilRefresh((currentSeconds) => {
        if (currentSeconds <= 1) {
          return REFRESH_SECONDS
        }

        return currentSeconds - 1
      })
    }, 1000)

    return () => {
      isMounted = false
      window.clearInterval(refreshTimer)
      window.clearInterval(countdownTimer)
    }
  }, [])

  useEffect(() => {
    let isMounted = true

    async function fetchCoinSlugs() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/coin-slugs`)

        if (!response.ok) {
          return
        }

        const data = await response.json()

        if (isMounted) {
          setCoinSlugs(data.slugs || {})
        }
      } catch {
        if (isMounted) {
          setCoinSlugs({})
        }
      }
    }

    fetchCoinSlugs()

    return () => {
      isMounted = false
    }
  }, [])

  const exchangeOptions = getExchangeOptions(opportunities)
  const activeSelectedExchanges = exchangeOptions.filter(
    (exchange) => !deselectedExchanges.includes(exchange),
  )
  const filteredOpportunities = opportunities
    .filter((opportunity) => {
      const spread = Number(opportunity.spread_percent)
      const buyVolume = Number(opportunity.volume_buy)
      const sellVolume = Number(opportunity.volume_sell)
      const matchesExchange =
        activeSelectedExchanges.includes(opportunity.buy_exchange) ||
        activeSelectedExchanges.includes(opportunity.sell_exchange)

      return (
        matchesExchange &&
        Number.isFinite(spread) &&
        spread >= minSpread &&
        Number.isFinite(buyVolume) &&
        Number.isFinite(sellVolume) &&
        buyVolume >= minVolume &&
        sellVolume >= minVolume
      )
    })
    .sort((first, second) => Number(second.spread_percent) - Number(first.spread_percent))
  const filteredExchangeCount = getExchangeOptions(filteredOpportunities).length
  const bestSpread = filteredOpportunities.length > 0 ? filteredOpportunities[0].spread_percent : 0
  const isConnected = !error

  function toggleExchange(exchange) {
    setDeselectedExchanges((currentDeselected) => {
      if (currentDeselected.includes(exchange)) {
        return currentDeselected.filter((deselectedExchange) => deselectedExchange !== exchange)
      }

      return [...currentDeselected, exchange].sort()
    })
  }

  function resetFilters() {
    setDeselectedExchanges([])
    setMinSpread(0)
    setMinVolume(0)
  }

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <div className="status-row">
            <span
              className={`status-dot ${isConnected ? 'status-dot--connected' : 'status-dot--error'}`}
              aria-label={isConnected ? 'Connected' : 'Error'}
            />
            <span className="status-text">{isConnected ? 'Connected' : 'Error'}</span>
          </div>
          <h1>Crypto Arbitrage Dashboard</h1>
          <p>Live cross-exchange spread detection</p>
        </div>

        <div className="refresh-panel">
          <span>Last updated</span>
          <strong>{formatDateTime(lastUpdated)}</strong>
          <small>
            {isRefreshing && !isInitialLoading ? 'Refreshing now' : `Auto-refresh in ${secondsUntilRefresh}s`}
          </small>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="summary-grid" aria-label="Dashboard summary">
        <article className="summary-card">
          <span>Total Opportunities</span>
          <strong>{filteredOpportunities.length}</strong>
        </article>
        <article className="summary-card">
          <span>Best Spread</span>
          <strong className={bestSpread >= 5 ? 'metric-danger' : 'metric-positive'}>
            {formatPercent(bestSpread)}
          </strong>
        </article>
        <article className="summary-card">
          <span>Exchanges Monitored</span>
          <strong>{filteredExchangeCount}</strong>
        </article>
      </section>

      <section className="table-section" aria-label="Arbitrage opportunities">
        <div className="section-heading">
          <div>
            <h2>Opportunities</h2>
            <p>Sorted by spread percentage descending</p>
          </div>
          {isRefreshing && !isInitialLoading ? <span className="refresh-chip">Refreshing</span> : null}
        </div>

        <div className="filter-panel" aria-label="Opportunity filters">
          <div className="filter-group filter-group--exchanges">
            <span className="filter-label">Exchanges</span>
            <div className="exchange-filter-list">
              {exchangeOptions.length > 0 ? (
                exchangeOptions.map((exchange) => (
                  <button
                    className={
                      activeSelectedExchanges.includes(exchange)
                        ? 'exchange-toggle exchange-toggle--active'
                        : 'exchange-toggle'
                    }
                    key={exchange}
                    onClick={() => toggleExchange(exchange)}
                    type="button"
                  >
                    {capitalizeExchange(exchange)}
                  </button>
                ))
              ) : (
                <span className="filter-empty">No exchanges yet</span>
              )}
            </div>
          </div>

          <label className="filter-group">
            <span className="filter-label">Minimum Spread %</span>
            <input
              className="number-input"
              max="15"
              min="0"
              onChange={(event) => setMinSpread(Number(event.target.value))}
              step="0.1"
              type="number"
              value={minSpread}
            />
          </label>

          <label className="filter-group">
            <span className="filter-label">Minimum Volume</span>
            <select
              className="select-input"
              onChange={(event) => setMinVolume(Number(event.target.value))}
              value={minVolume}
            >
              {VOLUME_FILTERS.map((filter) => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
            </select>
          </label>

          <button className="reset-button" onClick={resetFilters} type="button">
            Reset filters
          </button>
        </div>

        <div className="filtered-count">
          Showing {filteredOpportunities.length} of {opportunities.length} opportunities
        </div>

        {isInitialLoading ? (
          <div className="loading-state">
            <span className="spinner" />
            <span>Loading opportunities</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Buy Exchange</th>
                  <th>Sell Exchange</th>
                  <th>Buy Price</th>
                  <th>Sell Price</th>
                  <th>Spread %</th>
                  <th>Volume (Buy)</th>
                  <th>Volume (Sell)</th>
                </tr>
              </thead>
              <tbody>
                {filteredOpportunities.length > 0 ? (
                  filteredOpportunities.map((opportunity) => {
                    const spread = Number(opportunity.spread_percent)
                    const isHighSpread = Number.isFinite(spread) && spread >= 5

                    return (
                      <tr
                        key={`${opportunity.symbol}-${opportunity.buy_exchange}-${opportunity.sell_exchange}`}
                      >
                        <td className="symbol-cell">
                          <a
                            className="symbol-link"
                            href={getCoinLink(opportunity.symbol, coinSlugs)}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {opportunity.symbol}
                          </a>
                        </td>
                        <td>{capitalizeExchange(opportunity.buy_exchange)}</td>
                        <td>{capitalizeExchange(opportunity.sell_exchange)}</td>
                        <td>{formatPrice(opportunity.buy_price)}</td>
                        <td>{formatPrice(opportunity.sell_price)}</td>
                        <td>
                          <span className={isHighSpread ? 'spread spread--danger' : 'spread'}>
                            {formatPercent(opportunity.spread_percent)}
                          </span>
                        </td>
                        <td>{formatVolume(opportunity.volume_buy)}</td>
                        <td>{formatVolume(opportunity.volume_sell)}</td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td className="empty-state" colSpan="8">
                      No opportunities found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
