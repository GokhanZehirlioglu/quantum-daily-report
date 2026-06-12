"""
Domain exceptions for the Decision Support Engine.

Hierarchy:
    DataError (base)
    ├── InvalidDataError   → validation failure (data is corrupt / malformed)
    ├── ProviderError      → provider-level failure (timeout, rate-limit, network)
    └── Sev1DataError      → critical — all providers exhausted, pipeline killswitch
"""

from typing import Optional


class DataError(Exception):
    """Base exception for all data-layer errors."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        self.details: Optional[dict] = details or {}
        super().__init__(message)


class InvalidDataError(DataError):
    """
    Raised when raw data fails structural validation.

    Examples:
        - Volume is 0 or negative
        - High <= Low (inverted prices)
        - Close is missing / None
        - Date mismatch between requested target_date and returned data
    """

    def __init__(self, message: str, field: str, value: object, rule: str) -> None:
        self.field: str = field
        self.value: object = value
        self.rule: str = rule
        super().__init__(
            message=message,
            details={"field": field, "value": repr(value), "rule": rule},
        )


class ProviderError(DataError):
    """
    Raised when a specific data provider fails to retrieve data.

    Covers: network timeouts, HTTP errors, rate-limit exceeded,
    malformed API responses (not structurally invalid — that's InvalidDataError).
    """

    def __init__(
        self,
        message: str,
        provider_name: str,
        status_code: Optional[int] = None,
    ) -> None:
        self.provider_name: str = provider_name
        self.status_code: Optional[int] = status_code
        super().__init__(
            message=message,
            details={"provider": provider_name, "status_code": status_code},
        )


class Sev1DataError(DataError):
    """
    CRITICAL — Kill Switch.

    Raised when every provider in the fallback chain has been exhausted
    and no valid data could be obtained for a symbol. This halts the
    pipeline — silent degradation is NOT permitted.
    """

    def __init__(
        self,
        symbol: str,
        target_date: str,
        attempted_providers: list[str],
        errors: list[DataError],
    ) -> None:
        self.symbol: str = symbol
        self.target_date: str = target_date
        self.attempted_providers: list[str] = attempted_providers
        self.errors: list[DataError] = errors
        summary = "; ".join(f"{e.__class__.__name__}: {e}" for e in errors)
        super().__init__(
            message=(
                f"All providers exhausted for {symbol} on {target_date}. "
                f"Tried: {', '.join(attempted_providers)}. Errors: [{summary}]"
            ),
            details={
                "symbol": symbol,
                "target_date": target_date,
                "attempted_providers": attempted_providers,
                "error_count": len(errors),
            },
        )
