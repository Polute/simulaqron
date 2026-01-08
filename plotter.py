import pandas as pd
import matplotlib.pyplot as plt
import re

# ---------------------------------------------------------
# 1. Load the log file (robust parsing: any number of spaces/tabs)
# ---------------------------------------------------------

rows = []
with open("log_res.txt", "r") as f:
    for line in f:
        if not line.strip():
            continue
        
        parts = re.split(r'\s+', line.strip())
        
        # Detect header
        if parts[0] == "ID":
            header = parts
            continue
        
        # Pad missing columns
        while len(parts) < len(header):
            parts.append("")
        
        rows.append(parts)

df = pd.DataFrame(rows, columns=header)

print("Detected columns:", df.columns)
print(df.head())

# ---------------------------------------------------------
# 2. Convert time strings to seconds (reduced precision: divide by 2)
# ---------------------------------------------------------

def time_to_seconds(t):
    if t is None:
        return None
    t = str(t).strip()
    if t == "" or t.lower() == "nan":
        return None
    try:
        m, s = t.split(":")
        return int(m) * 60 + float(s)
    except:
        return None


df["t_start_s"] = df["t_gen"].apply(time_to_seconds)
df["t_end_s"] = df["t_recv"].apply(time_to_seconds)
df["t_mid"] = (df["t_start_s"] + df["t_end_s"]) / 2

df["w_out"] = pd.to_numeric(df["w_out"], errors="coerce")

# --------------------------------------------------------- # 3. Shift timeline so first t_gen = 1 second # --------------------------------------------------------- 
t0 = df["t_start_s"].min() 
df["t_start_s"] = df["t_start_s"] - t0 + 1.0 
df["t_end_s"] = df["t_end_s"] - t0 + 1.0 
df["t_mid"] = df["t_mid"] - t0 + 1.0

# ---------------------------------------------------------
# 3. Detect failed swaps from explicit rows
# ---------------------------------------------------------

failed_swaps = df[df["Estado"] == "failed_swap"].copy()

# ---------------------------------------------------------
# 4. Timeline: active at t_recv, failed_swap with dashed+solid lines
# ---------------------------------------------------------

plt.figure(figsize=(18, 8))

colors = {
    "measure": "blue",
    "swapped": "green",
    "active": "orange",
    "failed_swap": "red",
    "consumed": "purple"
}

sizes = {
    "measure": 160,
    "swapped": 300,
    "active": 340,
    "failed_swap": 200,
    "consumed": 200
}

markers = {
    "measure": "o",
    "swapped": "o",
    "active": "*",
    "failed_swap": "x",
    "consumed": "D"
}

