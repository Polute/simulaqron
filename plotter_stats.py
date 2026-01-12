import pandas as pd
import matplotlib.pyplot as plt
import re
import glob
import numpy as np

def load_log(path):
    df = pd.read_csv(path, sep=r"\s+", engine="python", dtype=str)
    df["w_out"] = pd.to_numeric(df["w_out"], errors="coerce")
    df["t_diff"] = pd.to_numeric(df["t_diff"], errors="coerce")

    # Remove rows with negative time differences
    df = df[df["t_diff"] >= 0]

    return df

# ---------------------------------------------------------
# MAIN: read all logs and compute mean/std of w_out for active events
# ---------------------------------------------------------

tcoh_values = []
mean_values = []
std_values = []

for file in sorted(glob.glob("logs/log_tcoh_*.txt")):
    print("Processing:", file)

    # Extract t_coh from filename
    match = re.search(r"tcoh_(\d+)", file)
    if not match:
        continue
    t_coh = int(match.group(1))

    df = load_log(file)

    # Filter only ACTIVE events (result of swapping)
    df_active = df[df["Estado"] == "active"]

    # Compute mean and std deviation of w_out
    if len(df_active) == 0:
        mean_w = 0
        std_w = 0
    else:
        mean_w = df_active["w_out"].mean()
        std_w = df_active["w_out"].std()

    tcoh_values.append(t_coh)
    mean_values.append(mean_w)
    std_values.append(std_w)

# ---------------------------------------------------------
# Sort values so the line connects 10→9→8→...→1
# ---------------------------------------------------------

tcoh_values, mean_values, std_values = zip(
    *sorted(zip(tcoh_values, mean_values, std_values), reverse=True)
)

# ---------------------------------------------------------
# Plot: mean as point, vertical std bar, line connecting means
# ---------------------------------------------------------

plt.figure(figsize=(10,6))

# Connecting line between means
plt.plot(
    tcoh_values,
    mean_values,
    color="purple",
    linewidth=2,
    alpha=0.8
)

# Draw the “I” bars and the mean points
for t_coh, mu, sigma in zip(tcoh_values, mean_values, std_values):

    # Vertical bar (std deviation)
    plt.plot(
        [t_coh, t_coh],
        [mu - sigma, mu + sigma],
        color="black",
        linewidth=2
    )

    # Mean point
    plt.scatter(
        t_coh, mu,
        color="purple",
        s=80,
        zorder=3
    )
# Horizontal reference line at w = 0.3 
plt.axhline(y=1/3, color="red", linestyle="--", linewidth=2, alpha=0.7)

plt.xlabel("Coherence time $t_{coh}$", fontsize=18)
plt.ylabel("Mean of $w_{out}$ (active events)", fontsize=18)
plt.title("Mean and standard deviation of $w_{out}$ vs. $t_{coh}$", fontsize=20)

plt.xticks(fontsize=16)
plt.yticks(fontsize=16)

plt.grid(True)
plt.gca().invert_xaxis()  # show 10 → 1
plt.savefig("plot.png")
plt.show()

