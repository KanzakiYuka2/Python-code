from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# =========================================================
# User settings
# =========================================================

# Put this Python file in the same folder as the CSV,
# or specify the full path to the CSV here.
INPUT_CSV = Path("asm340_log_20260617_130620.csv")

# Analyze the last N hours counted backward from the latest
# timestamp contained in the CSV.
LAST_HOURS = 3.0

# Column names used in the ASM340 CSV.
TIME_COLUMN = "pc_datetime"
Q_COLUMN = "leak_rate_mbar_l_s"

# Graph settings.
USE_LOG_SCALE = True
SAVE_GRAPHS = True
SHOW_GRAPHS = True
GRAPH_DPI = 200


# =========================================================
# Data loading and mode analysis
# =========================================================


def load_data(
    input_csv: Path,
    time_column: str,
    q_column: str,
) -> pd.DataFrame:
    """Load and clean the timestamp and leak-rate Q columns."""

    if not input_csv.exists():
        raise FileNotFoundError(
            f"CSV file was not found:\n{input_csv.resolve()}"
        )

    try:
        df = pd.read_csv(
            input_csv,
            usecols=[time_column, q_column],
            low_memory=False,
        )
    except ValueError as exc:
        raise ValueError(
            "The required columns were not found in the CSV.\n"
            f"Required columns: {time_column}, {q_column}"
        ) from exc

    df[time_column] = pd.to_datetime(
        df[time_column],
        errors="coerce",
    )

    df[q_column] = pd.to_numeric(
        df[q_column],
        errors="coerce",
    )

    df = (
        df.dropna(subset=[time_column, q_column])
        .sort_values(time_column)
        .reset_index(drop=True)
    )

    if df.empty:
        raise ValueError(
            "No valid time and leak-rate Q data were found."
        )

    if USE_LOG_SCALE:
        # A logarithmic y-axis cannot display zero or negative values.
        invalid_count = int((df[q_column] <= 0).sum())

        if invalid_count > 0:
            print(
                f"Warning: {invalid_count:,} zero or negative Q values "
                "were removed for logarithmic plotting and analysis."
            )

            df = df.loc[df[q_column] > 0].copy()

    if df.empty:
        raise ValueError(
            "No usable positive Q values remain."
        )

    return df


def analyze_last_hours(
    df: pd.DataFrame,
    last_hours: float,
    time_column: str,
    q_column: str,
) -> dict:
    """
    Trim the data to the last specified number of hours and calculate
    the exact-value mode of leak-rate Q.

    If several values have the same maximum count, all tied modes are
    retained.
    """

    if last_hours <= 0:
        raise ValueError(
            "LAST_HOURS must be greater than zero."
        )

    latest_time = df[time_column].max()

    requested_start_time = (
        latest_time - pd.Timedelta(hours=last_hours)
    )

    trimmed_df = df.loc[
        (df[time_column] >= requested_start_time)
        & (df[time_column] <= latest_time)
    ].copy()

    if trimmed_df.empty:
        raise ValueError(
            "No data were found in the selected time range."
        )

    # Count the exact occurrence frequency of each Q value.
    counts = trimmed_df[q_column].value_counts(
        dropna=True
    )

    maximum_count = int(counts.max())

    # There may be several modes if multiple Q values have
    # the same maximum occurrence count.
    mode_values = (
        counts.loc[counts == maximum_count]
        .index
        .tolist()
    )

    total_count = int(len(trimmed_df))

    frequency_percent = (
        maximum_count / total_count * 100.0
    )

    actual_start_time = trimmed_df[time_column].min()
    actual_end_time = trimmed_df[time_column].max()

    actual_duration_hours = (
        actual_end_time - actual_start_time
    ).total_seconds() / 3600.0

    if actual_duration_hours > 0:
        occurrences_per_hour = (
            maximum_count / actual_duration_hours
        )
    else:
        occurrences_per_hour = float("nan")

    return {
        "trimmed_df": trimmed_df,
        "mode_values": mode_values,
        "mode_count": maximum_count,
        "total_count": total_count,
        "frequency_percent": frequency_percent,
        "occurrences_per_hour": occurrences_per_hour,
        "requested_start_time": requested_start_time,
        "actual_start_time": actual_start_time,
        "latest_time": latest_time,
        "actual_duration_hours": actual_duration_hours,
    }


# =========================================================
# Terminal output
# =========================================================


def print_results(
    input_csv: Path,
    last_hours: float,
    result: dict,
) -> None:
    """Print the mode-analysis results in the terminal."""

    print("=" * 72)
    print("Leak-rate Q mode analysis")
    print("=" * 72)

    print(
        f"Input CSV              : "
        f"{input_csv.resolve()}"
    )

    print(
        f"Selected final period  : "
        f"{last_hours:g} h"
    )

    print(
        f"Requested start time   : "
        f"{result['requested_start_time']}"
    )

    print(
        f"Actual first data time : "
        f"{result['actual_start_time']}"
    )

    print(
        f"Latest data time       : "
        f"{result['latest_time']}"
    )

    print(
        f"Actual duration        : "
        f"{result['actual_duration_hours']:.6f} h"
    )

    print(
        f"Number of valid points : "
        f"{result['total_count']:,}"
    )

    print("-" * 72)

    if len(result["mode_values"]) == 1:
        print("Mode result")
    else:
        print(
            "Mode result "
            f"({len(result['mode_values'])} values tied "
            "for first place)"
        )

    for number, mode_value in enumerate(
        result["mode_values"],
        start=1,
    ):
        print(
            f"Mode Q #{number:<11} : "
            f"{mode_value:.12e} mbar L/s"
        )

    print(
        f"Occurrence count       : "
        f"{result['mode_count']:,}"
    )

    print(
        f"Frequency percentage   : "
        f"{result['frequency_percent']:.6f} %"
    )

    print(
        f"Occurrences per hour   : "
        f"{result['occurrences_per_hour']:.3f} /h"
    )

    print("=" * 72)


