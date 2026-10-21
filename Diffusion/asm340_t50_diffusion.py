"""
ASM340 helium diffusion analysis using the t50% steady-state method.

How the analysis works
----------------------
1. Read the timestamp and helium leak-rate columns from the selected CSV.
2. Treat the first valid CSV timestamp as the start of data logging.
3. Define helium introduction as a user-selected delay after logging starts.
   The helium introduction moment becomes time zero on the graph:
       time < 0  -> background measurements before helium
       time = 0  -> helium is introduced
       time > 0  -> permeation measurements after helium
4. Calculate the initial leak rate from the median of the measurements taken
   immediately before helium introduction. The median reduces the effect of
   occasional measurement spikes.
5. Calculate the steady-state leak rate from the mode of the final portion of
   the experiment. The mode is useful because the ASM340 output is quantized
   and therefore often repeats identical values.
6. Calculate the baseline-corrected halfway level:
       Q50 = Q_initial + 0.5 * (Q_steady_state - Q_initial)
7. Resample and smooth the curve, then find when the smoothed leak rate first
   reaches Q50. Several consecutive points must remain above Q50 so that one
   noise spike is not mistaken for the true crossing. Linear interpolation
   estimates the crossing time more precisely between recorded points.
8. Calculate the diffusion coefficient using:
       D = specimen_thickness^2 / (7.199 * t50)
   Thickness must be in metres and t50 must be in seconds, giving D in m^2/s.
9. Print the results, plot the complete curve, and save the graph as an image.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================================================
# User settings
# =========================================================

INPUT_CSV = Path("asm340_log_20260617_130620.csv")

TIME_COLUMN = "pc_datetime"
Q_COLUMN = "leak_rate_mbar_l_s"

# Helium introduction time, measured from the first valid timestamp in the CSV.
# This calculated moment is defined as time zero for the analysis and graph.
# Examples:
#   5 minutes after logging starts: HE_START_DELAY = 5, HE_START_DELAY_UNIT = "minutes"
#   2 hours after logging starts:   HE_START_DELAY = 2, HE_START_DELAY_UNIT = "hours"
HE_START_DELAY = 5.0
HE_START_DELAY_UNIT = "minutes"

# Specimen thickness
THICKNESS_MM = 3.0

# Initial background calculation:
# use the median of data within this many minutes immediately before He.
BASELINE_MINUTES = 3.0

# Steady-state Q calculation:
# use the most frequently repeated value (mode) from the final N minutes.
STEADY_LAST_MINUTES = 10.0

# Data processing:
# resampling makes the time spacing regular; rolling-median smoothing reduces
# noise; confirmation points prevent a single spike from being selected as t50.
RESAMPLE_SECONDS = 10
SMOOTH_WINDOW_POINTS = 7
CONFIRM_POINTS = 3

# Graph
Y_MIN = 1e-11
Y_MAX = 1e-6
OUTPUT_IMAGE = Path("asm340_t50_diffusion_analysis.png")
GRAPH_DPI = 300


# =========================================================
# Read and clean data
# =========================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(
        f"CSV file was not found:\n{INPUT_CSV.resolve()}"
    )

df = pd.read_csv(
    INPUT_CSV,
    usecols=[TIME_COLUMN, Q_COLUMN],
    low_memory=False,
)

df[TIME_COLUMN] = pd.to_datetime(
    df[TIME_COLUMN],
    errors="coerce",
)

df[Q_COLUMN] = pd.to_numeric(
    df[Q_COLUMN],
    errors="coerce",
)

df = (
    df.dropna(subset=[TIME_COLUMN, Q_COLUMN])
    .sort_values(TIME_COLUMN)
    .reset_index(drop=True)
)

# A logarithmic graph cannot display zero or negative values.
df = df[df[Q_COLUMN] > 0].copy()

if df.empty:
    raise ValueError("No valid positive leak-rate data were found.")


# =========================================================
# Define He introduction time from elapsed logging time
# =========================================================

delay_unit = HE_START_DELAY_UNIT.strip().lower()

if HE_START_DELAY < 0:
    raise ValueError("HE_START_DELAY cannot be negative.")

if delay_unit in {"minute", "minutes", "min", "mins"}:
    he_start_delay = pd.Timedelta(minutes=HE_START_DELAY)
    delay_description = f"{HE_START_DELAY:g} min"
elif delay_unit in {"hour", "hours", "h", "hr", "hrs"}:
    he_start_delay = pd.Timedelta(hours=HE_START_DELAY)
    delay_description = f"{HE_START_DELAY:g} h"
else:
    raise ValueError(
        'HE_START_DELAY_UNIT must be either "minutes" or "hours".'
    )

measurement_start = df[TIME_COLUMN].min()
he_start = measurement_start + he_start_delay

if he_start > df[TIME_COLUMN].max():
    raise ValueError(
        "The calculated He start time is later than the final CSV timestamp.\n"
        "Reduce HE_START_DELAY or check the selected CSV file."
    )

# Make helium introduction time zero. Values before He are negative and values
# after He are positive.
df["time_from_he_s"] = (
    df[TIME_COLUMN] - he_start
).dt.total_seconds()

df["time_from_he_h"] = (
    df["time_from_he_s"] / 3600.0
)


# =========================================================
# Initial background Q
# =========================================================

baseline_start = (
    he_start - pd.Timedelta(minutes=BASELINE_MINUTES)
)

baseline_df = df.loc[
    (df[TIME_COLUMN] >= baseline_start)
    & (df[TIME_COLUMN] < he_start)
]

if baseline_df.empty:
    raise ValueError(
        "No data exist in the requested pre-He baseline interval.\n"
        "Increase HE_START_DELAY, reduce BASELINE_MINUTES, or provide more "
        "pre-He background data."
    )

# Median is robust against occasional spikes.
q_initial = float(
    baseline_df[Q_COLUMN].median()
)


# =========================================================
# Steady-state Q_SS
# =========================================================

measurement_end = df[TIME_COLUMN].max()

steady_start = (
    measurement_end
    - pd.Timedelta(minutes=STEADY_LAST_MINUTES)
)

steady_df = df.loc[
    df[TIME_COLUMN] >= steady_start
]

if steady_df.empty:
    raise ValueError(
        "No data were found in the steady-state interval."
    )

# The ASM340 output is quantized, so exact mode extraction is possible.
steady_modes = steady_df[Q_COLUMN].mode()

if steady_modes.empty:
    raise ValueError(
        "A steady-state mode could not be calculated."
    )

# If several modes tie, use the median of the tied mode values.
q_ss = float(
    steady_modes.median()
)

if q_ss <= q_initial:
    raise ValueError(
        "Q_SS is not greater than the initial background.\n"
        "Check HE_START_DELAY and STEADY_LAST_MINUTES."
    )


# =========================================================
# Calculate the 50% steady-state level
# =========================================================

# Use baseline-corrected 50%, not simply Q_SS / 2. This is important when the
# initial background is not zero.
q_50 = (
    q_initial
    + 0.5 * (q_ss - q_initial)
)


# =========================================================
# Resample and smooth the complete curve
# =========================================================

processed = (
    df.set_index(TIME_COLUMN)[Q_COLUMN]
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

processed["time_from_he_s"] = (
    processed.index - he_start
).total_seconds()

processed["time_from_he_h"] = (
    processed["time_from_he_s"] / 3600.0
)

# =========================================================
# Find t_50%SS
# =========================================================

post_he = processed.loc[
    processed["time_from_he_s"] >= 0
].copy()

if post_he.empty:
    raise ValueError(
        "No data exist after helium introduction."
    )

above_50 = (
    post_he["q_smooth"] >= q_50
)

# Require several consecutive points above Q50 to avoid selecting a single
# noise spike as the true 50% crossing.
confirmed = (
    above_50.astype(int)
    .rolling(CONFIRM_POINTS)
    .sum()
    .eq(CONFIRM_POINTS)
)

confirmed_positions = np.flatnonzero(
    confirmed.to_numpy()
)

if len(confirmed_positions) == 0:
    raise ValueError(
        "The smoothed signal never reached the 50% steady-state level."
    )

# The first point in the confirmed sequence
cross_index = max(
    0,
    confirmed_positions[0] - CONFIRM_POINTS + 1,
)

if cross_index == 0:
    t_50_s = float(
        post_he["time_from_he_s"].iloc[0]
    )

else:
    # Linear interpolation estimates the Q50 crossing time between the points
    # immediately below and above Q50, rather than using the nearest timestamp.
    t1 = float(
        post_he["time_from_he_s"].iloc[cross_index - 1]
    )
    t2 = float(
        post_he["time_from_he_s"].iloc[cross_index]
    )

    q1 = float(
        post_he["q_smooth"].iloc[cross_index - 1]
    )
    q2 = float(
        post_he["q_smooth"].iloc[cross_index]
    )

    if q2 == q1:
        t_50_s = t2
    else:
        t_50_s = (
            t1
            + (q_50 - q1)
            * (t2 - t1)
            / (q2 - q1)
        )

if t_50_s <= 0:
    raise ValueError(
        "Calculated t50 is zero or negative."
    )


# =========================================================
# Calculate diffusion coefficient
# =========================================================

# The diffusion equation requires thickness in metres and t50 in seconds.
thickness_m = THICKNESS_MM * 1e-3

diffusion_m2_s = (
    thickness_m**2
    / (7.199 * t_50_s)
)

diffusion_cm2_s = (
    diffusion_m2_s * 1e4
)


# =========================================================
# Terminal results
# =========================================================
print()
print("=" * 72)
print("ASM340 t50%SS and Diffusion Coefficient Analysis")
print("=" * 72)

print(f"CSV file                  : {INPUT_CSV.resolve()}")
print(f"Measurement start         : {measurement_start}")
print(f"He start delay            : {delay_description} after measurement start")
print(f"He introduction time      : {he_start}")
print(f"Baseline interval         : {BASELINE_MINUTES:g} min before He")
print(f"Steady-state interval     : final {STEADY_LAST_MINUTES:g} min")
print(f"Selected steady modes     : {len(steady_modes)}")

print("-" * 72)

print(f"Initial Q                 : {q_initial:.12e} mbar L/s")
print(f"Steady-state Q_SS         : {q_ss:.12e} mbar L/s")
print(f"50% level Q_50            : {q_50:.12e} mbar L/s")

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
# Plot the complete curve
# =========================================================

fig, ax = plt.subplots(
    figsize=(13, 7)
)

# Complete raw dataset
ax.scatter(
    df["time_from_he_h"],
    df[Q_COLUMN],
    s=2,
    alpha=0.25,
    label="Raw Q data",
)

# Smoothed complete dataset
ax.plot(
    processed["time_from_he_h"],
    processed["q_smooth"],
    linewidth=1.2,
    label="Smoothed Q",
)

# Reference levels
ax.axhline(
    q_initial,
    linestyle=":",
    linewidth=1.2,
    label=f"Initial Q = {q_initial:.3e}",
)

ax.axhline(
    q_50,
    linestyle="--",
    linewidth=1.2,
    label=f"Q50 = {q_50:.3e}",
)

ax.axhline(
    q_ss,
    linestyle="-.",
    linewidth=1.2,
    label=f"QSS = {q_ss:.3e}",
)

# He introduction and t50
ax.axvline(
    0,
    linestyle=":",
    linewidth=1.2,
    label="He introduced",
)

ax.axvline(
    t_50_s / 3600.0,
    linestyle="--",
    linewidth=1.2,
    label=f"t50 = {t_50_s / 3600.0:.3f} h",
)

# Mark the t50 point
ax.scatter(
    [t_50_s / 3600.0],
    [q_50],
    s=70,
    zorder=5,
)

ax.set_xlabel(
    "Time from He introduction [h]"
)

ax.set_ylabel(
    "Leak rate Q [mbar L/s]"
)

ax.set_title(
    "ASM340 Full Permeation Curve and t50%SS"
)

ax.set_yscale("log")
ax.set_ylim(Y_MIN, Y_MAX)

ax.grid(
    True,
    which="both",
    alpha=0.3,
)

ax.legend(
    loc="best",
    fontsize=9,
)

fig.tight_layout()

fig.savefig(
    OUTPUT_IMAGE,
    dpi=GRAPH_DPI,
    bbox_inches="tight",
)

plt.show()

print(f"Graph saved as: {OUTPUT_IMAGE.resolve()}")
