"""
Unit tests for core/exceptions.py — domain error hierarchy.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.exceptions import (
    DataError,
    InvalidDataError,
    ProviderError,
    Sev1DataError,
)


def test_data_error_base():
    e = DataError("base error", details={"key": "val"})
    assert str(e) == "base error"
    assert e.details == {"key": "val"}


def test_invalid_data_error():
    e = InvalidDataError("volume must be positive", field="volume", value=0, rule="volume_positive")
    assert e.field == "volume"
    assert e.value == 0
    assert e.rule == "volume_positive"
    assert "volume" in str(e)


def test_provider_error():
    e = ProviderError("timeout", provider_name="polygon", status_code=408)
    assert e.provider_name == "polygon"
    assert e.status_code == 408


def test_sev1_data_error():
    inner = [
        ProviderError("Polygon failed", provider_name="polygon"),
        InvalidDataError("Bad data", field="close", value=None, rule="close_not_null"),
    ]
    e = Sev1DataError(
        symbol="QBTS",
        target_date="2026-06-10",
        attempted_providers=["polygon", "alpha_vantage"],
        errors=inner,
    )
    assert e.symbol == "QBTS"
    assert len(e.errors) == 2
    assert "QBTS" in str(e)
    assert "polygon" in str(e)
    assert "alpha_vantage" in str(e)


print("=" * 50)
print("EXCEPTION TESTS")
print("=" * 50)

tests = [
    ("data_error_base", test_data_error_base),
    ("invalid_data_error", test_invalid_data_error),
    ("provider_error", test_provider_error),
    ("sev1_data_error", test_sev1_data_error),
]

passed = 0
failed = 0
for name, fn in tests:
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1

print(f"\n{passed}/{passed + failed} passed")
