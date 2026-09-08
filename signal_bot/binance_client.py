"""Public Binance USDT-M futures market data client (no auth, no trading)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import requests

logger = logging.getLogger(__name__)

# fapi.binance.com is often geo-blocked (HTTP 451). www.binance.com/fapi is a
# common public fallback that still serves USDT-M klines.
DEFAULT_BASES: Sequence[str] = (
    "https://fapi.binance.com",
    "https://www.binance.com",
)


class BinanceFuturesClient:
    """Fetch public klines from Binance USDT-M futures."""

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        timeout: float = 15.0,
        fallback_bases: Optional[Sequence[str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "telegram-crypto-signal-bot/1.0"})
        bases = [self.base_url]
        for b in fallback_bases if fallback_bases is not None else DEFAULT_BASES:
            b = b.rstrip("/")
            if b not in bases:
                bases.append(b)
        self._bases = bases

    def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Return candle data as dicts with open/high/low/close/volume.
        Uses GET /fapi/v1/klines (public). Tries fallback bases on 451/403.
        """
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        last_error: Optional[Exception] = None

        for base in self._bases:
            url = f"{base}/fapi/v1/klines"
            logger.debug("Fetching klines %s %s limit=%s via %s", symbol, interval, limit, base)
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code in (403, 451):
                    logger.warning(
                        "Binance %s returned %s for %s; trying next base",
                        base,
                        resp.status_code,
                        symbol,
                    )
                    last_error = requests.HTTPError(
                        f"{resp.status_code} from {base}",
                        response=resp,
                    )
                    continue
                resp.raise_for_status()
                raw = resp.json()
                if base != self.base_url:
                    # Remember working base for subsequent calls
                    self.base_url = base
                return self._parse_klines(raw)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Binance request failed via %s: %s", base, exc)

        raise RuntimeError(
            f"Unable to fetch klines for {symbol} from any Binance base "
            f"({', '.join(self._bases)}). Last error: {last_error}"
        )

    @staticmethod
    def _parse_klines(raw: list) -> List[Dict[str, Any]]:
        candles: List[Dict[str, Any]] = []
        for row in raw:
            candles.append(
                {
                    "open_time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "close_time": int(row[6]),
                }
            )
        return candles

    def closes(self, symbol: str, interval: str = "15m", limit: int = 200) -> List[float]:
        """Convenience: close prices only."""
        return [c["close"] for c in self.get_klines(symbol, interval, limit)]