for _, row in df.iterrows():
    state = row["Estado"]

    # -------------------------------
    # FAILED_SWAP: dashed start + solid end + ID at w=0.95
    # -------------------------------
    if state == "failed_swap":
        x_start = row["t_start_s"]   # t_gen
        x_end = row["t_end_s"]       # t_recv

        # dashed line at t_gen
        plt.axvline(x_start, color="red", linestyle="--", linewidth=2, alpha=0.9)

        # solid line at t_recv
        plt.axvline(x_end, color="red", linestyle="-", linewidth=2, alpha=0.9)

        # ID label at w = 0.95
        plt.text(
            x_end + 0.1, 0.95, row["ID"],
            fontsize=11, ha="left", va="center",
            fontweight="bold", color="red",
            bbox=dict(facecolor="black", alpha=0.7, boxstyle="round,pad=0.2")
        )
        continue
    # -----------------------------------------
    # FAILED PURIFICATION (failed pur / failed p_pur)
    # -----------------------------------------
    if state in ["failed_pur", "failed_p_pur"]:
        # Convert t_pur to seconds
        t_pur_s = time_to_seconds(row["t_pur"])
        y = 0.95  # fixed w_out for failed purification

        plt.scatter(
            t_pur_s, y,
            color="red",
            s=260,
            marker="s",  # square
            edgecolors="black",
            linewidths=1.2,
            label="failed purification" if "failed purification" not in plt.gca().get_legend_handles_labels()[1] else ""
        )

        # ID label above
        plt.text(
            t_pur_s, y + 0.01, row["ID"],
            fontsize=10, ha="center", fontweight="bold",
            color="white",
            bbox=dict(facecolor="black", alpha=0.7, boxstyle="round,pad=0.2")
        )

        continue

    # -----------------------------------------
    # Draw arrows from consumed → purified
    # -----------------------------------------
    if state == "purified":
        t_pur_s = time_to_seconds(row["t_pur"])
        y_pur = row["w_out"]

        # Draw the purified point
        plt.scatter(
            t_pur_s, y_pur,
            color="limegreen",
            s=260,
            marker="s",
            edgecolors="black",
            linewidths=1.2,
            label="purified" if "purified" not in plt.gca().get_legend_handles_labels()[1] else ""
        )

        plt.text(
            t_pur_s, y_pur + 0.01, row["ID"],
            fontsize=10, ha="center", fontweight="bold",
            color="white",
            bbox=dict(facecolor="black", alpha=0.7, boxstyle="round,pad=0.2")
        )

        # Parse consumed IDs
        consumed_ids = str(row["purificado_de"]).split(",")

        for cid in consumed_ids:
            cid = cid.strip()
            if cid == "":
                continue

            # Find the consumed row
            consumed_row = df[df["ID"] == cid]
            if consumed_row.empty:
                continue

            consumed_row = consumed_row.iloc[0]

            # Coordinates of consumed event
            x_cons = consumed_row["t_mid"]
            y_cons = consumed_row["w_out"]

            # Draw arrow
            plt.annotate(
                "",
                xy=(t_pur_s, y_pur),
                xytext=(x_cons, y_cons),
                arrowprops=dict(
                    arrowstyle="->",
                    color="limegreen",
                    lw=2,
                    alpha=0.8
                )
            )

        continue




    # -------------------------------
    # NORMAL EVENTS (measure, swapped, active)
    # -------------------------------
    if state.startswith("EPR"):
        state_key = "EPR not received"
    else:
        state_key = state

    if state_key not in colors:
        continue

    # X POSITION:
    # - active → t_recv
    # - others → t_mid
    if state_key == "active":
        x = row["t_end_s"]
    else:
        x = row["t_mid"]

    y = row["w_out"]

    # -----------------------------------------
    # horizontal yellow line for ACTIVE
    # -----------------------------------------
    if state_key == "active":
        x_start = row["t_start_s"]
        x_end = row["t_end_s"]
        plt.plot(
            [x_start, x_end],
            [y, y],
            color="yellow",
            alpha=0.4,
            linewidth=4
        )

    # Draw main point
    plt.scatter(
        x, y,
        color=colors[state_key],
        s=sizes[state_key],
        marker=markers[state_key],
        edgecolors="black",
        linewidths=1.2,
        label=state_key if state_key not in plt.gca().get_legend_handles_labels()[1] else ""
    )
"""
    # ID above
    plt.text(
        x, y + 0.01, row["ID"],
        fontsize=10, ha="center", fontweight="bold",
        color="white",
        bbox=dict(facecolor="black", alpha=0.7, boxstyle="round,pad=0.2")
    )

    # w_out below
    if not pd.isna(y):
        plt.text(
            x, y - 0.01, f"{y:.5f}",
            fontsize=9, ha="center", fontweight="bold",
            color="yellow",
            bbox=dict(facecolor="black", alpha=0.7, boxstyle="round,pad=0.2")
        )
"""



plt.xlabel("Time (seconds)")
plt.ylabel("w_out")
plt.title("Quantum Event Timeline (failed_swap highlighted)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()



# ---------------------------------------------------------
# 5. Statistics bar chart
# ---------------------------------------------------------

stats = {
    "measure": sum(df["Estado"] == "measure"),
    "swapped": sum(df["Estado"] == "swapped"),
    "active": sum(df["Estado"] == "active"),
    "EPR not received": sum(df["Estado"].str.contains("EPR")),
    "failed_swap": len(failed_swaps),
    "consumed": sum(df["Estado"] == "consumed"),
    "failed pur": sum(df["Estado"] == "failed_pur"),
    "failed p_pur": sum(df["Estado"] == "failed_p_pur"),
    "purified": sum(df["Estado"] == "purified")
}

plt.figure(figsize=(10, 6))
plt.bar(stats.keys(), stats.values(), color=["blue", "green", "orange", "red", "gray"])
plt.title("Event Statistics")
plt.ylabel("Count")
plt.grid(axis="y")
plt.tight_layout()
plt.show()
