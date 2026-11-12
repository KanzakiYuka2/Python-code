"""Compare Abaqus 2D mass-diffusion RFL history with Shimadzu MSE-2600.

Usage:
    pip install numpy pandas matplotlib
    python compare_peek_abaqus_mse2600.py
    python compare_peek_abaqus_mse2600.py --he-start-min 10

Put this script, PEEK_2mm_RFL_total.rpt, and mse2600_log_20260716_1.csv
in the same folder. Review physical assumptions and CONFIG before use.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# 1. SETTINGS: EDIT HERE FIRST
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
ABAQUS_RPT = BASE_DIR / "PP_2mm_RFL.rpt"
MSE_CSV = BASE_DIR / "Diffusion" / "mse2600_log_20261112_2.csv"
OUTPUT_DIR = BASE_DIR / "comparison_results"

# Geometric scaling: 2D width x assumed unit out-of-plane depth.
MODEL_WIDTH_MM = 40.0
MODEL_OUT_OF_PLANE_MM = 1.0  # MUST verify for your Abaqus model.
EXP_AREA_MM2 = 41.0 * 41.0

# RFL units assumed kg/s, from your material's kg/mm^3 convention.
# Your uploaded RPT already contains POSITIVE downstream outflow.
# Set to -1 only if another RPT contains a NEGATIVE sum of downstream RFL11.
RFL_SIGN = +1.0

# Ideal-gas conversion: Q(Pa*m^3/s) = (mass flow kg/s) * R*T/M_He.
TEMPERATURE_K = 288.45
GAS_CONSTANT = 8.314462618     # Pa*m^3/(mol*K)
HE_MOLAR_MASS_KG_MOL = 4.002602e-3

# Match the standalone experimental t50 settings (no FINE_TEST filter).
TRIM_FRONT_MINUTES = 8.0
TRIM_BACK_MINUTES = 0.0
HE_START_DELAY_MINUTES =1.0
BASELINE_MINUTES = 1.0
STEADY_LAST_MINUTES = 5.0
RESAMPLE_SECONDS = 10
SMOOTH_WINDOW_POINTS = 7
CONFIRM_POINTS = 3
# EXP_END_MIN = 600.0   # He導入後90分まで使用
# Remove pre-He samples before smoothing, plotting, and comparison/export.
# Baseline estimation still uses the original measurement data.
TRIM_BEFORE_HE = True

SIM_REFERENCE_LAST_S = 0.0   # 0: use last Abaqus value.

# Plot range in seconds. Set to None to use experiment extent automatically.
PLOT_X_MIN_S = 0.0
PLOT_X_MAX_S = None
SAVE_DPI = 250
AXIS_LABEL_FONT_SIZE_PT = 30
Y_AXIS_LABEL_FONT_SIZE_PT = 24
TICK_FONT_SIZE_PT = 30
LEGEND_FONT_SIZE_PT = 18
EXPERIMENT_MARKER_SIZE_PT = 3.5


# ============================================================
# 2. READ FILES
# ============================================================
def read_abaqus_rpt(path):
    """Read Abaqus Report > XY: exactly two whitespace-separated numbers."""
    if not path.exists():
        raise FileNotFoundError(f"Abaqus RPT not found: {path}")
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            words = line.split()
            if len(words) != 2:
                continue
            try:
                t, rfl = float(words[0]), float(words[1])
            except ValueError:
                continue
            if np.isfinite(t) and np.isfinite(rfl):
                rows.append((t, rfl))
    if len(rows) < 3:
        raise ValueError("Abaqus RPT must contain at least three (time, RFL) rows.")
    df = pd.DataFrame(rows, columns=["time_s", "rfl_raw"])
    return (df.groupby("time_s", as_index=False).mean()
              .sort_values("time_s").reset_index(drop=True))


def analyze_experiment(path, onset_s=None):
    """Match the standalone experimental t50 processing and settings."""
    INPUT_CSV = path
    TIME_COLUMN, ELAPSED_COLUMN, Q_COLUMN = "pc_datetime", "elapsed_s", "leak_rate"
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
    he_start_s = HE_START_DELAY_MINUTES * 60.0 if onset_s is None else onset_s - retained_start_s

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
    return df, processed, q_initial, q_ss, q_50, t_50_s, retained_start_s + he_start_s

def interpolate_crossing(t, y, target=0.5):
    """First rising crossing of target, linearly interpolated."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    valid = (np.isfinite(t) & np.isfinite(y) & (t >= 0))
    t, y = t[valid], y[valid]
    ix = np.where((y[:-1] < target) & (y[1:] >= target))[0]
    if len(ix) == 0:
        return float("nan")
    i = int(ix[0])
    return float(t[i] + (target - y[i]) * (t[i+1] - t[i]) / (y[i+1] - y[i]))


