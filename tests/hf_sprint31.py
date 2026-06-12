"""Quick verification for Sprint 3.1 hotfixes."""
import sys; sys.path.insert(0, ".")
import pandas as pd
from core.gap_risk import calculate_g_worst
from core.position_sizing import calculate_position_size

errors = []

# ── 1. gap_risk tuple return ──
df = pd.DataFrame({"open": [101, 90, 105], "close": [100, 95, 104]})
g, meta = calculate_g_worst(df)
if abs(g - 0.10) >= 0.001:
    errors.append(f"gap_risk value: {g}")
if not meta["short_data_warning"]:
    errors.append("gap_risk: short_data_warning should be True")
if "kisa veri" not in meta["warning_text"].lower():
    errors.append("gap_risk: warning_text missing")
print(f"[{'FAIL' if errors else 'PASS'}] gap_risk: tuple return + warning")

# ── 2. dynamic cap: g_worst=0.20 -> cap 5% ──
r = calculate_position_size(r_max=100.0, g_worst=0.20)
if r["cap_pct"] != 0.05:
    errors.append(f"pos: cap_pct={r['cap_pct']} expected 0.05")
if r["capped"] is not False:
    errors.append("pos: should not be capped")
if r["cap_reason"] != "mathematical":
    errors.append(f"pos: reason={r['cap_reason']}")
print(f"[{'FAIL' if errors else 'PASS'}] pos_sizing: g=0.20 -> cap=5%")

# ── 3. dynamic cap: g_worst=0.12 -> cap 10%, triggers risk_limit ──
r2 = calculate_position_size(r_max=3000.0, g_worst=0.12)
if r2["cap_pct"] != 0.10:
    errors.append(f"pos2: cap_pct={r2['cap_pct']} expected 0.10")
if not r2["capped"]:
    errors.append("pos2: should be capped")
if r2["cap_reason"] != "risk_limit":
    errors.append(f"pos2: reason={r2['cap_reason']}")
print(f"[{'FAIL' if errors else 'PASS'}] pos_sizing: g=0.12 -> cap=10%, risk_limit")

# ── 4. dynamic cap: g_worst=0.08 -> cap 15% ──
r3 = calculate_position_size(r_max=100.0, g_worst=0.08)
if r3["cap_pct"] != 0.15:
    errors.append(f"pos3: cap_pct={r3['cap_pct']} expected 0.15")
print(f"[{'FAIL' if errors else 'PASS'}] pos_sizing: g=0.08 -> cap=15%")

if errors:
    print(f"\nFAILURES: {errors}")
    sys.exit(1)
else:
    print("\nALL SPRINT 3.1 TESTS PASSED")
