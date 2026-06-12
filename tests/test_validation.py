"""
Unit tests for core/validation.py — strict data validation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.exceptions import InvalidDataError
from core.validation import validate_daily_data, batch_validate


def test_valid_data_passes():
    """A structurally perfect data point must pass all rules."""
    data = {
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.5,
        "volume": 1_000_000,
        "date": "2026-06-10",
        "target_date": "2026-06-10",
    }
    assert validate_daily_data(data) is True


def test_zero_volume_fails():
    data = {
        "open": 100.0, "high": 105.0, "low": 99.0,
        "close": 103.5, "volume": 0,
        "date": "2026-06-10", "target_date": "2026-06-10",
    }
    try:
        validate_daily_data(data)
        assert False, "Expected InvalidDataError"
    except InvalidDataError as e:
        assert e.field == "volume"


def test_high_equals_low_fails():
    data = {
        "open": 100.0, "high": 100.0, "low": 100.0,
        "close": 100.0, "volume": 1_000_000,
        "date": "2026-06-10", "target_date": "2026-06-10",
    }
    try:
        validate_daily_data(data)
        assert False, "Expected InvalidDataError"
    except InvalidDataError as e:
        assert e.field == "high"


def test_close_none_fails():
    data = {
        "open": 100.0, "high": 105.0, "low": 99.0,
        "close": None, "volume": 1_000_000,
        "date": "2026-06-10", "target_date": "2026-06-10",
    }
    try:
        validate_daily_data(data)
        assert False, "Expected InvalidDataError"
    except InvalidDataError as e:
        assert e.field == "close"


def test_close_nan_fails():
    import math
    data = {
        "open": 100.0, "high": 105.0, "low": 99.0,
        "close": math.nan, "volume": 1_000_000,
        "date": "2026-06-10", "target_date": "2026-06-10",
    }
    try:
        validate_daily_data(data)
        assert False, "Expected InvalidDataError"
    except InvalidDataError as e:
        assert e.field == "close"


def test_date_mismatch_fails():
    data = {
        "open": 100.0, "high": 105.0, "low": 99.0,
        "close": 103.5, "volume": 1_000_000,
        "date": "2026-06-09", "target_date": "2026-06-10",
    }
    try:
        validate_daily_data(data)
        assert False, "Expected InvalidDataError"
    except InvalidDataError as e:
        assert e.field == "date"


def test_batch_validate_with_valid_items():
    items = [
        {"open": 100.0, "high": 105.0, "low": 99.0, "close": 103.5,
         "volume": 1_000_000, "date": "2026-06-10", "target_date": "2026-06-10"},
        {"open": 101.0, "high": 106.0, "low": 98.0, "close": 104.0,
         "volume": 1_200_000, "date": "2026-06-10", "target_date": "2026-06-10"},
    ]
    result = batch_validate(items)
    assert len(result) == 2


print("=" * 50)
print("VALIDATION TESTS")
print("=" * 50)

tests = [
    ("valid_data_passes", test_valid_data_passes),
    ("zero_volume_fails", test_zero_volume_fails),
    ("high_equals_low_fails", test_high_equals_low_fails),
    ("close_none_fails", test_close_none_fails),
    ("close_nan_fails", test_close_nan_fails),
    ("date_mismatch_fails", test_date_mismatch_fails),
    ("batch_validate_valid", test_batch_validate_with_valid_items),
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
