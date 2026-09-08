"""Public Binance USDT-M futures market data client (no auth, no trading)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence

import requests

logger = logging.getLogger(__name__)

# fapi.binance.com is often geo-blocked (HTTP 451). www.binance.com/fapi is a
# common public fallback that still serves USDT-M klines.
DEFAULT_BASES: Sequence[str] = (
    "https://fapi.binance.com",
    "https://www.binance.com",
)

# Binance hard limit per klines request
MAX_KLINES_PER_REQUEST = 1500


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

    def _request_klines(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """GET /fapi/v1/klines with base fallbacks. Returns parsed candles."""
        last_error: Optional[Exception] = None
        symbol = params.get("symbol", "?")

        for base in self._bases:
            url = f"{base}/fapi/v1/klines"
            logger.debug("Fetching klines %s via %s params=%s", symbol, base, params)
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
                    self.base_url = base
                # Prefer working base on subsequent requests
                if self._bases[0] != base:
                    self._bases = [base] + [b for b in self._bases if b != base]
                return self._parse_klines(raw)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Binance request failed via %s: %s", base, exc)

        raise RuntimeError(
            f"Unable to fetch klines for {symbol} from any Binance base "
            f"({', '.join(self._bases)}). Last error: {last_error}"
        )

    def get_klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return candle data as dicts with open/high/low/close/volume.
        Uses GET /fapi/v1/klines (public). Tries fallback bases on 451/403.
        Optional start_time / end_time are Binance millisecond timestamps.
        """
        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(int(limit), MAX_KLINES_PER_REQUEST),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self._request_klines(params)

    def get_historical_klines(
        self,
        symbol: str,
        interval: str = "15m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_candles: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Paginate klines to cover a long history (Binance max 1500/request).

        Walks *forward* from ``start_time`` using ``startTime`` cursors.
        When ``start_time`` is omitted, walks *backward* from ``end_time``
        (default: now) using ``endTime`` only (no startTime — Binance returns
        the newest ``limit`` bars ending at endTime).

        Returns candles sorted ascending by open_time.
        """
        if end_time is None:
            end_time = int(time.time() * 1000)

        collected: List[Dict[str, Any]] = []

        if start_time is not None:
            # Forward pagination: Binance returns bars from startTime ascending
            cursor_start = int(start_time)
            while cursor_start <= end_time:
                batch_limit = MAX_KLINES_PER_REQUEST
                if max_candles is not None:
                    remaining = max_candles - len(collected)
                    if remaining <= 0:
                        break
                    batch_limit = min(batch_limit, remaining)

                params: Dict[str, Any] = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": batch_limit,
                    "startTime": cursor_start,
                    "endTime": int(end_time),
                }
                batch = self._request_klines(params)
                if not batch:
                    break

                collected.extend(batch)
                last_open = batch[-1]["open_time"]
                # Advance past the last candle
                cursor_start = last_open + 1

                if len(batch) < batch_limit:
                    break
                if max_candles is not None and len(collected) >= max_candles:
                    collected = collected[:max_candles]
                    break
                if last_open >= end_time:
                    break

                time.sleep(0.15)
        else:
            # Backward pagination from end_time (no startTime in request)
            cursor_end = int(end_time)
            while True:
                batch_limit = MAX_KLINES_PER_REQUEST
                if max_candles is not None:
                    remaining = max_candles - len(collected)
                    if remaining <= 0:
                        break
                    batch_limit = min(batch_limit, remaining)

                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": batch_limit,
                    "endTime": cursor_end,
                }
                batch = self._request_klines(params)
                if not batch:
                    break

                collected = batch + collected
                oldest_open = batch[0]["open_time"]

                if len(batch) < batch_limit:
                    break
                if max_candles is not None and len(collected) >= max_candles:
                    collected = collected[-max_candles:]
                    break

                cursor_end = oldest_open - 1
                time.sleep(0.15)

        # Deduplicate by open_time and sort; clamp to [start, end]
        by_time: Dict[int, Dict[str, Any]] = {}
        for c in collected:
            ot = c["open_time"]
            if start_time is not None and ot < start_time:
                continue
            if ot > end_time:
                continue
            by_time[ot] = c
        return [by_time[k] for k in sorted(by_time)]

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
