import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from arbitrage import find_opportunities
from fetcher import fetch_all_markets


EXCHANGE_LOGOS = {
    "binance": "https://github.com/user-attachments/assets/e9419b93-ccb0-46aa-9bff-c883f096274b",
    "okx": "https://user-images.githubusercontent.com/1294454/152485636-38b19e4a-bece-4dec-979a-5982859ffc04.jpg",
    "bybit": "https://github.com/user-attachments/assets/97a5d0b3-de10-423d-90e1-6620960025ed",
    "kucoin": "https://user-images.githubusercontent.com/51840849/87295558-132aaf80-c50e-11ea-9801-a2fb0c57c799.jpg",
    "gateio": "https://github.com/user-attachments/assets/64f988c5-07b6-4652-b5c1-679a6bf67c85",
    "bitget": "https://github.com/user-attachments/assets/fbaa10cc-a277-441d-a5b7-997dd9a87658",
}


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


COINGECKO_COINS_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
COIN_SLUG_CACHE = {}
COIN_SLUG_AMBIGUOUS_CACHE = []

cache = {
    "markets_data": {},
    "opportunities": [],
    "last_updated": None,
}
cache_lock = asyncio.Lock()
coin_slug_lock = asyncio.Lock()


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _fetch_coin_slugs_sync():
    try:
        request = Request(
            COINGECKO_COINS_LIST_URL,
            headers={"User-Agent": "Arbitrase/1.0"},
        )
        timeout_seconds = getattr(config, "REQUEST_TIMEOUT_MS", 10000) / 1000

        with urlopen(request, timeout=timeout_seconds) as response:
            coins = json.loads(response.read().decode("utf-8"))

        symbol_counts = {}
        for coin in coins:
            symbol = coin.get("symbol")

            if not symbol:
                continue

            symbol_key = symbol.upper()
            symbol_counts[symbol_key] = symbol_counts.get(symbol_key, 0) + 1

        slugs = {}
        ambiguous = sorted(
            symbol for symbol, count in symbol_counts.items() if count > 1
        )
        for coin in coins:
            symbol = coin.get("symbol")
            coin_id = coin.get("id")

            if not symbol or not coin_id:
                continue

            symbol_key = symbol.upper()
            if symbol_counts.get(symbol_key) == 1:
                slugs[symbol_key] = coin_id

        return slugs, ambiguous
    except (OSError, URLError, json.JSONDecodeError, TypeError) as exc:
        logger.exception("Failed to fetch CoinGecko coin slugs: %s", exc)
        return {}, []
    except Exception as exc:
        logger.exception("Unexpected error fetching CoinGecko coin slugs: %s", exc)
        return {}, []


async def refresh_coin_slug_cache():
    try:
        logger.info("Refreshing CoinGecko coin slug cache")
        slugs, ambiguous = await asyncio.to_thread(_fetch_coin_slugs_sync)

        async with coin_slug_lock:
            COIN_SLUG_CACHE.clear()
            COIN_SLUG_CACHE.update(slugs)
            COIN_SLUG_AMBIGUOUS_CACHE.clear()
            COIN_SLUG_AMBIGUOUS_CACHE.extend(ambiguous)

        logger.info(
            "Coin slug cache refreshed with %s symbols and %s ambiguous symbols",
            len(slugs),
            len(ambiguous),
        )
    except Exception as exc:
        logger.exception("Failed to refresh coin slug cache: %s", exc)


async def refresh_cache():
    try:
        logger.info("Refreshing market data")
        markets_data = await asyncio.to_thread(fetch_all_markets)
        opportunities = await asyncio.to_thread(find_opportunities, markets_data)
        timestamp = _utc_now_iso()

        async with cache_lock:
            cache["markets_data"] = markets_data
            cache["opportunities"] = opportunities
            cache["last_updated"] = timestamp

        logger.info(
            "Cache refreshed with %s exchanges and %s opportunities",
            len(markets_data),
            len(opportunities),
        )
    except Exception as exc:
        logger.exception("Failed to refresh cache: %s", exc)


async def refresh_loop():
    while True:
        await asyncio.sleep(config.FETCH_INTERVAL_SECONDS)
        await refresh_cache()


@asynccontextmanager
async def lifespan(app):
    logger.info("Starting Crypto Arbitrage Dashboard")
    await refresh_cache()
    await refresh_coin_slug_cache()
    refresh_task = asyncio.create_task(refresh_loop())

    try:
        yield
    finally:
        logger.info("Stopping Crypto Arbitrage Dashboard")
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            logger.info("Background refresh task cancelled")


app = FastAPI(title="Crypto Arbitrage Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/opportunities")
async def get_opportunities():
    try:
        async with cache_lock:
            opportunities = list(cache["opportunities"])
            last_updated = cache["last_updated"]

        return {
            "opportunities": opportunities,
            "last_updated": last_updated,
            "count": len(opportunities),
        }
    except Exception as exc:
        logger.exception("Failed to return opportunities: %s", exc)
        return {"opportunities": [], "last_updated": None, "count": 0}


@app.get("/api/markets")
async def get_markets():
    try:
        async with cache_lock:
            markets_data = dict(cache["markets_data"])
            last_updated = cache["last_updated"]

        exchanges = {
            exchange_name: {"pair_count": len(exchange_markets)}
            for exchange_name, exchange_markets in markets_data.items()
            if isinstance(exchange_markets, dict)
        }

        return {"exchanges": exchanges, "last_updated": last_updated}
    except Exception as exc:
        logger.exception("Failed to return markets summary: %s", exc)
        return {"exchanges": {}, "last_updated": None}


@app.get("/api/coin-slugs")
async def get_coin_slugs():
    try:
        async with coin_slug_lock:
            slugs = dict(COIN_SLUG_CACHE)
            ambiguous = list(COIN_SLUG_AMBIGUOUS_CACHE)

        return {"slugs": slugs, "ambiguous": ambiguous}
    except Exception as exc:
        logger.exception("Failed to return coin slugs: %s", exc)
        return {"slugs": {}, "ambiguous": []}


@app.get("/api/exchange-logos")
async def get_exchange_logos():
    return {"logos": dict(EXCHANGE_LOGOS)}


@app.get("/health")
async def health():
    try:
        async with cache_lock:
            last_updated = cache["last_updated"]

        return {"status": "ok", "last_updated": last_updated}
    except Exception as exc:
        logger.exception("Failed to return health status: %s", exc)
        return {"status": "ok", "last_updated": None}