# =========================================================
# Graph creation
# =========================================================


def format_time_axis(ax: plt.Axes) -> None:
    """Apply readable automatic date-time labels."""

    locator = mdates.AutoDateLocator(
        minticks=4,
        maxticks=10,
    )

    formatter = mdates.ConciseDateFormatter(
        locator
    )

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)


def create_full_graph(
    df: pd.DataFrame,
    input_csv: Path,
    time_column: str,
    q_column: str,
) -> Path:
    """
    Graph 1:
    Plot the complete leak-rate Q time series.
    """

    fig, ax = plt.subplots(
        figsize=(13, 6.5)
    )

    ax.plot(
        df[time_column],
        df[q_column],
        linewidth=0.7,
        label="Leak rate Q",
    )

    if USE_LOG_SCALE:
        ax.set_yscale("log")

    ax.set_xlabel("Time")
    ax.set_ylabel(
        "Leak rate Q [mbar L/s]"
    )
    ax.set_title(
        "Full Leak-rate Q Time Series"
    )

    ax.grid(
        True,
        which="both",
        alpha=0.3,
    )

    ax.legend()

    format_time_axis(ax)

    fig.tight_layout()

    output_path = input_csv.with_name(
        f"{input_csv.stem}_full_leakrate.png"
    )

    if SAVE_GRAPHS:
        fig.savefig(
            output_path,
            dpi=GRAPH_DPI,
            bbox_inches="tight",
        )

        print(
            f"Saved full graph        : "
            f"{output_path.resolve()}"
        )

    return output_path


def create_trimmed_mode_graph(
    result: dict,
    input_csv: Path,
    last_hours: float,
    time_column: str,
    q_column: str,
) -> Path:
    """
    Graph 2:
    Plot only the selected final period and highlight every
    data point whose Q value exactly equals the mode.
    """

    trimmed_df = result["trimmed_df"]
    mode_values = result["mode_values"]

    fig, ax = plt.subplots(
        figsize=(13, 6.5)
    )

    # Plot the trimmed leak-rate Q data.
    ax.plot(
        trimmed_df[time_column],
        trimmed_df[q_column],
        linewidth=0.8,
        alpha=0.75,
        label="Leak rate Q",
    )

    for mode_number, mode_value in enumerate(
        mode_values,
        start=1,
    ):
        mode_mask = (
            trimmed_df[q_column] == mode_value
        )

        if len(mode_values) == 1:
            mode_label = (
                f"Mode Q = {mode_value:.3e}"
            )
        else:
            mode_label = (
                f"Mode Q #{mode_number} "
                f"= {mode_value:.3e}"
            )

        # Highlight every occurrence of the mode.
        ax.scatter(
            trimmed_df.loc[
                mode_mask,
                time_column,
            ],
            trimmed_df.loc[
                mode_mask,
                q_column,
            ],
            s=24,
            zorder=4,
            label=f"{mode_label} occurrences",
        )

        # Draw a horizontal line at the mode value.
        ax.axhline(
            y=mode_value,
            linewidth=1.0,
            linestyle="--",
            alpha=0.8,
        )

    if USE_LOG_SCALE:
        ax.set_yscale("log")

    ax.set_xlabel("Time")

    ax.set_ylabel(
        "Leak rate Q [mbar L/s]"
    )

    ax.set_title(
        f"Leak-rate Q and Mode "
        f"in the Final {last_hours:g} Hours"
    )

    ax.grid(
        True,
        which="both",
        alpha=0.3,
    )

    ax.legend()

    format_time_axis(ax)

    fig.tight_layout()

    hours_label = str(last_hours).replace(
        ".",
        "p",
    )

    output_path = input_csv.with_name(
        f"{input_csv.stem}_last_"
        f"{hours_label}h_mode.png"
    )

    if SAVE_GRAPHS:
        fig.savefig(
            output_path,
            dpi=GRAPH_DPI,
            bbox_inches="tight",
        )

        print(
            f"Saved trimmed graph     : "
            f"{output_path.resolve()}"
        )

    return output_path


# =========================================================
# Main
# =========================================================


def main() -> None:
    # Load the complete CSV data.
    df = load_data(
        input_csv=INPUT_CSV,
        time_column=TIME_COLUMN,
        q_column=Q_COLUMN,
    )

    # Analyze only the final specified number of hours.
    result = analyze_last_hours(
        df=df,
        last_hours=LAST_HOURS,
        time_column=TIME_COLUMN,
        q_column=Q_COLUMN,
    )

    # Print mode information in the terminal.
    print_results(
        input_csv=INPUT_CSV,
        last_hours=LAST_HOURS,
        result=result,
    )

    # Graph 1: complete leak-rate history.
    create_full_graph(
        df=df,
        input_csv=INPUT_CSV,
        time_column=TIME_COLUMN,
        q_column=Q_COLUMN,
    )

    # Graph 2: trimmed period with mode highlighted.
    create_trimmed_mode_graph(
        result=result,
        input_csv=INPUT_CSV,
        last_hours=LAST_HOURS,
        time_column=TIME_COLUMN,
        q_column=Q_COLUMN,
    )

    if SHOW_GRAPHS:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()