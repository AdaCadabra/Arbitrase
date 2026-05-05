import logging

import ccxt
import config


logger = logging.getLogger(__name__)


def _initialize_exchanges():
    exchanges = {}

    for exchange_name in config.EXCHANGES:
        try:
            exchange_class = getattr(ccxt, exchange_name)
            exchanges[exchange_name] = exchange_class(
                {
                    "timeout": config.REQUEST_TIMEOUT_MS,
                    "enableRateLimit": True,
                }
            )
        except Exception as exc:
            logger.exception("Failed to initialize exchange %s: %s", exchange_name, exc)

    return exchanges


EXCHANGE_CLIENTS = _initialize_exchanges()


def _ticker_volume(ticker):
    quote_volume = ticker.get("quoteVolume")
    if quote_volume is not None:
        return quote_volume

    base_volume = ticker.get("baseVolume")
    last_price = ticker.get("last")
    if base_volume is not None and last_price is not None:
        try:
            return base_volume * last_price
        except TypeError:
            return base_volume

    return base_volume


def fetch_all_markets():
    markets_data = {}

    for exchange_name, exchange in EXCHANGE_CLIENTS.items():
        try:
            markets = exchange.load_markets()
            requested_symbols = [
                symbol
                for symbol, market in markets.items()
                if market.get("quote") == config.QUOTE_CURRENCY
            ]
            available_spot_symbols = {
                symbol
                for symbol, market in markets.items()
                if market.get("spot") is True
                and market.get("active") is True
                and ":" not in symbol
            }
            usdt_symbols = [
                symbol for symbol in requested_symbols if symbol in available_spot_symbols
            ]

            if not usdt_symbols:
                logger.warning("No valid active spot symbols found for %s", exchange_name)
                continue

            try:
                tickers = exchange.fetch_tickers(usdt_symbols)
            except Exception as exc:
                logger.exception(
                    "Failed to fetch tickers for %s, falling back to per-symbol fetch: %s",
                    exchange_name,
                    exc,
                )
                tickers = {}
                for symbol in usdt_symbols:
                    try:
                        tickers[symbol] = exchange.fetch_ticker(symbol)
                    except Exception as symbol_exc:
                        logger.exception(
                            "Failed to fetch ticker for %s on %s: %s",
                            symbol,
                            exchange_name,
                            symbol_exc,
                        )

            exchange_markets = {}
            for symbol in usdt_symbols:
                ticker = tickers.get(symbol)
                if not ticker:
                    continue

                market = exchange.markets.get(symbol, {})
                base_name = (
                    market.get("info", {}).get("base_name")
                    or market.get("name")
                    or market.get("base", symbol.split("/")[0])
                )

                exchange_markets[symbol] = {
                    "last": ticker.get("last"),
                    "bid": ticker.get("bid"),
                    "ask": ticker.get("ask"),
                    "volume": _ticker_volume(ticker),
                    "base_name": base_name,
                }

            markets_data[exchange_name] = exchange_markets
        except Exception as exc:
            logger.exception("Failed to fetch markets for %s: %s", exchange_name, exc)
            continue

    return markets_data


def get_common_pairs(markets_data):
    try:
        pair_counts = {}

        for exchange_markets in markets_data.values():
            if not isinstance(exchange_markets, dict):
                continue

            for symbol in exchange_markets:
                pair_counts[symbol] = pair_counts.get(symbol, 0) + 1

        return [symbol for symbol, count in pair_counts.items() if count >= 2]
    except Exception as exc:
        logger.exception("Failed to find common pairs: %s", exc)
        return []
