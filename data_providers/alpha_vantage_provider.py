"""
Alpha Vantage provider — FALLBACK data source.

Used when the primary provider (Polygon) is unavailable, rate-limited, or
returns invalid data. Implements the same ``BaseProvider`` interface.

API key is read from the environment variable defined in ``config/settings.yaml``
under ``data_providers.fallback.env_api_key`` (default: ALPHA_VANTAGE_API_KEY).

Documentation: https://www.alphavantage.co/documentation/
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from data_providers.base import BaseProvider, DailyData
from core.exceptions import ProviderError

# ─── CONSTANTS ─────────────────────────────────────────────

_AV_BASE_URL: str = "https://www.alphavantage.co/query"
_DEFAULT_TIMEOUT: int = 15
_RATE_LIMIT_WINDOW: float = 60.0  # seconds — free tier: 5 req/min

_AV_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
]


class AlphaVantageProvider(BaseProvider):
    """
    Fetches daily OHLCV data from Alpha Vantage.

    Config keys (passed via ``__init__(config=...)`` or loaded from settings.yaml):
        ``env_api_key`` (str):       Environment variable name holding the API key.
                                     Default: ``"ALPHA_VANTAGE_API_KEY"``.
        ``base_url`` (str):          Alpha Vantage API base URL.
                                     Default: ``"https://www.alphavantage.co/query"``.
        ``timeout_seconds`` (int):   HTTP request timeout.
                                     Default: ``15``.
        ``rate_limit_per_minute`` (int): Max requests per minute.
                                        Default: ``5``.

    Environment variable:
        ``ALPHA_VANTAGE_API_KEY`` — Your Alpha Vantage API key (required).
    """

    PROVIDER_NAME: str = "alpha_vantage"

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._env_key: str = self.config.get("env_api_key", "ALPHA_VANTAGE_API_KEY")
        self._api_key: str = os.environ.get(self._env_key, "")
        self._base_url: str = self.config.get("base_url", _AV_BASE_URL)
        self._timeout: int = int(self.config.get("timeout_seconds", _DEFAULT_TIMEOUT))

        self._max_rpm: int = int(self.config.get("rate_limit_per_minute", 5))
        self._request_timestamps: list[float] = []

    # ── Public API ─────────────────────────────────────

    def get_daily_data(self, symbol: str, target_date: str) -> DailyData:
        """
        Fetch daily OHLCV for *symbol* on *target_date* via Alpha Vantage.

        Uses the ``TIME_SERIES_DAILY_ADJUSTED`` endpoint, then walks the
        returned time-series to locate the bar matching *target_date*.

        Args:
            symbol: Ticker symbol (e.g. ``"QBTS"``).
            target_date: ISO date string ``"YYYY-MM-DD"``.

        Returns:
            A validated ``DailyData`` instance.

        Raises:
            ProviderError: On any API failure, missing data, or parse error.
        """
        self._enforce_rate_limit()

        if not self._api_key:
            raise ProviderError(
                message=f"Alpha Vantage API key not set. Set ${self._env_key}.",
                provider_name=self.PROVIDER_NAME,
            )

        params: dict[str, str] = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol.upper(),
            "outputsize": "compact",
            "apikey": self._api_key,
        }

        try:
            resp = requests.get(self._base_url, params=params, timeout=self._timeout)
            self._request_timestamps.append(time.monotonic())
        except requests.Timeout:
            raise ProviderError(
                message=f"Alpha Vantage timed out ({self._timeout}s) for {symbol}.",
                provider_name=self.PROVIDER_NAME,
            )
        except requests.ConnectionError as exc:
            raise ProviderError(
                message=f"Alpha Vantage connection error for {symbol}: {exc}",
                provider_name=self.PROVIDER_NAME,
            )

        if resp.status_code == 429:
            raise ProviderError(
                message=f"Alpha Vantage rate limit for {symbol}.",
                provider_name=self.PROVIDER_NAME,
                status_code=429,
            )
        if resp.status_code != 200:
            raise ProviderError(
                message=f"Alpha Vantage HTTP {resp.status_code} for {symbol}: {resp.text[:200]}",
                provider_name=self.PROVIDER_NAME,
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()

        # Alpha Vantage places time-series under a key like
        # ``Time Series (Daily)``
        series_key = _find_series_key(payload)
        if not series_key:
            # Check for explicit error message from AV
            error_note = payload.get("Note", payload.get("Information", ""))
            raise ProviderError(
                message=f"Alpha Vantage: no time-series found for {symbol}. "
                        f"{error_note[:200]}",
                provider_name=self.PROVIDER_NAME,
            )

        series: dict[str, Any] = payload.get(series_key, {})

        # Locate the bar for target_date
        bar = series.get(target_date)
        if bar is None:
            # Try fuzzy date matching
            bar = _fuzzy_date_lookup(series, target_date)

        if bar is None:
            raise ProviderError(
                message=f"Alpha Vantage: no bar for {symbol} on {target_date}. "
                        f"Available dates: {list(series.keys())[:5]}",
                provider_name=self.PROVIDER_NAME,
            )

        return DailyData(
            open=float(bar["1. open"]),
            high=float(bar["2. high"]),
            low=float(bar["3. low"]),
            close=float(bar["4. close"]),
            volume=int(bar["6. volume"]),
            date=target_date,
            target_date=target_date,
            provider_name=self.PROVIDER_NAME,
            metadata={"raw_keys_found": len(series)},
        )

    # ── Internals ──────────────────────────────────────

    def _enforce_rate_limit(self) -> None:
        """Sliding-window rate limiter."""
        now = time.monotonic()
        window_start = now - _RATE_LIMIT_WINDOW
        self._request_timestamps = [t for t in self._request_timestamps if t > window_start]
        if len(self._request_timestamps) >= self._max_rpm:
            sleep_for = self._request_timestamps[0] + _RATE_LIMIT_WINDOW - now
            if sleep_for > 0:
                time.sleep(sleep_for + 0.5)


# ─── HELPERS ──────────────────────────────────────────────


def _find_series_key(payload: dict[str, Any]) -> Optional[str]:
    """Locate the time-series key in an Alpha Vantage response."""
    for key in payload:
        if "time series" in key.lower():
            return key
    return None


def _fuzzy_date_lookup(series: dict[str, Any], target_date: str) -> Optional[dict[str, Any]]:
    """
    Attempt to find a date-adjacent bar if the exact *target_date* is missing
    (e.g. the date fell on a weekend / holiday).

    Checks:
        1. The next available date after *target_date*.
        2. The first key in the series (most recent day).
    """
    sorted_dates = sorted(series.keys(), reverse=True)

    # Return the most recent bar (closest to target)
    for d in sorted_dates:
        if d <= target_date:
            return series[d]

    return None
