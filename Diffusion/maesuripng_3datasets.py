"""MSE2600の3つのCSVを、個別に前後カットして同じグラフに表示する。"""

from pathlib import Path
import math

import matplotlib

# PNG保存専用のため、GUI/Tkを必要としないバックエンドを使用。
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, LogLocator, NullFormatter, MultipleLocator
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

# CSV名、凡例名、先頭/末尾からカットする時間（分）をそれぞれ設定。
# 相対パスはこのスクリプトのあるフォルダを基準にします。
DATASETS = [
    dict(file="mse2600_log_20260721_1.csv", label="1mm",
         trim_start_minutes=8.0, trim_end_minutes=0.0, qs_last_minutes=10.0,
         color="#1f77b4", linestyle="-"),
    dict(file="mse2600_log_20260716_1.csv", label="2mm",
         trim_start_minutes=6.0, trim_end_minutes=5.0, qs_last_minutes=10.0,
         color="#d97706", linestyle="--"),
    dict(file="mse2600_log_20260724_1.csv", label="3mm",
         trim_start_minutes=0.0, trim_end_minutes=120.0, qs_last_minutes=10.0,
         color="#2ca02c", linestyle="-."),
]

# qs_last_minutes: カット後の末尾何分をQsの算術平均に使うか。
# 横軸の表示範囲に関係なく、各データのカット後の末尾を使用します。

OUTPUT_IMAGE = "maesuri_comparison_3datasets.png"
X_MIN_SECONDS = 0.0
# None uses the shortest retained duration; a number overrides it in seconds.
X_MAX_SECONDS = None
Y_MIN = 1e-11
Y_MAX = 1e-6
# Poster panel dimensions; insert at these dimensions to preserve font sizes.
FIGURE_WIDTH_CM = 25.94
FIGURE_HEIGHT_CM = 17.29
FONT_SIZE_PT = 36.0
TICK_FONT_SIZE_PT = 30.0
LINE_WIDTH_PT = 3.2
AXIS_LINE_WIDTH_PT = 1.8
GRAPH_DPI = 600
LEGEND_FONT_SIZE_PT = 26.0
# Labeled ticks every 1000 seconds; minor ticks every 100 seconds.
X_MAJOR_TICK_SECONDS = 1000.0
X_MINOR_SUBDIVISIONS = 10


def prepare_data(config):
    """元コードと同様に、カット後の最初の点を時刻0にする。"""
    name = config["label"]
    start = float(config["trim_start_minutes"])
    end = float(config["trim_end_minutes"])
    if not all(math.isfinite(v) and v >= 0 for v in (start, end)):
        raise ValueError(f"{name}: カット時間は0以上の有限値にしてください。")
    csv_path = BASE_DIR / config["file"]
    if not csv_path.is_file():
        raise FileNotFoundError(f"{name}: CSVが見つかりません: {csv_path}")
    columns = ["elapsed_s", "leak_rate"]
    try:
        df = pd.read_csv(csv_path, usecols=columns, encoding="utf-8-sig", low_memory=False)
    except ValueError as exc:
        raise ValueError(f"{name}: elapsed_s, leak_rate列が必要です。") from exc
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    df = df.dropna(subset=columns).sort_values("elapsed_s").reset_index(drop=True)
    df = df.loc[df["leak_rate"] > 0].copy()
    if df.empty:
        raise ValueError(f"{name}: 有効な正のリークレートがありません。")
    keep_start = float(df["elapsed_s"].iloc[0]) + start * 60
    keep_end = float(df["elapsed_s"].iloc[-1]) - end * 60
    if keep_end <= keep_start:
        raise ValueError(f"{name}: カット時間が長すぎます。")
    df = df.loc[df["elapsed_s"].between(keep_start, keep_end)].copy()
    if df.empty:
        raise ValueError(f"{name}: カット後にデータが残りません。")
    df["plot_time_s"] = df["elapsed_s"] - float(df["elapsed_s"].iloc[0])
    return df


