import math

T_COH = 10.0

def parse_time_to_seconds(t_str):
    """
    Convert a time string 'MM:SS.mmm' into seconds as a float.
    Not strictly required if we trust t_diff from the log,
    but useful if recomputation is needed.
    """
    if not t_str or t_str == '""':
        return None
    t_str = t_str.strip().strip('"')
    mm, rest = t_str.split(":")
    if "." in rest:
        ss, ms = rest.split(".")
        return int(mm) * 60 + int(ss) + int(ms) / 1000.0
    else:
        return int(mm) * 60 + int(rest)

def parse_float_safe(x):
    x = x.strip()
    if x in ('""', '""\n', ''):
        return None
    return float(x)

def load_log(filename):
    """
    Load the log file and parse each row into a dictionary.
    """
    rows = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Skip header
            if line.startswith("ID") and "Estado" in line:
                continue

            parts = line.split()
            if len(parts) < 3:
                continue

            row = {
                "id": parts[0],
                "estado": parts[1],
                "link": parts[2],
                "w_gen": None,
                "w_out": None,
                "t_gen": None,
                "t_recv": None,
                "t_diff": None,
                "medicion": None
            }

            if len(parts) >= 5:
                row["w_gen"] = parse_float_safe(parts[3]) if parts[3] != '""' else None
                row["w_out"] = parse_float_safe(parts[4]) if parts[4] != '""' else None

            if len(parts) >= 7:
                row["t_gen"] = parts[5] if parts[5] != '""' else None
                row["t_recv"] = parts[6] if parts[6] != '""' else None

            if len(parts) >= 8:
                row["t_diff"] = parse_float_safe(parts[7]) if parts[7] != '""' else None

            if len(parts) >= 9:
                row["medicion"] = parts[8]

            rows.append(row)

    return rows

def is_A_link(link):
    return "node_etsiinf_upm-node_cedint_upm" in link

def is_B_link(link):
    return "node_rectorado_upm-node_cedint_upm" in link

def process_blocks(rows):
    """
    Scan the log and group entries into blocks of:
    swapped A, swapped B, swapper, active.
    Each block produces one result row.
    """
    results = []
    i = 0
    n = len(rows)

    while i < n:
        row = rows[i]

        if row["estado"] == "swapped":
            swapped1 = row
            if i + 1 >= n:
                break
            swapped2 = rows[i + 1]

            if swapped2["estado"] != "swapped":
                i += 1
                continue

            if i + 2 >= n:
                break
            swapper = rows[i + 2]
            if swapper["estado"] != "swapper":
                i += 1
                continue

            if i + 3 >= n:
                break
            active = rows[i + 3]
            if active["estado"] != "active":
                i += 1
                continue

            # Identify A and B
            if is_A_link(swapped1["link"]) and is_B_link(swapped2["link"]):
                A = swapped1
                B = swapped2
            elif is_B_link(swapped1["link"]) and is_A_link(swapped2["link"]):
                A = swapped2
                B = swapped1
            else:
                i += 1
                continue

            delta_A = A["t_diff"]
            delta_B = B["t_diff"]

            w_A = A["w_out"]
            w_B = B["w_out"]

            w_direct = None
            if w_A is not None and w_B is not None:
                w_direct = w_A * w_B

            # Correct theoretical decay (matches README)
            w_theoretical = None
            if delta_B is not None:
                w_theoretical = math.exp(-2.0 * delta_B / T_COH)

            w_real = active["w_out"]

            error = None
            if w_theoretical is not None and w_real is not None:
                error = w_theoretical - w_real

            results.append({
                "A_id": A["id"],
                "B_id": B["id"],
                "delta_A": delta_A,
                "delta_B": delta_B,
                "w_A": w_A,
                "w_B": w_B,
                "w_direct": w_direct,
                "w_theoretical": w_theoretical,
                "w_real": w_real,
                "error": error
            })

            i += 4
        else:
            i += 1

    return results

def print_table(results):
    header = (
        f"{'A_ID':<12} {'B_ID':<12} "
        f"{'ΔA':>8} {'ΔB':>8} "
        f"{'w_A':>10} {'w_B':>10} "
        f"{'w_direct':>12} {'w_theor':>12} "
        f"{'w_real':>10} {'error':>10}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        delta_A = f"{r['delta_A']:.3f}" if r["delta_A"] is not None else "---"
        delta_B = f"{r['delta_B']:.3f}" if r["delta_B"] is not None else "---"
        w_A = f"{r['w_A']:.5f}" if r["w_A"] is not None else "---"
        w_B = f"{r['w_B']:.5f}" if r["w_B"] is not None else "---"
        w_direct = f"{r['w_direct']:.5f}" if r["w_direct"] is not None else "---"
        w_theor = f"{r['w_theoretical']:.5f}" if r["w_theoretical"] is not None else "---"
        w_real = f"{r['w_real']:.5f}" if r["w_real"] is not None else "---"
        error = f"{r['error']:.5f}" if r["error"] is not None else "---"

        print(
            f"{r['A_id']:<12} {r['B_id']:<12} "
            f"{delta_A:>8} {delta_B:>8} "
            f"{w_A:>10} {w_B:>10} "
            f"{w_direct:>12} {w_theor:>12} "
            f"{w_real:>10} {error:>10}"
        )

def main():
    filename = "werner_logs.txt"
    rows = load_log(filename)
    results = process_blocks(rows)
    print_table(results)

if __name__ == "__main__":
    main()
