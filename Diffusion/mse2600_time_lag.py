"""MSE2600 diffusion analysis using the classical time-lag method.

The measured leak rate is integrated to obtain cumulative permeation. A line
is fitted to the final steady-state portion of that cumulative curve. Its
time-axis intercept is the time lag theta, and D = L^2 / (6 theta) for
one-dimensional Fickian diffusion through a plane sheet.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# =========================================================
# User settings
# =========================================================

INPUT_CSV = Path("mse2600_log_20260818_1.csv")
OUTPUT_IMAGE = Path("PEEK3mm_20260818_time_lag.png")

TIME_COLUMN = "pc_datetime"
ELAPSED_COLUMN = "elapsed_s"
Q_COLUMN = "leak_rate"          # MSE2600 unit: Pa m^3/s

# Trim the original recording before analysis. The first retained point is
# then treated as retained elapsed time zero.
TRIM_FRONT_MINUTES = 0.0
TRIM_BACK_MINUTES = 0.0

# Actual helium introduction time after the first retained data point.
HE_START_DELAY_MINUTES = 8.0

# Background is estimated immediately before He and subtracted before
# integration. This is important because a constant background changes the
# cumulative-curve slope and intercept.
SUBTRACT_BACKGROUND = True
BASELINE_MINUTES = 3.0

# Fit the straight steady-state part of cumulative permeation over the final
# N minutes. Increase this only if that whole interval remains linear.
STEADY_FIT_LAST_MINUTES = 10.0

THICKNESS_MM = 3.0

# Optional resampling reduces file size/noise before numerical integration.
RESAMPLE_SECONDS = 10

GRAPH_DPI = 300
SHOW_GRAPH = True


# =========================================================
# Read, clean, and trim MSE2600 data
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
        "This is not a supported MSE2600 CSV. Required columns: "
        + ", ".join(required_columns)
    ) from exc

df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], errors="coerce")
df[ELAPSED_COLUMN] = pd.to_numeric(df[ELAPSED_COLUMN], errors="coerce")
df[Q_COLUMN] = pd.to_numeric(df[Q_COLUMN], errors="coerce")
df = (
    df.dropna(subset=[ELAPSED_COLUMN, Q_COLUMN])
    .sort_values(ELAPSED_COLUMN)
    .reset_index(drop=True)
)

if df.empty:
    raise ValueError("No valid elapsed-time and leak-rate data were found.")

if TRIM_FRONT_MINUTES < 0 or TRIM_BACK_MINUTES < 0:
    raise ValueError("Trim durations cannot be negative.")

original_start_s = float(df[ELAPSED_COLUMN].iloc[0])
original_end_s = float(df[ELAPSED_COLUMN].iloc[-1])
keep_start_s = original_start_s + TRIM_FRONT_MINUTES * 60.0
keep_end_s = original_end_s - TRIM_BACK_MINUTES * 60.0

if keep_end_s <= keep_start_s:
    raise ValueError("The trim settings leave no usable time interval.")

df = df.loc[
    (df[ELAPSED_COLUMN] >= keep_start_s)
    & (df[ELAPSED_COLUMN] <= keep_end_s)
].copy()

if df.empty:
    raise ValueError("No data remain after trimming.")

retained_start_s = float(df[ELAPSED_COLUMN].iloc[0])
df["retained_elapsed_s"] = df[ELAPSED_COLUMN] - retained_start_s
retained_end_s = float(df["retained_elapsed_s"].iloc[-1])
he_start_s = HE_START_DELAY_MINUTES * 60.0

if HE_START_DELAY_MINUTES < 0 or he_start_s >= retained_end_s:
    raise ValueError("Helium introduction is outside the retained data.")


# =========================================================
# Estimate background and prepare the post-He signal
# =========================================================

baseline_start_s = he_start_s - BASELINE_MINUTES * 60.0

if SUBTRACT_BACKGROUND:
    if BASELINE_MINUTES <= 0:
        raise ValueError("BASELINE_MINUTES must be positive.")

    baseline_df = df.loc[
        (df["retained_elapsed_s"] >= baseline_start_s)
        & (df["retained_elapsed_s"] < he_start_s)
    ]

    if baseline_df.empty:
        raise ValueError("No data exist in the requested baseline interval.")

    q_background = float(baseline_df[Q_COLUMN].median())
else:
    q_background = 0.0

post_he = df.loc[df["retained_elapsed_s"] >= he_start_s].copy()
post_he["time_from_he_s"] = post_he["retained_elapsed_s"] - he_start_s

if post_he.empty:
    raise ValueError("No data exist after helium introduction.")

# Resample by elapsed time, so the method does not depend on timestamp quality.
post_he.index = pd.to_timedelta(post_he["time_from_he_s"], unit="s")
processed = (
    post_he[Q_COLUMN]
    .resample(f"{RESAMPLE_SECONDS}s")
    .median()
    .dropna()
    .to_frame(name="q_measured")
)
processed["time_s"] = processed.index.total_seconds()
processed["q_corrected"] = processed["q_measured"] - q_background

if len(processed) < 3:
    raise ValueError("Too few processed points remain for time-lag analysis.")


# =========================================================
# Integrate Q(t) to obtain cumulative permeation
# =========================================================

t = processed["time_s"].to_numpy(dtype=float)
q = processed["q_corrected"].to_numpy(dtype=float)
dt = np.diff(t)

if np.any(dt <= 0):
    raise ValueError("Processed elapsed time is not strictly increasing.")

# Trapezoidal numerical integration. Units: Pa m^3.
cumulative_increment = 0.5 * (q[1:] + q[:-1]) * dt
cumulative = np.concatenate(([0.0], np.cumsum(cumulative_increment)))
processed["cumulative_pa_m3"] = cumulative


# =========================================================
# Fit the final linear region and determine time lag
# =========================================================

if STEADY_FIT_LAST_MINUTES <= 0:
    raise ValueError("STEADY_FIT_LAST_MINUTES must be positive.")

fit_start_s = t[-1] - STEADY_FIT_LAST_MINUTES * 60.0
fit_mask = t >= fit_start_s

if np.count_nonzero(fit_mask) < 3:
    raise ValueError("Too few points exist in the steady-state fit interval.")

t_fit_data = t[fit_mask]
cumulative_fit_data = cumulative[fit_mask]
slope, intercept = np.polyfit(t_fit_data, cumulative_fit_data, 1)

if slope <= 0:
    raise ValueError(
        "The fitted steady-state cumulative slope is not positive. Check the "
        "selected fit interval and background setting."
    )

# Cumulative = slope * time + intercept; set cumulative = 0.
theta_s = -intercept / slope

if theta_s <= 0:
    raise ValueError(
        "The calculated time lag is zero or negative. The selected final "
        "interval may not represent steady-state permeation, or the baseline "
        "and helium-start settings may be incorrect."
    )

fit_prediction = slope * t_fit_data + intercept
ss_res = np.sum((cumulative_fit_data - fit_prediction) ** 2)
ss_tot = np.sum(
    (cumulative_fit_data - np.mean(cumulative_fit_data)) ** 2
)
r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


# =========================================================
# Diffusion coefficient from time lag
# =========================================================

if THICKNESS_MM <= 0:
    raise ValueError("THICKNESS_MM must be positive.")

thickness_m = THICKNESS_MM * 1e-3
diffusion_m2_s = thickness_m**2 / (6.0 * theta_s)
diffusion_cm2_s = diffusion_m2_s * 1e4


# =========================================================
# Results
# =========================================================

print()
print("=" * 72)
print("MSE2600 Classical Time-Lag Diffusion Analysis")
print("=" * 72)
print(f"CSV file                  : {INPUT_CSV.resolve()}")
print(f"Specimen thickness        : {THICKNESS_MM:.6f} mm")
print(f"He start after trim       : {HE_START_DELAY_MINUTES:g} min")
print(f"Trimmed from front        : {TRIM_FRONT_MINUTES:g} min")
print(f"Trimmed from back         : {TRIM_BACK_MINUTES:g} min")
print(f"Background subtraction    : {SUBTRACT_BACKGROUND}")
print(f"Background Q              : {q_background:.12e} Pa m^3/s")
print(f"Final linear fit interval : {STEADY_FIT_LAST_MINUTES:g} min")
print(f"Steady-state fitted Q     : {slope:.12e} Pa m^3/s")
print(f"Linear-fit R^2            : {r_squared:.8f}")
print("-" * 72)
print(f"Time lag theta            : {theta_s:.3f} s")
print(f"Time lag theta            : {theta_s / 60.0:.3f} min")
print(f"Diffusion coefficient D   : {diffusion_m2_s:.12e} m^2/s")
print(f"Diffusion coefficient D   : {diffusion_cm2_s:.12e} cm^2/s")
print("=" * 72)
print()


# =========================================================
# Plot leak rate and cumulative time-lag construction
# =========================================================

fig, (ax_q, ax_cum) = plt.subplots(2, 1, figsize=(12, 10))

ax_q.plot(
    t / 60.0,
    processed["q_measured"],
    linewidth=1.0,
    label="Measured Q",
)

if SUBTRACT_BACKGROUND:
    ax_q.axhline(
        q_background,
        linestyle=":",
        linewidth=1.2,
        label="Background Q",
    )

ax_q.axvspan(
    fit_start_s / 60.0,
    t[-1] / 60.0,
    alpha=0.15,
    label="Steady-state fit interval",
)
ax_q.set_xlabel("Time from He introduction [min]")
ax_q.set_ylabel("Leak rate Q [Pa m³/s]")
ax_q.set_title("MSE2600 Leak-rate Curve")
ax_q.set_yscale("log")
ax_q.grid(True, which="both", alpha=0.3)
ax_q.legend(fontsize=9)

ax_cum.plot(
    t / 60.0,
    cumulative,
    linewidth=1.3,
    label="Cumulative permeation",
)

# Extend the fitted line backward to cumulative = 0 to show theta.
line_start_s = max(0.0, theta_s)
line_time_s = np.linspace(line_start_s, t[-1], 300)
ax_cum.plot(
    line_time_s / 60.0,
    slope * line_time_s + intercept,
    linestyle="--",
    linewidth=1.3,
    label="Extrapolated steady-state fit",
)
ax_cum.axvline(
    theta_s / 60.0,
    linestyle=":",
    linewidth=1.3,
    label=rf"Time lag $\theta$ = {theta_s / 60.0:.3f} min",
)
ax_cum.scatter([theta_s / 60.0], [0.0], s=60, zorder=5)
ax_cum.set_xlabel("Time from He introduction [min]")
ax_cum.set_ylabel("Cumulative permeation [Pa m³]")
ax_cum.set_title("Classical Time-Lag Construction")
ax_cum.grid(True, alpha=0.3)
ax_cum.legend(fontsize=9)

fig.tight_layout()
fig.savefig(OUTPUT_IMAGE, dpi=GRAPH_DPI, bbox_inches="tight")

if SHOW_GRAPH:
    plt.show()
else:
    plt.close(fig)

print(f"Graph saved as: {OUTPUT_IMAGE.resolve()}")
