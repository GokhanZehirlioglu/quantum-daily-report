"""
Abstract base provider (Adapter pattern).

Every market-data source in the system MUST subclass ``BaseProvider``
and implement ``get_daily_data()``. This guarantees uniform output
regardless of the underlying API, which lets the fallback manager and
downstream layers treat all providers identically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Protocol


# ─── STANDARDISED OUTPUT CONTRACT ───────────────────────────

@dataclass(frozen=True)
class DailyData:
    """
    Canonical daily OHLCV data point returned by every provider.

    All fields are validated before construction — see ``core.validation``.

    Attributes:
        open: Opening price.
        high: Highest price of the session.
        low: Lowest price of the session.
        close: Closing price.
        volume: Total trading volume (shares / contracts).
        date: Trading date in ``YYYY-MM-DD`` format.
        target_date: The date that was originally requested (for reconciliation).
        provider_name: Name of the provider that sourced this data (e.g. ``"polygon"``).
        metadata: Optional provider-specific extra info (raw response snippets, etc.).
    """
    open: float
    high: float
    low: float
    close: float
    volume: int
    date: str
    target_date: str
    provider_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for serialisation / compatibility."""
        return asdict(self)

    @classmethod
    def from_dict(cls, mapping: dict[str, Any], provider_name: str) -> "DailyData":
        """Construct from a dictionary (e.g. raw JSON)."""
        return cls(
            open=float(mapping["open"]),
            high=float(mapping["high"]),
            low=float(mapping["low"]),
            close=float(mapping["close"]),
            volume=int(mapping["volume"]),
            date=str(mapping["date"]),
            target_date=str(mapping.get("target_date", mapping["date"])),
            provider_name=provider_name,
            metadata=mapping.get("metadata", {}),
        )


# ─── ABSTRACT PROVIDER ─────────────────────────────────────

class BaseProvider(ABC):
    """
    Abstract interface every data provider must implement.

    Usage:
        class MyProvider(BaseProvider):
            PROVIDER_NAME = "my_provider"

            def get_daily_data(self, symbol: str, target_date: str) -> DailyData:
                ...
    """

    PROVIDER_NAME: str = "base"

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config: dict[str, Any] = config or {}

    @abstractmethod
    def get_daily_data(self, symbol: str, target_date: str) -> DailyData:
        """
        Fetch a single day of OHLCV data for *symbol* on *target_date*.

        Args:
            symbol: Ticker symbol, e.g. ``"QBTS"``.
            target_date: Trading date in ``YYYY-MM-DD`` format.

        Returns:
            A validated ``DailyData`` instance.

        Raises:
            ProviderError: If the upstream API fails (timeout, HTTP error, rate-limit).
            InvalidDataError: If the raw data fails structural validation.
        """
        ...


# ─── SUPPORT ───────────────────────────────────────────────

class ProviderConfigProtocol(Protocol):
    """Structural typing for settings dicts that describe a provider."""

    @property
    def env_api_key(self) -> str: ...
    @property
    def base_url(self) -> str: ...
    @property
    def rate_limit_per_minute(self) -> int: ...
    @property
    def timeout_seconds(self) -> int: ...
