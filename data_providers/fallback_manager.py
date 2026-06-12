"""
Fallback orchestration — DataFetcher.

The ``DataFetcher`` is the single entry point for all daily data retrieval.
It owns the fallback chain and guarantees:

    1. Try primary provider (Polygon).
    2. On ANY failure (provider error OR validation failure) → try fallback.
    3. On fallback failure → raise ``Sev1DataError`` (Kill Switch).

No silent degradation. No incomplete data. Every consumer either gets
a fully validated ``DailyData`` instance, or the pipeline halts with a
clear, auditable error.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from data_providers.base import BaseProvider, DailyData
from data_providers.polygon_provider import PolygonProvider
from data_providers.alpha_vantage_provider import AlphaVantageProvider
from core.exceptions import DataError, InvalidDataError, ProviderError, Sev1DataError
from core.validation import validate_daily_data

logger = logging.getLogger("quantum.engine.data")

# ─── DEFAULT CONFIG (bootstrap) ───────────────────────────

_DEFAULT_PRIMARY_CONFIG: dict[str, Any] = {
    "env_api_key": "POLYGON_API_KEY",
    "base_url": "https://api.polygon.io",
    "timeout_seconds": 15,
    "rate_limit_per_minute": 5,
}

_DEFAULT_FALLBACK_CONFIG: dict[str, Any] = {
    "env_api_key": "ALPHA_VANTAGE_API_KEY",
    "base_url": "https://www.alphavantage.co/query",
    "timeout_seconds": 15,
    "rate_limit_per_minute": 5,
}


# ─── DATAFETCHER ──────────────────────────────────────────

class DataFetcher:
    """
    Orchestrates the data-fetching fallback chain.

    Typical usage::

        fetcher = DataFetcher()
        data = fetcher.fetch("QBTS", "2026-06-10")

    The caller receives a fully validated ``DailyData`` instance or
    a ``Sev1DataError`` is raised.

    Args:
        primary_config:  Config dict for the primary provider (Polygon).
        fallback_config: Config dict for the fallback provider (Alpha Vantage).
        strict_validation: If ``True`` (default), data MUST pass
                           ``validate_daily_data()`` before being returned.
    """

    def __init__(
        self,
        primary_config: Optional[dict[str, Any]] = None,
        fallback_config: Optional[dict[str, Any]] = None,
        strict_validation: bool = True,
    ) -> None:
        self._strict: bool = strict_validation

        # Instantiate providers (lazy — one instance per fetcher lifecycle)
        self._primary: BaseProvider = PolygonProvider(
            config=primary_config or _DEFAULT_PRIMARY_CONFIG,
        )
        self._fallback: BaseProvider = AlphaVantageProvider(
            config=fallback_config or _DEFAULT_FALLBACK_CONFIG,
        )

    # ── Public API ─────────────────────────────────────

    def fetch(self, symbol: str, target_date: str) -> DailyData:
        """
        Fetch validated daily data for *symbol* on *target_date*.

        Fallback chain:
            1. ``PolygonProvider.get_daily_data()``
            2. ``validate_daily_data()``
            3. If either fails → ``AlphaVantageProvider.get_daily_data()``
            4. ``validate_daily_data()``
            5. If both fail → ``Sev1DataError``

        Args:
            symbol: Ticker symbol (e.g. ``"QBTS"``).
            target_date: ISO date string ``"YYYY-MM-DD"``.

        Returns:
            A fully validated ``DailyData`` instance.

        Raises:
            Sev1DataError: If ALL providers have been exhausted without
                           producing valid data.
        """
        errors: list[DataError] = []
        attempted: list[str] = []

        # ── PHASE 1: Primary ──────────────────────────
        try:
            data = self._primary.get_daily_data(symbol, target_date)
            attempted.append(self._primary.PROVIDER_NAME)

            if self._strict:
                validated = self._validate_with_context(
                    data, self._primary.PROVIDER_NAME, symbol, target_date,
                )
                logger.info(
                    "Data OK | provider=%s symbol=%s date=%s",
                    self._primary.PROVIDER_NAME, symbol, target_date,
                )
                return validated

            return data

        except (ProviderError, InvalidDataError) as exc:
            logger.warning(
                "Primary failed | provider=%s symbol=%s reason=%s",
                self._primary.PROVIDER_NAME, symbol, exc,
            )
            errors.append(exc)
            if self._primary.PROVIDER_NAME not in attempted:
                attempted.append(self._primary.PROVIDER_NAME)

        # ── PHASE 2: Fallback ─────────────────────────
        try:
            data = self._fallback.get_daily_data(symbol, target_date)
            if self._fallback.PROVIDER_NAME not in attempted:
                attempted.append(self._fallback.PROVIDER_NAME)

            if self._strict:
                validated = self._validate_with_context(
                    data, self._fallback.PROVIDER_NAME, symbol, target_date,
                )
                logger.info(
                    "Data OK (fallback) | provider=%s symbol=%s date=%s",
                    self._fallback.PROVIDER_NAME, symbol, target_date,
                )
                return validated

            return data

        except (ProviderError, InvalidDataError) as exc:
            logger.error(
                "Fallback also failed | provider=%s symbol=%s reason=%s",
                self._fallback.PROVIDER_NAME, symbol, exc,
            )
            errors.append(exc)
            if self._fallback.PROVIDER_NAME not in attempted:
                attempted.append(self._fallback.PROVIDER_NAME)

        # ── KILL SWITCH ───────────────────────────────
        raise Sev1DataError(
            symbol=symbol,
            target_date=target_date,
            attempted_providers=attempted,
            errors=errors,
        )

    # ── Batch ─────────────────────────────────────────

    def fetch_batch(
        self,
        symbols: list[str],
        target_date: str,
    ) -> dict[str, DailyData]:
        """
        Fetch validated data for multiple symbols on the same *target_date*.

        Args:
            symbols: List of ticker symbols.
            target_date: ISO date string ``"YYYY-MM-DD"``.

        Returns:
            Dict mapping each symbol to its ``DailyData``.

        Raises:
            Sev1DataError: If any single symbol exhausts all providers.
                           (Fail-fast: one bad symbol stops the batch.)
        """
        result: dict[str, DailyData] = {}
        for sym in symbols:
            result[sym] = self.fetch(sym, target_date)
        return result

    # ── Internals ─────────────────────────────────────

    @staticmethod
    def _validate_with_context(
        data: DailyData,
        provider_name: str,
        symbol: str,
        target_date: str,
    ) -> DailyData:
        """
        Wrap ``validate_daily_data()`` with provider context.

        Injects ``target_date`` into the dict so the date-matching rule can
        compare ``data.date`` against ``data.target_date``.

        Raises:
            InvalidDataError: If validation fails.
        """
        raw = data.to_dict()
        raw["target_date"] = target_date  # ensure the validation rule has it
        validate_daily_data(raw)
        return data
