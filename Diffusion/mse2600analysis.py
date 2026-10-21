import re
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# =========================
# Settings
# =========================

CSV_FILE = "mse2600_log_20260828_1.csv"

# Use the YYYYMMDD date in the CSV filename for the output image name.
# Example: mse2600_log_20260715_1.csv -> helium_leak_test_20260715.png
csv_date_match = re.search(r"\d{8}", Path(CSV_FILE).stem)

if csv_date_match is None:
    raise ValueError(
        "CSV_FILE must contain an eight-digit date such as 20260715."
    )

CSV_DATE = csv_date_match.group()
OUTPUT_IMAGE = f"helium_leak_test_{CSV_DATE}.png"

# Amount of data to remove from each end of the measurement.
# Set either value to 0 if no trimming is required on that end.
TRIM_START_MINUTES = 0
TRIM_END_HOURS = 0


# =========================
# Read CSV
# =========================

df = pd.read_csv(
    CSV_FILE,
    encoding="utf-8-sig"
)

df["elapsed_s"] = pd.to_numeric(
    df["elapsed_s"],
    errors="coerce"
)

df["leak_rate"] = pd.to_numeric(
    df["leak_rate"],
    errors="coerce"
)

df = df.dropna(
    subset=["elapsed_s", "leak_rate"]
)

# Remove zero and negative values because log scale cannot show them
df = df[df["leak_rate"] > 0].copy()

if df.empty:
    raise ValueError("No valid positive leak-rate data were found.")


# =========================
# Trim the beginning and end
# =========================

if TRIM_START_MINUTES < 0 or TRIM_END_HOURS < 0:
    raise ValueError("Trim durations cannot be negative.")

df = df.sort_values("elapsed_s").reset_index(drop=True)

measurement_start_s = df["elapsed_s"].iloc[0]
measurement_end_s = df["elapsed_s"].iloc[-1]

keep_start_s = measurement_start_s + TRIM_START_MINUTES * 60
keep_end_s = measurement_end_s - TRIM_END_HOURS * 3600

df = df.loc[
    (df["elapsed_s"] >= keep_start_s)
    & (df["elapsed_s"] <= keep_end_s)
].copy()

if df.empty:
    raise ValueError(
        "The trim settings removed all data. Reduce "
        "TRIM_START_MINUTES or TRIM_END_HOURS."
    )


# =========================
# Restart retained data from zero
# =========================

df["elapsed_h"] = (
    df["elapsed_s"] - df["elapsed_s"].iloc[0]
) / 3600


# =========================
# Plot full graph
# =========================

plt.figure(figsize=(12, 6))

plt.plot(
    df["elapsed_h"],
    df["leak_rate"],
    linewidth=1.0
)

plt.xlabel("Elapsed time [h]")
plt.ylabel("Leak rate [Pa·m³/s]")
plt.title("MSE2600 Full Leak-rate Data")

plt.yscale("log")
plt.ylim(1e-11, 1e-6)
plt.xlim(left=0)

plt.grid(
    True,
    which="both",
    alpha=0.3
)

plt.tight_layout()

# Save graph
plt.savefig(
    OUTPUT_IMAGE,
    dpi=300,
    bbox_inches="tight"
)

plt.close()

print(f"Graph saved as: {OUTPUT_IMAGE}")
print(f"Number of points plotted: {len(df):,}")
print(f"Trimmed from start: {TRIM_START_MINUTES:g} min")
print(f"Trimmed from end  : {TRIM_END_HOURS:g} h")
