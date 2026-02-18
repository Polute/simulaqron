import re
import numpy as np

pattern = re.compile(r"^\s*([A-Za-z0-9_→\-\s]+?)\s*:\s*([0-9.]+)\s*s")


def parse_file(filename):
    stats = {}

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.match(line)
            if match:
                key = match.group(1)
                value = float(match.group(2))

                if key not in stats:
                    stats[key] = []
                stats[key].append(value)

    return stats


def compute_stats(stats):
    results = {}

    for key, values in stats.items():
        arr = np.array(values)
        results[key] = {
            "min": float(arr.min()),
            "max": float(arr.max()),
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
        }

    return results


def write_results(results, output_file="resultados.txt"):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=== RESULTADOS ===\n\n")
        for key, r in results.items():
            f.write(f"{key}:\n")
            f.write(f"  min  = {r['min']:.6f} s\n")
            f.write(f"  max  = {r['max']:.6f} s\n")
            f.write(f"  mean = {r['mean']:.6f} s\n")
            f.write(f"  std  = {r['std']:.6f} s\n\n")


def main():
    input_file = "latencies/latencies_epr_pipelinex2_9.txt"       # Cambia si tu archivo se llama distinto
    output_file = "resultadosx2_9.txt" # Cambia si quieres otro nombre

    stats = parse_file(input_file)
    results = compute_stats(stats)
    write_results(results, output_file)


if __name__ == "__main__":
    main()
