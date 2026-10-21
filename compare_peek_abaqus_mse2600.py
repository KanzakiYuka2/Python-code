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
ABAQUS_RPT = BASE_DIR / "PEEK_2mm_RE.rpt"
MSE_CSV = BASE_DIR / "Diffusion" / "mse2600_log_20261020_2.csv"
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
TEMPERATURE_K = 295.65
GAS_CONSTANT = 8.314462618     # Pa*m^3/(mol*K)
HE_MOLAR_MASS_KG_MOL = 4.002602e-3

# Apply only the FINE_TEST measurement period; exclude venting / ready.
FILTER_FINE_TEST = True

# He導入までの時間 [分]：ここを直接変更してください。
# CSV記録開始から10分後にHeを導入した場合は 10.0 に設定します。
# 導入前をカットし、He導入時点を比較グラフの時刻0にします。
# 実際の導入時刻を設定してください（0.0 はCSV記録開始）。
HE_START_MIN = 6.0
# EXP_END_MIN = 600.0   # He導入後90分まで使用
# Remove pre-He samples before smoothing, plotting, and comparison/export.
# Baseline estimation still uses the original measurement data.
TRIM_BEFORE_HE = True

# Experimental baseline correction: "none", "fixed", "initial_median".
BASELINE_METHOD = "none"
BASELINE_FIXED_PA_M3_S = 0.0
BASELINE_INITIAL_WINDOW_S = (0.0, 300.0)

# Smooth experimental trace for display and t50 ONLY. Raw data is retained.
SMOOTH_POINTS = 11            # ~22 seconds at ~2 sec per sample.

# The last N sec of FINE_TEST are used as an experimental REFERENCE level.
# This is not proof of a physically steady plateau.
EXP_REFERENCE_LAST_S = 300.0
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


