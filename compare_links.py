import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from tkinter import filedialog

# ---------------------------------------------------------
# Load a single log file
# ---------------------------------------------------------
def load_log(path):
    df = pd.read_csv(path, sep=r"\s+", engine="python", dtype=str)

    # Convert numeric fields
    df["w_out"] = pd.to_numeric(df["w_out"], errors="coerce")
    df["t_diff"] = pd.to_numeric(df["t_diff"], errors="coerce")

    # Remove rows with negative time differences
    df = df[df["t_diff"] >= 0]

    return df


# ---------------------------------------------------------
# File selection dialog (starts in histories/)
# ---------------------------------------------------------
def select_file():
    root = tk.Tk()
    root.withdraw()  # hide main window

    filename = filedialog.askopenfilename(
        initialdir="histories",
        title="Selecciona un archivo de log",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
    )
    return filename


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
path = select_file()
if not path:
    print("No se seleccionó archivo.")
    exit()

print("Cargando:", path)
df = load_log(path)

# ---------------------------------------------------------
# Filter groups
# ---------------------------------------------------------

# Group 1: active + measure from rectorado-cait
df_cait = df[
    (df["link"] == "node_rectorado_upm-node_cait_upm") &
    (df["Estado"].isin(["active", "measure"]))
]

# Group 2: swapped from rectorado-etsiinf
df_etsiinf = df[
    (df["link"] == "node_rectorado_upm-node_etsiinf_upm") &
    (df["Estado"] == "swapped")
]

samples_cait = df_cait["w_out"].tolist()
samples_etsiinf = df_etsiinf["w_out"].tolist()

# ---------------------------------------------------------
# Match sample lengths
# ---------------------------------------------------------
n = min(len(samples_cait), len(samples_etsiinf))

samples_cait = samples_cait[:n]
samples_etsiinf = samples_etsiinf[:n]

x = np.arange(n)

# ---------------------------------------------------------
# Plot scatter comparison
# ---------------------------------------------------------

plt.figure(figsize=(12, 6))

# Scatter 1: rectorado-cait (active/measure)
plt.scatter(
    x,
    samples_cait,
    c=samples_cait,
    cmap="viridis",
    s=60,
    label="active/measure rectorado-cait"
)

# Scatter 2: rectorado-etsiinf (swapped)
plt.scatter(
    x,
    samples_etsiinf,
    c=samples_etsiinf,
    cmap="plasma",
    s=60,
    marker="x",
    label="swapped rectorado-etsiinf"
)

plt.axhline(y=1/3, color="red", linestyle="--", linewidth=2, alpha=0.7)

plt.xlabel("Índice de muestra", fontsize=16)
plt.ylabel("w_out", fontsize=16)
plt.title("Comparación de w_out entre enlaces", fontsize=18)

plt.grid(True)
plt.legend(fontsize=14)
plt.tight_layout()

plt.savefig("compare_single_log.png")
plt.show()
