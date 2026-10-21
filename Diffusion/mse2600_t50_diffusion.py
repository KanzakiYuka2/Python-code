"""MSE2600 helium permeation analysis using the t50 steady-state method.

The script reads an MSE2600 series CSV, optionally trims unwanted data from
both ends, calculates the initial and steady-state leak rates, finds t50, and
calculates the diffusion coefficient.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# =========================================================
# User settings
# =========================================================

# Resolve input filenames relative to this script's Diffusion folder, even
# when the script is launched from another working directory.
DATA_DIR = Path(__file__).resolve().parent
INPUT_CSV = DATA_DIR / "mse2600_log_20261020_2.csv"

# Choose the saved graph filename for this analysis.
OUTPUT_IMAGE = Path("PEEK2mm_20261020_1.png")

TIME_COLUMN = "pc_datetime"
ELAPSED_COLUMN = "elapsed_s"
Q_COLUMN = "leak_rate"

# Remove unwanted data before performing any analysis. After trimming, the
# first retained point becomes elapsed time zero.
TRIM_FRONT_MINUTES = 0.0
TRIM_BACK_MINUTES = 0.0

# Helium introduction time measured from the first retained point.
HE_START_DELAY_MINUTES = 6.0

# Median background interval immediately before helium introduction.
BASELINE_MINUTES = 1.0

# Mode calculation interval at the end of the retained measurement.
STEADY_LAST_MINUTES = 10.0

# Specimen thickness used by D = L^2 / (7.199 * t50).
THICKNESS_MM = 2.0

# Signal processing and crossing confirmation.
RESAMPLE_SECONDS = 10
SMOOTH_WINDOW_POINTS = 7
CONFIRM_POINTS = 3

# Graph settings.
Y_MIN = 1e-11
Y_MAX = 1e-6
GRAPH_DPI = 300
SHOW_GRAPH = True


# =========================================================
# Read and validate an MSE2600 CSV
# =========================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(f"CSV file was not found:\n{INPUT_CSV.resolve()}")

required_columns = [TIME_COLUMN, ELAPSED_COLUMN, Q_COLUMN]

try:
    df = pd.read_csv(
        INPUT_CSV,
        usecols=required_columns,
        encoding="utf-8-sig",
        low_memory=False,
    )
except ValueError as exc:
    raise ValueError(
        "This does not appear to be a supported MSE2600 CSV.\n"
        f"Required columns: {', '.join(required_columns)}"
    ) from exc

df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], errors="coerce")
df[ELAPSED_COLUMN] = pd.to_numeric(df[ELAPSED_COLUMN], errors="coerce")
df[Q_COLUMN] = pd.to_numeric(df[Q_COLUMN], errors="coerce")

df = (
    df.dropna(subset=[ELAPSED_COLUMN, Q_COLUMN])
    .sort_values(ELAPSED_COLUMN)
    .reset_index(drop=True)
)

# Zero and negative leak rates cannot be displayed on a logarithmic graph.
df = df.loc[df[Q_COLUMN] > 0].copy()

if df.empty:
    raise ValueError("No valid positive leak-rate data were found.")


# =========================================================
# Trim first, then restart retained elapsed time from zero
# =========================================================

if TRIM_FRONT_MINUTES < 0 or TRIM_BACK_MINUTES < 0:
    raise ValueError("Front and back trim durations cannot be negative.")

original_start_s = float(df[ELAPSED_COLUMN].iloc[0])
original_end_s = float(df[ELAPSED_COLUMN].iloc[-1])
keep_start_s = original_start_s + TRIM_FRONT_MINUTES * 60.0
keep_end_s = original_end_s - TRIM_BACK_MINUTES * 60.0

if keep_end_s <= keep_start_s:
    raise ValueError(
        "The trim settings leave no usable time interval. Reduce "
        "TRIM_FRONT_MINUTES or TRIM_BACK_MINUTES."
    )

df = df.loc[
    (df[ELAPSED_COLUMN] >= keep_start_s)
    & (df[ELAPSED_COLUMN] <= keep_end_s)
].copy()

if df.empty:
    raise ValueError("No data remain after trimming.")

retained_start_s = float(df[ELAPSED_COLUMN].iloc[0])
df["retained_elapsed_s"] = df[ELAPSED_COLUMN] - retained_start_s

retained_duration_s = float(df["retained_elapsed_s"].iloc[-1])
he_start_s = HE_START_DELAY_MINUTES * 60.0

if HE_START_DELAY_MINUTES < 0:
    raise ValueError("HE_START_DELAY_MINUTES cannot be negative.")

if he_start_s >= retained_duration_s:
    raise ValueError(
        "Helium introduction is outside the retained data. Reduce trimming "
        "or HE_START_DELAY_MINUTES."
    )

df["time_from_he_s"] = df["retained_elapsed_s"] - he_start_s
df["time_from_he_h"] = df["time_from_he_s"] / 3600.0


# =========================================================
# Initial background and steady-state Q
# =========================================================

if BASELINE_MINUTES <= 0:
    raise ValueError("BASELINE_MINUTES must be greater than zero.")

baseline_start_s = he_start_s - BASELINE_MINUTES * 60.0
baseline_df = df.loc[
    (df["retained_elapsed_s"] >= baseline_start_s)
    & (df["retained_elapsed_s"] < he_start_s)
]

if baseline_df.empty:
    raise ValueError(
        "No data exist in the requested pre-He baseline interval. Increase "
        "HE_START_DELAY_MINUTES or reduce BASELINE_MINUTES."
    )

q_initial = float(baseline_df[Q_COLUMN].median())

if STEADY_LAST_MINUTES <= 0:
    raise ValueError("STEADY_LAST_MINUTES must be greater than zero.")

steady_start_s = retained_duration_s - STEADY_LAST_MINUTES * 60.0
steady_df = df.loc[df["retained_elapsed_s"] >= steady_start_s]

if steady_df.empty:
    raise ValueError("No data were found in the steady-state interval.")

steady_modes = steady_df[Q_COLUMN].mode()

if steady_modes.empty:
    raise ValueError("A steady-state mode could not be calculated.")

# If exact values tie for most frequent, use the median of the tied modes.
q_ss = float(steady_modes.median())

if q_ss <= q_initial:
    raise ValueError(
        "Q_SS is not greater than the initial background. Check the helium "
        "start, trimming, and steady-state interval settings."
    )

q_50 = q_initial + 0.5 * (q_ss - q_initial)


# =========================================================
# Resample, smooth, and find t50
# =========================================================

if RESAMPLE_SECONDS <= 0 or SMOOTH_WINDOW_POINTS <= 0 or CONFIRM_POINTS <= 0:
    raise ValueError("Processing settings must be positive.")

# A TimedeltaIndex makes resampling independent of timestamp availability.
processing_df = df.set_index(
    pd.to_timedelta(df["retained_elapsed_s"], unit="s")
)

processed = (
    processing_df[Q_COLUMN]
    .resample(f"{RESAMPLE_SECONDS}s")
    .median()
    .dropna()
    .to_frame(name="q_resampled")
)

processed["q_smooth"] = (
    processed["q_resampled"]
    .rolling(
        window=SMOOTH_WINDOW_POINTS,
        center=True,
        min_periods=1,
    )
    .median()
)

processed["retained_elapsed_s"] = processed.index.total_seconds()
processed["time_from_he_s"] = processed["retained_elapsed_s"] - he_start_s
processed["time_from_he_h"] = processed["time_from_he_s"] / 3600.0

post_he = processed.loc[processed["time_from_he_s"] >= 0].copy()

if post_he.empty:
    raise ValueError("No processed data exist after helium introduction.")

above_50 = post_he["q_smooth"] >= q_50
confirmed = (
    above_50.astype(int)
    .rolling(CONFIRM_POINTS)
    .sum()
    .eq(CONFIRM_POINTS)
)
confirmed_positions = np.flatnonzero(confirmed.to_numpy())

if len(confirmed_positions) == 0:
    raise ValueError("The smoothed signal never reached Q50.")

cross_index = max(0, confirmed_positions[0] - CONFIRM_POINTS + 1)

if cross_index == 0:
    t_50_s = float(post_he["time_from_he_s"].iloc[0])
else:
    t1 = float(post_he["time_from_he_s"].iloc[cross_index - 1])
    t2 = float(post_he["time_from_he_s"].iloc[cross_index])
    q1 = float(post_he["q_smooth"].iloc[cross_index - 1])
    q2 = float(post_he["q_smooth"].iloc[cross_index])
    t_50_s = t2 if q2 == q1 else t1 + (q_50 - q1) * (t2 - t1) / (q2 - q1)

if t_50_s <= 0:
    raise ValueError("Calculated t50 is zero or negative.")


# =========================================================
# Diffusion coefficient and results
# =========================================================

thickness_m = THICKNESS_MM * 1e-3
diffusion_m2_s = thickness_m**2 / (7.199 * t_50_s)
diffusion_cm2_s = diffusion_m2_s * 1e4

print()
print("=" * 72)
print("MSE2600 t50%SS and Diffusion Coefficient Analysis")
print("=" * 72)
print(f"CSV file                  : {INPUT_CSV.resolve()}")
print(f"Points after trimming     : {len(df):,}")
print(f"Trimmed from front        : {TRIM_FRONT_MINUTES:g} min")
print(f"Trimmed from back         : {TRIM_BACK_MINUTES:g} min")
print(f"Retained duration         : {retained_duration_s / 3600.0:.6f} h")
print(f"He start after trim       : {HE_START_DELAY_MINUTES:g} min")
print(f"Baseline interval         : {BASELINE_MINUTES:g} min before He")
print(f"Steady-state interval     : final {STEADY_LAST_MINUTES:g} min")
print(f"Selected steady modes     : {len(steady_modes)}")
print("-" * 72)
print(f"Initial Q                 : {q_initial:.12e} Pa m^3/s")
print(f"Steady-state Q_SS         : {q_ss:.12e} Pa m^3/s")
print(f"50% level Q_50            : {q_50:.12e} Pa m^3/s")
print("-" * 72)
print(f"t_50%SS                   : {t_50_s:.3f} s")
print(f"t_50%SS                   : {t_50_s / 60.0:.3f} min")
print(f"t_50%SS                   : {t_50_s / 3600.0:.6f} h")
print(f"Specimen thickness        : {THICKNESS_MM:.6f} mm")
print("-" * 72)
print(f"Diffusion coefficient D   : {diffusion_m2_s:.12e} m^2/s")
print(f"Diffusion coefficient D   : {diffusion_cm2_s:.12e} cm^2/s")
print("=" * 72)
print()


# =========================================================
# Plot retained data and analysis levels
# =========================================================

fig, ax = plt.subplots(figsize=(13, 7))
ax.scatter(
    df["time_from_he_s"],
    df[Q_COLUMN],
    s=3,
    alpha=0.25,
    label="Raw MSE2600 Q data",
)
ax.plot(
    processed["time_from_he_s"],
    processed["q_smooth"],
    linewidth=1.2,
    label="Smoothed Q",
)
ax.axhline(q_initial, linestyle=":", linewidth=1.2, label=f"Initial Q = {q_initial:.3e}")
ax.axhline(q_50, linestyle="--", linewidth=1.2, label=f"Q50 = {q_50:.3e}")
ax.axhline(q_ss, linestyle="-.", linewidth=1.2, label=f"QSS = {q_ss:.3e}")
ax.axvline(0, linestyle=":", linewidth=1.2, label="He introduced")
ax.axvline(
    t_50_s,
    linestyle="--",
    linewidth=1.2,
    label=f"t50 = {t_50_s:.3f} s",
)
ax.scatter([t_50_s], [q_50], s=70, zorder=5)

ax.set_xlabel("Time from He introduction [s]")
ax.set_ylabel("Leak rate Q [Pa m³/s]")
ax.set_title("MSE2600 Full Permeation Curve and t50%SS")
ax.set_yscale("log")
ax.set_ylim(Y_MIN, Y_MAX)
ax.grid(True, which="both", alpha=0.3)
ax.legend(loc="best", fontsize=9)
fig.tight_layout()
fig.savefig(OUTPUT_IMAGE, dpi=GRAPH_DPI, bbox_inches="tight")

if SHOW_GRAPH:
    plt.show()
else:
    plt.close(fig)

print(f"Graph saved as: {OUTPUT_IMAGE.resolve()}")