def read_mse_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"MSE-2600 CSV not found: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    required = {"elapsed_s", "leak_rate", "leak_rate_unit", "process"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing MSE-2600 columns: {sorted(missing)}")
    unit = df["leak_rate_unit"].dropna().astype(str).str.strip().unique()
    if set(unit) != {"Pa_m3_s"}:
        raise ValueError(f"Expected Pa_m3_s leak-rate units; got {list(unit)}")
    if FILTER_FINE_TEST:
        df = df[df["process"].astype(str).str.strip() == "FINE_TEST"].copy()
    df["elapsed_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
    df["leak_rate"] = pd.to_numeric(df["leak_rate"], errors="coerce")
    df = df.dropna(subset=["elapsed_s", "leak_rate"])
    df = df.sort_values("elapsed_s").drop_duplicates("elapsed_s")
    if len(df) < 3:
        raise ValueError("Too few valid experimental data points.")
    return df.reset_index(drop=True)


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
    time_zero_s = HE_START_MIN * 60.0
    if args.he_start_s is not None:
        time_zero_s = args.he_start_s
    elif args.he_start_min is not None:
        time_zero_s = args.he_start_min * 60.0
    if not np.isfinite(time_zero_s) or time_zero_s < 0:
        raise ValueError("He introduction time must be finite and non-negative.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    sim = read_abaqus_rpt(ABAQUS_RPT)
    exp = read_mse_csv(MSE_CSV)

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
    exp["time_s"] = exp["elapsed_s"] - time_zero_s
    exp["time_min"] = exp["time_s"] / 60.0
    exp["q_raw_Pa_m3_s"] = exp["leak_rate"]

    if BASELINE_METHOD == "none":
        background = 0.0
    elif BASELINE_METHOD == "fixed":
        background = BASELINE_FIXED_PA_M3_S
    elif BASELINE_METHOD == "initial_median":
        a, b = BASELINE_INITIAL_WINDOW_S
        first = exp.loc[exp["elapsed_s"].between(a, b), "leak_rate"]
        if first.empty:
            raise ValueError("Empty baseline window. Adjust BASELINE_INITIAL_WINDOW_S.")
        background = float(first.median())
    else:
        raise ValueError("BASELINE_METHOD must be none / fixed / initial_median")

    removed_rows = 0
    if TRIM_BEFORE_HE:
        removed_rows = int((exp["time_s"] < 0).sum())
        exp = exp.loc[exp["time_s"] >= 0].copy().reset_index(drop=True)
        if len(exp) < 3:
            raise ValueError("Too few experimental points after trimming. Check He introduction time.")

    exp["q_corrected_Pa_m3_s"] = exp["q_raw_Pa_m3_s"] - background
    exp["q_smooth_Pa_m3_s"] = (exp["q_corrected_Pa_m3_s"]
                                  .rolling(max(1, SMOOTH_POINTS), center=True,
                                           min_periods=1).median())

    if SIM_REFERENCE_LAST_S > 0:
        sim_ref = last_window_reference(sim, "time_s", "q_Pa_m3_s", SIM_REFERENCE_LAST_S)
    else:
        sim_ref = float(sim["q_Pa_m3_s"].iloc[-1])
    exp_ref = last_window_reference(exp, "elapsed_s", "q_smooth_Pa_m3_s",
                                    EXP_REFERENCE_LAST_S)
    if min(sim_ref, exp_ref) <= 0:
        raise ValueError("Reference flow must be positive; verify settings.")

    sim["normalized"] = sim["q_Pa_m3_s"] / sim_ref
    exp["normalized"] = exp["q_smooth_Pa_m3_s"] / exp_ref

    sim_t50_s = interpolate_crossing(sim["time_s"], sim["normalized"])
    exp_t50_s = interpolate_crossing(exp["time_s"], exp["normalized"])

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
    plt.axhline(exp_ref, ls=":", lw=1, label="MSE end-window reference")
    plt.xlim(x_min, x_max)
    plt.xlabel("Time [s]")
    plt.ylabel(r"He leak rate [Pa $\cdot$ m$^3$/s]", fontsize=Y_AXIS_LABEL_FONT_SIZE_PT)
    plt.title("PEEK 2 mm: absolute leak-rate comparison")
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
    plt.title("PEEK 2 mm: normalized permeation response")
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
    plt.title("PEEK 2 mm: early-time comparison (log scale)")
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
        "PP 3 mm: Abaqus vs MSE-2600 (NO FITTING)\n"
        "=====================================================\n"
        f"RPT rows: {len(sim)}, MSE FINE_TEST rows: {len(exp)}\n"
        f"Model area: {model_area_mm2:.6g} mm^2 (assumed depth={MODEL_OUT_OF_PLANE_MM} mm)\n"
        f"Experiment area: {EXP_AREA_MM2:.6g} mm^2\n"
        f"Area factor: {area_ratio:.8g}\n"
        f"RFL -> Q factor: {convert_factor:.8e} (Pa*m^3/s)/(kg/s)\n"
        f"Background method: {BASELINE_METHOD}, background: {background:.8e} Pa*m^3/s\n"
        f"Experimental zero time at elapsed_s={time_zero_s:.3f}\n"
        f"Trim before He: {TRIM_BEFORE_HE}, removed rows: {removed_rows}\n"
        f"Abaqus final RFL: {sim['rfl_raw'].iloc[-1]:.8e} (mass-unit/s)\n"
        f"Abaqus reference Q: {sim_ref:.8e} Pa*m^3/s\n"
        f"MSE reference Q (last {EXP_REFERENCE_LAST_S:.0f} s median): {exp_ref:.8e} Pa*m^3/s\n"
        f"MSE FINE_TEST maximum Q (raw): {exp['q_raw_Pa_m3_s'].max():.8e} Pa*m^3/s\n"
        f"Abaqus / MSE reference ratio: {sim_ref/exp_ref:.6f}\n"
        f"Abaqus t50 (with chosen reference): {sim_t50_s:.5f} s\n"
        f"MSE t50 (with chosen reference): {exp_t50_s:.5f} s\n"
        f"t50 difference (MSE - Abaqus): {exp_t50_s-sim_t50_s:.5f} s\n"
        f"Overlap RMSE [Pa*m^3/s]: {rmse:.8e}\n"
        f"Overlap normalized RMSE: {norm_rmse:.6f}\n"
        "\nCAUTIONS:\n"
        "- RFL is assumed kg/s, requiring consistent Abaqus unit conventions.\n"
        "- Abaqus 2D out-of-plane depth is ASSUMED 1 mm until verified.\n"
        "- Final experimental 300 s median is a REFERENCE, not proven steady state.\n"
        "- Experimental time zero is not automatically He exposure onset.\n"
        "- FINE_TEST selection removes VENTING/TEST_READY but not a He supply change.\n"
        "- RMSE is descriptive only; no parameter fitting has been performed.\n"
    )
    output_path("summary.txt").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"Saved outputs to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
