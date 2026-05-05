import logging
from datetime import datetime, timezone

import config
from fetcher import get_common_pairs


logger = logging.getLogger(__name__)


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def find_opportunities(markets_data):
    opportunities = []

    try:
        common_pairs = get_common_pairs(markets_data)
        common_pairs = [
            s for s in common_pairs if s.split("/")[0].upper() not in config.EXCLUDED_SYMBOLS
        ]
    except Exception as exc:
        logger.exception("Failed to get common pairs: %s", exc)
        return opportunities

    for symbol in common_pairs:
        try:
            quotes = []

            for exchange_name, exchange_markets in markets_data.items():
                try:
                    if not isinstance(exchange_markets, dict) or symbol not in exchange_markets:
                        continue

                    ticker = exchange_markets[symbol]
                    ask = _to_float(ticker.get("ask"))
                    bid = _to_float(ticker.get("bid"))
                    volume = _to_float(ticker.get("volume"))

                    if ask is None or bid is None or volume is None:
                        continue
                    if ask <= 0 or bid <= 0:
                        continue

                    quotes.append(
                        {
                            "exchange": exchange_name,
                            "ask": ask,
                            "bid": bid,
                            "volume": volume,
                        }
                    )
                except Exception as exc:
                    logger.exception(
                        "Failed to process %s ticker on %s: %s",
                        symbol,
                        exchange_name,
                        exc,
                    )

            if len(quotes) < 2:
                continue

            best_buy = min(quotes, key=lambda quote: quote["ask"])
            best_sell = max(quotes, key=lambda quote: quote["bid"])

            if best_buy["exchange"] == best_sell["exchange"]:
                continue

            spread_percent = ((best_sell["bid"] - best_buy["ask"]) / best_buy["ask"]) * 100

            if spread_percent < config.MIN_SPREAD_PERCENT:
                continue
            if spread_percent > config.MAX_SPREAD_PERCENT:
                continue
            if best_buy["volume"] < config.MIN_VOLUME_USD:
                continue
            if best_sell["volume"] < config.MIN_VOLUME_USD:
                continue

            base_name_buy = (
                markets_data.get(best_buy["exchange"], {}).get(symbol, {}).get("base_name", "")
            )
            base_name_sell = (
                markets_data.get(best_sell["exchange"], {}).get(symbol, {}).get("base_name", "")
            )

            opportunities.append(
                {
                    "symbol": symbol,
                    "buy_exchange": best_buy["exchange"],
                    "sell_exchange": best_sell["exchange"],
                    "buy_price": best_buy["ask"],
                    "sell_price": best_sell["bid"],
                    "spread_percent": spread_percent,
                    "volume_buy": best_buy["volume"],
                    "volume_sell": best_sell["volume"],
                    "base_name_buy": base_name_buy,
                    "base_name_sell": base_name_sell,
                    "name_mismatch": (
                        bool(base_name_buy and base_name_sell)
                        and base_name_buy.lower() != base_name_sell.lower()
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            logger.exception("Failed to find opportunity for %s: %s", symbol, exc)

    try:
        return sorted(
            opportunities,
            key=lambda opportunity: opportunity["spread_percent"],
            reverse=True,
        )
    except Exception as exc:
        logger.exception("Failed to sort opportunities: %s", exc)
        return opportunities
