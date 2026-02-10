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
    swapped A, swapped B and measure.
    Each block produces one result row.
    """
    results = []
    i = 0
    n = len(rows)

    while i < n:
        row = rows[i]

        # Look for first swapped
        if row["estado"] == "swapped":
            swapped1 = row

            # Find next swapped
            j = i + 1
            while j < n and rows[j]["estado"] != "swapped":
                j += 1
            if j >= n:
                break
            swapped2 = rows[j]

            # Find next measure
            k = j + 1
            while k < n and rows[k]["estado"] != "measure":
                k += 1
            if k >= n:
                break
            measure = rows[k]

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

            # Extract values
            t_gen_A = parse_time_to_seconds(A["t_gen"])
            t_gen_B = parse_time_to_seconds(B["t_gen"])

            # SWAP time = time of the measure event
            t_swap = parse_time_to_seconds(measure["t_recv"])

            delta_A = t_swap - t_gen_A if t_gen_A is not None else None
            delta_B = t_swap - t_gen_B if t_gen_B is not None else None

            w_A = A["w_out"]
            w_B = B["w_out"]

            w_direct = w_A * w_B if w_A and w_B else None

            # theoretical decay using both deltas
            w_theoretical = None
            if delta_A is not None and delta_B is not None:
                w_theoretical = math.exp(-delta_A / T_COH) * math.exp(-delta_B / T_COH)

            w_real = measure["w_out"]
            error = (w_theoretical - w_real) if (w_theoretical and w_real) else None


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

            # Move index past the measure
            i = k + 1
        else:
            i += 1

    return results

def print_table(results, outfile="results.txt"):
    lines = []

    header = (
        f"{'A_ID':<12} {'B_ID':<12} "
        f"{'ΔA':>8} {'ΔB':>8} "
        f"{'w_A':>10} {'w_B':>10} "
        f"{'w_direct':>12} {'w_theor':>12} "
        f"{'w_real':>10} {'error':>10}"
    )
    separator = "-" * len(header)

    # Add header to lines
    lines.append(header)
    lines.append(separator)

    # Build each row
    for r in results:
        delta_A = f"{r['delta_A']:.3f}" if r["delta_A"] is not None else "---"
        delta_B = f"{r['delta_B']:.3f}" if r["delta_B"] is not None else "---"
        w_A = f"{r['w_A']:.5f}" if r["w_A"] is not None else "---"
        w_B = f"{r['w_B']:.5f}" if r["w_B"] is not None else "---"
        w_direct = f"{r['w_direct']:.5f}" if r["w_direct"] is not None else "---"
        w_theor = f"{r['w_theoretical']:.5f}" if r["w_theoretical"] is not None else "---"
        w_real = f"{r['w_real']:.5f}" if r["w_real"] is not None else "---"
        error = f"{r['error']:.5f}" if r["error"] is not None else "---"

        line = (
            f"{r['A_id']:<12} {r['B_id']:<12} "
            f"{delta_A:>8} {delta_B:>8} "
            f"{w_A:>10} {w_B:>10} "
            f"{w_direct:>12} {w_theor:>12} "
            f"{w_real:>10} {error:>10}"
        )
        lines.append(line)

    # Print to console
    for line in lines:
        print(line)

    # Write to file
    with open(outfile, "w") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"\nResults written to {outfile}")

def main():
    filename = "werner_logs.txt"
    rows = load_log(filename)
    results = process_blocks(rows)
    print_table(results, "results.txt")

if __name__ == "__main__":
    main()