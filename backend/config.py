# Exchanges to monitor
EXCHANGES = ["binance", "okx", "bybit", "kraken", "kucoin", "gateio", "bitget"]

# Only monitor USDT pairs to ensure same asset comparison
QUOTE_CURRENCY = "USDT"

# Arbitrage filter thresholds
MIN_SPREAD_PERCENT = 0.2
MAX_SPREAD_PERCENT = 15.0
MIN_VOLUME_USD = 100000

# Cache settings
CACHE_TTL_SECONDS = 60

# Fetch settings
FETCH_INTERVAL_SECONDS = 60
REQUEST_TIMEOUT_MS = 10000

# Chiliz fan tokens - excluded because each exchange lists different contract addresses
# making cross-exchange arbitrage impossible for these tokens
EXCLUDED_SYMBOLS = {
    "CITY", "BAR", "PSG", "JUV", "ACM", "INTER", "ATM", "ASR", "NAP", "GAL",
    "SPURS", "PORTO", "LEV", "OG", "AFC", "BARCA", "MENGO", "GALO", "SCCP",
    "SANTOS", "LAZIO", "ALPINE", "NAVI", "TRADE"
}
