import re

# ---------------------------------------
# Parse timestamp MM:SS.xxxxxx → seconds
# ---------------------------------------
def ts_to_seconds(ts):
    mm, rest = ts.split(":")
    ss, us = rest.split(".")
    return int(mm)*60 + int(ss) + int(us)/1_000_000

# ---------------------------------------
# Load trace file
# ---------------------------------------
lines = []
with open("trace_epr_63tm8r3t4.txt") as f:
    for line in f:
        m = re.match(r"(\d\d:\d\d\.\d{6}) \[CALL\] (.*)", line)
        if m:
            ts = m.group(1)
            info = m.group(2)
            lines.append((ts_to_seconds(ts), ts, info))

# ---------------------------------------
# Compute deltas
# ---------------------------------------
deltas = []
for i in range(len(lines)-1):
    t1, ts1, info1 = lines[i]
    t2, ts2, info2 = lines[i+1]
    delta = t2 - t1
    deltas.append((delta, i, ts1, info1, ts2, info2))

# ---------------------------------------
# Top 30 slowest
# ---------------------------------------
deltas_sorted = sorted(deltas, reverse=True, key=lambda x: x[0])

print("\n=== TOP 30 INTERVALOS MÁS GRANDES ===\n")
for d, idx, ts1, info1, ts2, info2 in deltas_sorted[:30]:
    print(f"{d:.6f}s  entre:")
    print(f"   {ts1}  {info1}")
    print(f"   {ts2}  {info2}")
    print()

# ---------------------------------------
# Función CALL n
# ---------------------------------------
def show_call(n):
    if n < 0 or n >= len(deltas):
        print("CALL fuera de rango")
        return
    d, idx, ts1, info1, ts2, info2 = deltas[n]
    print(f"\n=== CALL {n} ===")
    print(f"Delta: {d:.6f}s")
    print(f"   {ts1}  {info1}")
    print(f"   {ts2}  {info2}")

# Ejemplo:
# show_call(10)
