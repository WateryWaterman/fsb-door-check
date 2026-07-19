"""Clinic 样本诊断 — 验证 fail=0 是合理还是 bug。"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
WORKSPACE = BACKEND.parent.parent
sys.path.insert(0, str(BACKEND))
from app.core.pipeline import analyze_ifc

r = analyze_ifc(WORKSPACE / "samples" / "Clinic_Architectural_IFC2x3.ifc")

caps = [s["capacity"] for s in r["spaces"] if s["capacity"] is not None and s["capacity"] > 0]
caps.sort()
print(f"Clinic spaces with capacity>0: {len(caps)}")
if caps:
    print(f"capacity range: {caps[0]} ~ {caps[-1]}, median={caps[len(caps)//2]}")
    print(f"capacity>3 (Table B2 applies): {sum(1 for c in caps if c>3)}")
    print(f"capacity>30: {sum(1 for c in caps if c>30)}")
    print(f"capacity>200: {sum(1 for c in caps if c>200)}")

uc = Counter(s["use_class"] for s in r["spaces"])
print(f"\nuse_class distribution: {dict(uc)}")
ucs = Counter(s["use_class_source"] for s in r["spaces"])
print(f"use_class_source: {dict(ucs)}")

unknown_doors = [d for d in r["doors"] if d["check_result"]["status"] == "unknown"]
print(f"\nunknown doors: {len(unknown_doors)}")
reasons = Counter(d["check_result"]["reason"][:70] for d in unknown_doors)
for reason, cnt in reasons.most_common(6):
    print(f"  [{cnt}] {reason}")

pass_doors = [d for d in r["doors"] if d["check_result"]["status"] == "pass"]
th = Counter(d["check_result"]["threshold_mm"] for d in pass_doors)
print(f"\npass doors threshold distribution: {dict(th)}")

print(f"\nSample doors with capacity>3:")
cnt = 0
for d in r["doors"]:
    cr = d["check_result"]
    if cr["occupant_capacity"] and cr["occupant_capacity"] > 3:
        gid = d["global_id"][:12]
        print(f"  door={gid} cap={cr['occupant_capacity']} width={cr['measured_mm']} threshold={cr['threshold_mm']} status={cr['status']}")
        cnt += 1
        if cnt >= 10:
            break

print(f"\nSample unknown doors (first 5):")
for d in unknown_doors[:5]:
    cr = d["check_result"]
    gid = d["global_id"][:12]
    print(f"  door={gid} cap={cr['occupant_capacity']} width={cr['measured_mm']} reason={cr['reason'][:80]}")

print("\n=== Unknown-source space LongNames (top 40 distinct) ===")
unknown_lns = [s["long_name"] for s in r["spaces"] if s["use_class_source"] == "unknown"]
ln_counter = Counter(unknown_lns)
for ln, cnt in ln_counter.most_common(40):
    print(f"  [{cnt}] {ln!r}")

print("\n=== Matched space LongNames (sample) ===")
matched = [s for s in r["spaces"] if s["use_class_source"] == "longname_keyword"]
for s in matched[:15]:
    print(f"  {s['long_name']!r} -> use_class={s['use_class']} factor={s['factor']} cap={s['capacity']}")
