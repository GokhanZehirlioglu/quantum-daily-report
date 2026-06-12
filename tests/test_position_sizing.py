"""Tests for core/position_sizing.py — calculate_position_size."""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.position_sizing import calculate_position_size


def verify_all():
    errors = []

    # ── Test 1: Basic formula ──
    # r_max=100, g_worst=0.20  →  S_pos = 100/0.20 = 500
    # Cap = 0.15 * 10000 = 1500 → 500 < 1500 → uncapped
    r = calculate_position_size(r_max=100.0, g_worst=0.20)
    if r["raw_s_pos"] != 500.0:
        errors.append(f"Test 1: raw_s_pos={r['raw_s_pos']}, expected 500")
    if r["position_size"] != 500.0:
        errors.append(f"Test 1: position_size={r['position_size']}, expected 500")
    if r["capped"] is not False:
        errors.append("Test 1: should not be capped")
    if r["position_size_pct"] != 5.0:
        errors.append(f"Test 1: pct={r['position_size_pct']}, expected 5.0")
    if r["g_used"] != 0.20:
        errors.append(f"Test 1: g_used={r['g_used']}, expected 0.20")

    # ── Test 2: g_floor kicks in when g_worst is small ──
    # r_max=100, g_worst=0.02, g_floor=0.10  →  g_used=0.10 → S_pos=1000
    r2 = calculate_position_size(r_max=100.0, g_worst=0.02, g_floor=0.10)
    if r2["g_used"] != 0.10:
        errors.append(f"Test 2: g_used={r2['g_used']}, expected 0.10")
    if r2["raw_s_pos"] != 1000.0:
        errors.append(f"Test 2: raw_s_pos={r2['raw_s_pos']}, expected 1000")

    # ── Test 3: Cap applied ──
    # r_max=5000, g_worst=0.05, g_floor=0.10  →  S_pos=50000
    # Cap = 0.15 * 10000 = 1500  →  capped at 1500
    r3 = calculate_position_size(r_max=5000.0, g_worst=0.05, g_floor=0.10)
    if r3["position_size"] != 1500.0:
        errors.append(f"Test 3: position_size={r3['position_size']}, expected 1500")
    if r3["capped"] is not True:
        errors.append("Test 3: should be capped")

    # ── Test 4: Custom cap fraction ──
    r4 = calculate_position_size(r_max=100.0, g_worst=0.20, max_position_cap=0.30, portfolio_value=5000)
    # raw=500, cap=0.30*5000=1500 → uncapped
    if r4["position_size"] != 500.0:
        errors.append(f"Test 4: position_size={r4['position_size']}, expected 500")

    # ── Test 5: Error on r_max <= 0 ──
    try:
        calculate_position_size(r_max=0, g_worst=0.10)
        errors.append("Test 5: should have raised ValueError for r_max=0")
    except ValueError:
        pass

    # ── Test 6: Error on negative g_worst ──
    try:
        calculate_position_size(r_max=100, g_worst=-0.05)
        errors.append("Test 6: should have raised ValueError for negative g_worst")
    except ValueError:
        pass

    # ── Test 7: Zero g_worst with floor ──
    r7 = calculate_position_size(r_max=100.0, g_worst=0.0, g_floor=0.10)
    if r7["g_used"] != 0.10:
        errors.append(f"Test 7: g_used={r7['g_used']}, expected 0.10")
    if r7["raw_s_pos"] != 1000.0:
        errors.append(f"Test 7: raw_s_pos={r7['raw_s_pos']}, expected 1000")

    return errors


errors = verify_all()
print(f"Errors: {len(errors)}")
for e in errors:
    print(f"  FAIL: {e}")
if not errors:
    print("ALL position_sizing tests PASSED")
