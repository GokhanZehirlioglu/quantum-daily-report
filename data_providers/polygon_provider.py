"""
Polygon.io provider — PRIMARY data source.

Uses the Polygon REST API v2 to fetch historical daily OHLCV.

API key is read from the environment variable defined in ``config/settings.yaml``
under ``data_providers.primary.env_api_key`` (default: POLYGON_API_KEY).

Documentation: https://polygon.io/docs/stocks/get_v2_aggs_ticker__stocksticker__range__multiplier__timespan__from__to
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from data_providers.base import BaseProvider, DailyData
from core.exceptions import ProviderError

# ─── CONSTANTS ─────────────────────────────────────────────

_POLYGON_BASE_URL: str = "https://api.polygon.io"
_DEFAULT_TIMEOUT: int = 15
_RATE_LIMIT_WINDOW: float = 60.0  # seconds


class PolygonProvider(BaseProvider):
    """
    Fetches daily OHLCV data from Polygon.io.

    Config keys (passed via ``__init__(config=...)`` or loaded from settings.yaml):
        ``env_api_key`` (str):       Environment variable name holding the API key.
                                     Default: ``"POLYGON_API_KEY"``.
        ``base_url`` (str):          Polygon API base URL.
                                     Default: ``"https://api.polygon.io"``.
        ``timeout_seconds`` (int):   HTTP request timeout.
                                     Default: ``15``.
        ``rate_limit_per_minute`` (int): Max requests per minute.
                                        Default: ``5``.

    Environment variable:
        ``POLYGON_API_KEY`` — Your Polygon.io API key (required).
    """

    PROVIDER_NAME: str = "polygon"

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._env_key: str = self.config.get("env_api_key", "POLYGON_API_KEY")
        self._api_key: str = os.environ.get(self._env_key, "")
        self._base_url: str = self.config.get("base_url", _POLYGON_BASE_URL)
        self._timeout: int = int(self.config.get("timeout_seconds", _DEFAULT_TIMEOUT))

        # Rate limiting — simple per-instance token bucket
        self._max_rpm: int = int(self.config.get("rate_limit_per_minute", 5))
        self._request_timestamps: list[float] = []

    # ── Public API ─────────────────────────────────────

    def get_daily_data(self, symbol: str, target_date: str) -> DailyData:
        """
        Fetch daily OHLCV for *symbol* on *target_date*.

        Args:
            symbol: Ticker symbol (e.g. ``"QBTS"``).
            target_date: ISO date string ``"YYYY-MM-DD"``.

        Returns:
            A validated ``DailyData`` instance.

        Raises:
            ProviderError: If the API key is missing, rate-limit is exceeded,
                           the HTTP request fails, or the response is empty.
        """
        self._enforce_rate_limit()

        if not self._api_key:
            raise ProviderError(
                message=f"Polygon API key not set. Set ${self._env_key}.",
                provider_name=self.PROVIDER_NAME,
            )

        url = (
            f"{self._base_url}/v2/aggs/ticker/{symbol.upper()}"
            f"/range/1/day/{target_date}/{target_date}"
            f"?adjusted=true&sort=asc&limit=1"
        )
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            resp = requests.get(url, headers=headers, timeout=self._timeout)
            self._request_timestamps.append(time.monotonic())
        except requests.Timeout:
            raise ProviderError(
                message=f"Polygon request timed out ({self._timeout}s) for {symbol} on {target_date}.",
                provider_name=self.PROVIDER_NAME,
            )
        except requests.ConnectionError as exc:
            raise ProviderError(
                message=f"Polygon connection failed for {symbol}: {exc}",
                provider_name=self.PROVIDER_NAME,
            )

        if resp.status_code == 429:
            raise ProviderError(
                message=f"Polygon rate limit exceeded for {symbol} on {target_date}.",
                provider_name=self.PROVIDER_NAME,
                status_code=429,
            )
        if resp.status_code == 403:
            raise ProviderError(
                message=f"Polygon auth error (403) — check API key for {symbol}.",
                provider_name=self.PROVIDER_NAME,
                status_code=403,
            )
        if resp.status_code != 200:
            raise ProviderError(
                message=f"Polygon HTTP {resp.status_code} for {symbol} on {target_date}: {resp.text[:200]}",
                provider_name=self.PROVIDER_NAME,
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()

        # Polygon wraps results in a ``results`` array
        results: list[dict[str, Any]] = payload.get("results", [])
        if not results:
            raise ProviderError(
                message=f"Polygon returned empty results for {symbol} on {target_date}.",
                provider_name=self.PROVIDER_NAME,
            )

        bar = results[0]
        return DailyData(
            open=float(bar["o"]),
            high=float(bar["h"]),
            low=float(bar["l"]),
            close=float(bar["c"]),
            volume=int(bar["v"]),
            date=_ts_to_date(bar.get("t", 0)),
            target_date=target_date,
            provider_name=self.PROVIDER_NAME,
            metadata={"raw_response_summary": {"results_count": len(results)}},
        )

    # ── Internals ──────────────────────────────────────

    def _enforce_rate_limit(self) -> None:
        """Sleep if we've hit the per-minute cap."""
        now = time.monotonic()
        window_start = now - _RATE_LIMIT_WINDOW
        # Drop timestamps outside the sliding window
        self._request_timestamps = [t for t in self._request_timestamps if t > window_start]

        if len(self._request_timestamps) >= self._max_rpm:
            sleep_for = self._request_timestamps[0] + _RATE_LIMIT_WINDOW - now
            if sleep_for > 0:
                time.sleep(sleep_for + 0.5)  # small buffer


def _ts_to_date(ts: int) -> str:
    """
    Convert Polygon's millisecond Unix timestamp to ``YYYY-MM-DD``.

    Polygon nanos: ``t`` field is in **milliseconds** since epoch.
    """
    if ts > 1_000_000_000_000_000:  # nanoseconds fallback
        ts //= 1_000_000
    elif ts > 1_000_000_000_000:  # microseconds fallback
        ts //= 1_000
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