def last_window_reference(df, time_col, flow_col, seconds):
    tmax = df[time_col].max()
    tail = df.loc[df[time_col] >= tmax - seconds, flow_col]
    if len(tail) < 3:
        raise ValueError("Insufficient points to estimate a reference level.")
    return float(tail.median())


def output_path(name):
    """Prefix every output with the input RPT name (without .rpt)."""
    return OUTPUT_DIR / f"{ABAQUS_RPT.stem}_{name}"


def save_fig(name):
    plt.tight_layout(pad=1.2)
    plt.savefig(output_path(name), dpi=SAVE_DPI)
    plt.close()


# ============================================================
# 3. CONVERT SIMULATION TO EXPERIMENTAL AREA
# ============================================================
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    onset = parser.add_mutually_exclusive_group()
    onset.add_argument("--he-start-s", type=float,
                       help="He introduction time in seconds from CSV recording start")
    onset.add_argument("--he-start-min", type=float,
                       help="He introduction time in minutes from CSV recording start")
    args = parser.parse_args(argv)
    time_zero_s = None
    if args.he_start_s is not None:
        time_zero_s = args.he_start_s
    elif args.he_start_min is not None:
        time_zero_s = args.he_start_min * 60.0
    if time_zero_s is not None and (not np.isfinite(time_zero_s) or time_zero_s < 0):
        raise ValueError("He introduction time must be finite and non-negative.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    sim = read_abaqus_rpt(ABAQUS_RPT)
    raw_exp, processed, q_initial, q_ss, q_50, exp_t50_s, time_zero_s = analyze_experiment(MSE_CSV, time_zero_s)

    model_area_mm2 = MODEL_WIDTH_MM * MODEL_OUT_OF_PLANE_MM
    if model_area_mm2 <= 0 or EXP_AREA_MM2 <= 0 or TEMPERATURE_K <= 0:
        raise ValueError("Area and absolute temperature must be positive.")
    area_ratio = EXP_AREA_MM2 / model_area_mm2
    convert_factor = area_ratio * GAS_CONSTANT * TEMPERATURE_K / HE_MOLAR_MASS_KG_MOL

    sim["mass_out_kg_s"] = RFL_SIGN * sim["rfl_raw"]
    if sim["mass_out_kg_s"].iloc[-1] <= 0:
        raise ValueError("Final downstream mass flow is not positive: check RFL_SIGN.")
    sim["q_Pa_m3_s"] = sim["mass_out_kg_s"] * convert_factor
    sim["time_min"] = sim["time_s"] / 60.0

    # ============================================================
    # 4. BACKGROUND AND TIME ORIGIN OF EXPERIMENT
    # ============================================================
    exp = raw_exp.copy()
    exp["time_s"] = exp["time_from_he_s"]
    exp["time_min"] = exp["time_s"] / 60.0
    exp["q_raw_Pa_m3_s"] = exp["leak_rate"]
    background = q_initial
    exp["q_corrected_Pa_m3_s"] = exp["leak_rate"] - background
    # Interpolation is for plotting/export only; t50 uses the processed grid.
    exp["q_smooth_Pa_m3_s"] = np.interp(
        exp["time_s"], processed["time_from_he_s"], processed["q_smooth"]
    ) - background
    removed_rows = int((exp["time_s"] < 0).sum()) if TRIM_BEFORE_HE else 0
    if TRIM_BEFORE_HE:
        exp = exp.loc[exp["time_s"] >= 0].copy().reset_index(drop=True)

    if SIM_REFERENCE_LAST_S > 0:
        sim_ref = last_window_reference(sim, "time_s", "q_Pa_m3_s", SIM_REFERENCE_LAST_S)
    else:
        sim_ref = float(sim["q_Pa_m3_s"].iloc[-1])
    exp_ref = q_ss - q_initial
    if min(sim_ref, exp_ref) <= 0:
        raise ValueError("Reference flow must be positive; verify settings.")

    sim["normalized"] = sim["q_Pa_m3_s"] / sim_ref
    exp["normalized"] = exp["q_smooth_Pa_m3_s"] / exp_ref

    sim_t50_s = interpolate_crossing(sim["time_s"], sim["normalized"])
    # Experimental t50 was calculated using the confirmed crossing above.

    # ============================================================
    # 5. PLOTS
    # ============================================================
    plt.rcParams.update({
        "axes.labelsize": AXIS_LABEL_FONT_SIZE_PT,
        "xtick.labelsize": TICK_FONT_SIZE_PT,
        "ytick.labelsize": TICK_FONT_SIZE_PT,
        "legend.fontsize": LEGEND_FONT_SIZE_PT,
        "legend.borderpad": 0.3,
        "legend.labelspacing": 0.3,
        "legend.handlelength": 1.6,
    })
    x_min = PLOT_X_MIN_S
    x_max = (PLOT_X_MAX_S if PLOT_X_MAX_S is not None
             else float(exp["time_s"].max()))

    # Linear leak-rate comparison
    plt.figure(figsize=(28.0 / 2.54, 18.0 / 2.54))
    plt.plot(sim["time_s"], sim["q_Pa_m3_s"], label="Abaqus (converted)", ls="-", lw=2.2)
    plt.plot(exp["time_s"], exp["q_raw_Pa_m3_s"], label="MSE-2600 (raw)",
             ls="None", marker=".", ms=EXPERIMENT_MARKER_SIZE_PT, alpha=0.35)
    plt.plot(exp["time_s"], exp["q_smooth_Pa_m3_s"],
             label="MSE-2600 (smoothed, background-corrected)",
             ls="None", marker=".", ms=EXPERIMENT_MARKER_SIZE_PT)
    plt.axhline(sim_ref, ls="--", lw=1, label="Abaqus end-value reference")
    plt.axhline(exp_ref, ls=":", lw=1, label="MSE mode minus baseline reference")
    plt.xlim(x_min, x_max)
    plt.xlabel("Time [s]")
    plt.ylabel(r"He leak rate [Pa $\cdot$ m$^3$/s]", fontsize=Y_AXIS_LABEL_FONT_SIZE_PT)
    plt.title("PP 2 mm: absolute leak-rate comparison")
    plt.grid(alpha=0.25)
    plt.legend() 
    save_fig("01_absolute_leak_rate.png")

    # Normalized curves
    plt.figure(figsize=(28.0 / 2.54, 18.0 / 2.54))
    plt.plot(sim["time_s"], sim["normalized"], label="Abaqus", ls="-", lw=2.2)
    plt.plot(exp["time_s"], exp["normalized"], label="MSE-2600",
             ls="None", marker=".", ms=EXPERIMENT_MARKER_SIZE_PT)
    plt.axhline(0.5, ls="--", lw=1, label="50% reference")
    if np.isfinite(sim_t50_s):
        plt.axvline(sim_t50_s, ls=":", lw=1, label=f"Sim t50 = {sim_t50_s:.2f} s")
    if np.isfinite(exp_t50_s):
        plt.axvline(exp_t50_s, ls="-.", lw=1, label=f"Exp t50 = {exp_t50_s:.2f} s")
    plt.xlim(x_min, x_max)
    plt.xlabel("Time [s]")
    plt.ylabel("Normalized flow / reference [-]", fontsize=Y_AXIS_LABEL_FONT_SIZE_PT)
    plt.title("PP 2 mm: normalized permeation response")
    plt.grid(alpha=0.25)
    plt.legend()
    save_fig("02_normalized_comparison.png")

    # Log plot: use positive values only.
    plt.figure(figsize=(28.0 / 2.54, 18.0 / 2.54))
    s = sim["q_Pa_m3_s"] > 0
    e = exp["q_smooth_Pa_m3_s"] > 0
    plt.semilogy(sim.loc[s, "time_s"], sim.loc[s, "q_Pa_m3_s"],
                 label="Abaqus", ls="-", lw=2.1)
    plt.semilogy(exp.loc[e, "time_s"], exp.loc[e, "q_smooth_Pa_m3_s"],
                 label="MSE-2600", ls="None", marker=".", ms=EXPERIMENT_MARKER_SIZE_PT)
    plt.xlim(x_min, x_max)
    plt.xlabel("Time [s]")
    plt.ylabel(r"He leak rate [Pa $\cdot$ m$^3$/s] (log)", fontsize=Y_AXIS_LABEL_FONT_SIZE_PT)
    plt.title("PP 2 mm: early-time comparison (log scale)")
    plt.grid(alpha=0.25, which="both")
    plt.legend()
    save_fig("03_log_leak_rate.png")

    # ============================================================
    # 6. EXPORT DATA AND SUMMARY
    # ============================================================
    sim.to_csv(output_path("abaqus_converted.csv"), index=False)
    exp.to_csv(output_path("mse2600_filtered.csv"), index=False)

    # Compare at common timestamps without extrapolation.
    t_s = sim["time_s"].to_numpy()
    t_e = exp["time_s"].to_numpy()
    common = (t_s >= max(0, t_e.min())) & (t_s <= t_e.max())
    aligned = sim.loc[common, ["time_s", "time_min", "q_Pa_m3_s", "normalized"]].copy()
    aligned.rename(columns={"q_Pa_m3_s": "sim_q", "normalized": "sim_norm"}, inplace=True)
    aligned["exp_q"] = np.interp(aligned["time_s"], t_e, exp["q_smooth_Pa_m3_s"])
    aligned["exp_norm"] = aligned["exp_q"] / exp_ref
    aligned["difference_q"] = aligned["exp_q"] - aligned["sim_q"]
    aligned.to_csv(output_path("comparison_at_sim_times.csv"), index=False)

    rmse = float(np.sqrt(np.mean(aligned["difference_q"] ** 2))) if len(aligned) else float("nan")
    norm_rmse = (float(np.sqrt(np.mean((aligned["exp_norm"] - aligned["sim_norm"]) ** 2)))
                 if len(aligned) else float("nan"))
    summary = (
        "PP 2 mm: Abaqus vs MSE-2600 (NO FITTING)\n"
        "=====================================================\n"
        f"RPT rows: {len(sim)}, MSE retained post-He rows: {len(exp)}\n"
        f"Model area: {model_area_mm2:.6g} mm^2 (assumed depth={MODEL_OUT_OF_PLANE_MM} mm)\n"
        f"Experiment area: {EXP_AREA_MM2:.6g} mm^2\n"
        f"Area factor: {area_ratio:.8g}\n"
        f"RFL -> Q factor: {convert_factor:.8e} (Pa*m^3/s)/(kg/s)\n"
        f"Background method: pre-He median, background: {background:.8e} Pa*m^3/s\n"
        f"Experimental zero time at elapsed_s={time_zero_s:.3f}\n"
        f"Trim before He: {TRIM_BEFORE_HE}, removed rows: {removed_rows}\n"
        f"Abaqus final RFL: {sim['rfl_raw'].iloc[-1]:.8e} (mass-unit/s)\n"
        f"Abaqus reference Q: {sim_ref:.8e} Pa*m^3/s\n"
        f"MSE reference Q (final {STEADY_LAST_MINUTES:g} min mode minus baseline): {exp_ref:.8e} Pa*m^3/s\n"
        f"MSE Q_initial={q_initial:.12e}, Q_SS={q_ss:.12e}, Q_50={q_50:.12e}\n"
        f"MSE post-He maximum Q (raw): {exp['q_raw_Pa_m3_s'].max():.8e} Pa*m^3/s\n"
        f"Abaqus / MSE reference ratio: {sim_ref/exp_ref:.6f}\n"
        f"Abaqus t50 (with chosen reference): {sim_t50_s:.5f} s\n"
        f"MSE t50 (with chosen reference): {exp_t50_s:.5f} s\n"
        f"t50 difference (MSE - Abaqus): {exp_t50_s-sim_t50_s:.5f} s\n"
        f"Overlap RMSE [Pa*m^3/s]: {rmse:.8e}\n"
        f"Overlap normalized RMSE: {norm_rmse:.6f}\n"
        "\nCAUTIONS:\n"
        "- RFL is assumed kg/s, requiring consistent Abaqus unit conventions.\n"
        "- Abaqus 2D out-of-plane depth is ASSUMED 1 mm until verified.\n"
        "- Final experimental mode is a REFERENCE, not proven steady state.\n"
        "- Experimental time zero is not automatically He exposure onset.\n"
        "- All positive experimental samples are used, matching the standalone t50 script.\n"
        "- RMSE is descriptive only; no parameter fitting has been performed.\n"
    )
    output_path("summary.txt").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"Saved outputs to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