def main():
    if len(DATASETS) != 3:
        raise ValueError("DATASETSに3つのデータを設定してください。")
    prepared = [(config, prepare_data(config)) for config in DATASETS]
    qs_results = []
    for config, df in prepared:
        window_minutes = float(config["qs_last_minutes"])
        duration_s = float(df["plot_time_s"].iloc[-1])
        if not math.isfinite(window_minutes) or window_minutes <= 0:
            raise ValueError(f"{config['label']}: qs_last_minutes must be finite and positive.")
        if window_minutes * 60 > duration_s:
            raise ValueError(f"{config['label']}: Qs averaging interval exceeds retained duration.")
        tail = df.loc[df["plot_time_s"] >= duration_s - window_minutes * 60, "leak_rate"]
        qs_results.append((float(tail.mean()), len(tail)))
    shortest_duration_s = min(float(df["plot_time_s"].iloc[-1]) for _, df in prepared)
    x_max_seconds = shortest_duration_s if X_MAX_SECONDS is None else X_MAX_SECONDS
    if not math.isfinite(x_max_seconds) or x_max_seconds <= X_MIN_SECONDS:
        raise ValueError("The x-axis maximum must be finite and greater than X_MIN_SECONDS.")
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "stix",
    })
    fig, ax = plt.subplots(
        figsize=(FIGURE_WIDTH_CM / 2.54, FIGURE_HEIGHT_CM / 2.54),
        constrained_layout=True,
    )
    for (config, df), (qs, _) in zip(prepared, qs_results):
        ax.plot(df["plot_time_s"], df["leak_rate"], label=config["label"],
                color=config["color"], linestyle=config["linestyle"],
                linewidth=LINE_WIDTH_PT)
        ax.axhline(qs, color=config["color"], linestyle=":", linewidth=2.8,
                   label="_nolegend_")
    ax.set_xlabel("Time [s]", fontsize=FONT_SIZE_PT)
    ax.set_ylabel(r"Leak Rate (Q) [Pa$\cdot$m$^3$/s]", fontsize=FONT_SIZE_PT)
    ax.tick_params(axis="both", which="both", labelsize=TICK_FONT_SIZE_PT,
                   direction="in", top=False, right=False, width=AXIS_LINE_WIDTH_PT)
    ax.tick_params(axis="both", which="major", length=9.0, pad=8.0)
    ax.tick_params(axis="both", which="minor", length=5.0)
    for spine in ax.spines.values():
        spine.set_linewidth(AXIS_LINE_WIDTH_PT)
    ax.set_yscale("log")
    ax.set_ylim(Y_MIN, Y_MAX)
    ax.set_xlim(left=X_MIN_SECONDS, right=x_max_seconds)
    ax.xaxis.set_major_locator(MultipleLocator(X_MAJOR_TICK_SECONDS))
    ax.xaxis.set_minor_locator(AutoMinorLocator(X_MINOR_SUBDIVISIONS))
    ax.yaxis.set_major_locator(LogLocator(base=10, numticks=12))
    ax.yaxis.set_minor_locator(LogLocator(base=10, subs=range(2, 10), numticks=100))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.grid(True, which="major", alpha=0.3, linewidth=0.8)
    ax.grid(True, which="minor", alpha=0.12, linewidth=0.5)
    ax.legend(loc="best",
              fontsize=LEGEND_FONT_SIZE_PT, frameon=True,
              fancybox=False, edgecolor="black", framealpha=1.0, handlelength=1.6,
              borderpad=0.3, labelspacing=0.3, handletextpad=0.5)
    output_image = BASE_DIR / OUTPUT_IMAGE
    fig.savefig(output_image, dpi=GRAPH_DPI)
    # Vector PDF remains sharp when resized in the poster layout.
    output_pdf = output_image.with_suffix(".pdf")
    fig.savefig(output_pdf)
    plt.close(fig)
    print(f"Graph saved as: {output_image.resolve()}")
    print(f"Vector PDF saved as: {output_pdf.resolve()}")
    print(f"Poster panel size: {FIGURE_WIDTH_CM:g} x {FIGURE_HEIGHT_CM:g} cm")
    print(f"X-axis range: {X_MIN_SECONDS:g} to {x_max_seconds:g} s")
    for (config, df), (qs, qs_points) in zip(prepared, qs_results):
        print(f"{config['label']}: {len(df):,} points; "
              f"start cut = {config['trim_start_minutes']:g} min; "
              f"end cut = {config['trim_end_minutes']:g} min")
        print(f"  Qs = {qs:.6g} Pa*m^3/s; arithmetic mean of last "
              f"{config['qs_last_minutes']:g} min ({qs_points:,} points)")


if __name__ == "__main__":
    main()
