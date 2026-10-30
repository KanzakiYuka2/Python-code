"""Create an MSE2600 graph sized for the preprint Word document.

The PNG is produced at 7.5 cm x 4.8 cm and 600 dpi. Insert it into Word at
exactly the same dimensions so that the 10 pt axis text is preserved.
"""

import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd


# =========================================================
# User settings
# =========================================================

# Resolve the CSV from this script's Diffusion folder, regardless of cwd.
DIFFUSION_DIR = Path(__file__).resolve().parent
INPUT_CSV = DIFFUSION_DIR / "mse2600_log_20261030_1.csv"

# Change this name for each graph if desired. When left as None, the date in
# the CSV filename is used, for example: maesuri_20260828.png.
# Only the filename is used; output is always saved in DIFFUSION_DIR.
OUTPUT_IMAGE = None

# Remove unwanted data from the beginning or end before plotting.
TRIM_START_MINUTES = 0.0
TRIM_END_MINUTES = 0.0

# Axis range in seconds. Set X_MAX_SECONDS to None to use the complete retained duration.
X_MIN_SECONDS = 0.0
X_MAX_SECONDS = None
Y_MIN = 1e-11
Y_MAX = 1e-6

# Final dimensions in the Word document.
FIGURE_WIDTH_CM = 7.5
FIGURE_HEIGHT_CM = 4.8
FONT_SIZE_PT = 10.0
LINE_WIDTH_PT = 1.4
AXIS_LINE_WIDTH_PT = 1.0
GRAPH_DPI = 600

# Event markers (minutes from the beginning of the displayed data).
# Replace None with the measured value for each CSV, for example 8.0.
HE_INTRODUCTION_MINUTES = 5.0

# t50 is entered as the elapsed time AFTER helium introduction. Its vertical
# line is drawn automatically at HE_INTRODUCTION_MINUTES + T50_MINUTES_AFTER_HE.
# Replace None with the calculated/manual t50, for example 24.5.
T50_MINUTES_AFTER_HE = None

# A compact legend is used because the graph is only 7.5 cm wide in Word.
LEGEND_FONT_SIZE_PT = 7.5


# =========================================================
# Output filename
# =========================================================

if OUTPUT_IMAGE is None:
    date_match = re.search(r"\d{8}", INPUT_CSV.stem)
    suffix = date_match.group() if date_match else INPUT_CSV.stem
    output_image = DIFFUSION_DIR / f"maesuri_{suffix}.png"
else:
    output_image = DIFFUSION_DIR / Path(OUTPUT_IMAGE).name


# =========================================================
# Read and prepare MSE2600 data
# =========================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(f"CSV file was not found:\n{INPUT_CSV.resolve()}")

required_columns = ["elapsed_s", "leak_rate"]

try:
    df = pd.read_csv(
        INPUT_CSV,
        usecols=required_columns,
        encoding="utf-8-sig",
        low_memory=False,
    )
except ValueError as exc:
    raise ValueError(
        "This does not appear to be an MSE2600 CSV. "
        "Required columns: elapsed_s, leak_rate"
    ) from exc

df["elapsed_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
df["leak_rate"] = pd.to_numeric(df["leak_rate"], errors="coerce")
df = (
    df.dropna(subset=required_columns)
    .sort_values("elapsed_s")
    .reset_index(drop=True)
)

# Logarithmic axes cannot display zero or negative leak rates.
df = df.loc[df["leak_rate"] > 0].copy()

if df.empty:
    raise ValueError("No valid positive leak-rate data were found.")

if TRIM_START_MINUTES < 0 or TRIM_END_MINUTES < 0:
    raise ValueError("Trim durations cannot be negative.")

measurement_start_s = float(df["elapsed_s"].iloc[0])
measurement_end_s = float(df["elapsed_s"].iloc[-1])
keep_start_s = measurement_start_s + TRIM_START_MINUTES * 60.0
keep_end_s = measurement_end_s - TRIM_END_MINUTES * 60.0

if keep_end_s <= keep_start_s:
    raise ValueError("The trim settings leave no usable measurement time.")

df = df.loc[
    (df["elapsed_s"] >= keep_start_s)
    & (df["elapsed_s"] <= keep_end_s)
].copy()

if df.empty:
    raise ValueError("No data remain after trimming.")

# Restart the retained data at elapsed time zero.
df["plot_elapsed_s"] = (
    df["elapsed_s"] - float(df["elapsed_s"].iloc[0])
)


# =========================================================
# Make the preprint-sized graph
# =========================================================

cm_to_inch = 1.0 / 2.54

# A serif typeface and STIX mathematical glyphs remain clear when the graph
# is reduced for a two-column paper.
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
    }
)

fig, ax = plt.subplots(
    figsize=(
        FIGURE_WIDTH_CM * cm_to_inch,
        FIGURE_HEIGHT_CM * cm_to_inch,
    ),
    constrained_layout=True,
)

ax.plot(
    df["plot_elapsed_s"],
    df["leak_rate"],
    linewidth=LINE_WIDTH_PT,
    color="#1f77b4",
    label="Leak rate",
)

# Manually specified event lines. The different line styles keep the two
# events distinguishable even when the figure is printed in grayscale.
if HE_INTRODUCTION_MINUTES is not None:
    if HE_INTRODUCTION_MINUTES < 0:
        raise ValueError("HE_INTRODUCTION_MINUTES cannot be negative.")

    he_time_s = HE_INTRODUCTION_MINUTES * 60.0
    ax.axvline(
        he_time_s,
        color="black",
        linestyle="--",
        linewidth=1.0,
        label="He introduced",
    )

    if T50_MINUTES_AFTER_HE is not None:
        if T50_MINUTES_AFTER_HE < 0:
            raise ValueError("T50_MINUTES_AFTER_HE cannot be negative.")

        t50_position_s = (
            HE_INTRODUCTION_MINUTES + T50_MINUTES_AFTER_HE
        ) * 60.0
        ax.axvline(
            t50_position_s,
            color="#d97706",
            linestyle="-.",
            linewidth=1.0,
            label=rf"$t_{{50}}$ = {T50_MINUTES_AFTER_HE * 60.0:g} s",
        )

elif T50_MINUTES_AFTER_HE is not None:
    raise ValueError(
        "Set HE_INTRODUCTION_MINUTES before setting T50_MINUTES_AFTER_HE."
    )

# The title is intentionally omitted because the Word figure caption provides
# the description. Labels and tick numbers use the same final font size.
ax.set_xlabel("Time [s]", fontsize=FONT_SIZE_PT)
ax.set_ylabel("Leak Rate (Q) [Pa·m³/s]", fontsize=FONT_SIZE_PT)
ax.tick_params(
    axis="both",
    which="both",
    labelsize=FONT_SIZE_PT,
    direction="in",
    top=True,
    right=True,
    width=AXIS_LINE_WIDTH_PT,
)
ax.tick_params(
    axis="both",
    which="major",
    length=4.0,
)
ax.tick_params(
    axis="both",
    which="minor",
    length=2.5,
)

for spine in ax.spines.values():
    spine.set_linewidth(AXIS_LINE_WIDTH_PT)

ax.set_yscale("log")
ax.set_ylim(Y_MIN, Y_MAX)
ax.set_xlim(
    left=X_MIN_SECONDS,
    right=X_MAX_SECONDS,
)

# Limit the number of x-axis labels so they remain legible in a 7.5 cm graph.
ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))

ax.grid(
    True,
    which="major",
    alpha=0.2,
    linewidth=0.45,
)

ax.legend(
    loc="best",
    fontsize=LEGEND_FONT_SIZE_PT,
    frameon=True,
    fancybox=False,
    edgecolor="black",
    framealpha=1.0,
    handlelength=2.2,
)

fig.savefig(
    output_image,
    dpi=GRAPH_DPI,
)
plt.close(fig)


# =========================================================
# Results
# =========================================================

print(f"Graph saved as            : {output_image.resolve()}")
print(f"Image size for Word       : {FIGURE_WIDTH_CM:g} x {FIGURE_HEIGHT_CM:g} cm")
print(f"Axis/tick font size       : {FONT_SIZE_PT:g} pt")
print(f"Number of points plotted  : {len(df):,}")
print(f"Trimmed from start        : {TRIM_START_MINUTES:g} min")
print(f"Trimmed from end          : {TRIM_END_MINUTES:g} min")
