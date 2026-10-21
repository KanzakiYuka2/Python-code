from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


# =========================================================
# User settings
# =========================================================

INPUT_CSV = Path("asm340_log_20260617_130620.csv")

TIME_COLUMN = "pc_datetime"
Q_COLUMN = "leak_rate_mbar_l_s"


# ---------------------------------------------------------
# Data-selection mode
# ---------------------------------------------------------
#
# Choose one:
#
# "last"
#     Analyze the final LAST_HOURS of the experiment.
#
# "range"
#     Analyze data between START_HOUR and END_HOUR.
#     These hours are elapsed hours from the first CSV record.
#
SELECTION_MODE = "last"


# Used when SELECTION_MODE = "last"
LAST_HOURS = 3.0


# Used when SELECTION_MODE = "range"
#
# Example:
# START_HOUR = 5
# END_HOUR = 8
#
# means analyze only the data from experiment hour 5
# until experiment hour 8.
START_HOUR = 5.0
END_HOUR = 8.0


# ---------------------------------------------------------
# Graph settings
# ---------------------------------------------------------

USE_LOG_SCALE = True

# Optional fixed logarithmic y-axis range.
# Set FIX_Y_LIMIT = False to use automatic limits.
FIX_Y_LIMIT = True
Y_MIN = 1e-11
Y_MAX = 1e-6

FULL_GRAPH_DOT_SIZE = 4
SELECTED_GRAPH_DOT_SIZE = 8
MODE_DOT_SIZE = 28

SAVE_GRAPHS = True
SHOW_GRAPHS = True
GRAPH_DPI = 200


# =========================================================
# Load and clean data
# =========================================================

def load_data(
    input_csv: Path,
    time_column: str,
    q_column: str,
) -> pd.DataFrame:
    """
    Load the CSV and create elapsed time in hours.

    The first valid timestamp becomes elapsed time = 0 hours.
    """

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
            "The required columns were not found.\n"
            f"Required time column: {time_column}\n"
            f"Required Q column   : {q_column}"
        ) from exc

    # Convert the timestamp column.
    df[time_column] = pd.to_datetime(
        df[time_column],
        errors="coerce",
    )

    # Convert leak-rate Q to numeric data.
    df[q_column] = pd.to_numeric(
        df[q_column],
        errors="coerce",
    )

    # Remove invalid rows.
    df = (
        df.dropna(subset=[time_column, q_column])
        .sort_values(time_column)
        .reset_index(drop=True)
    )

    if df.empty:
        raise ValueError(
            "No valid timestamp and leak-rate Q data were found."
        )

    # Logarithmic axes cannot display zero or negative values.
    if USE_LOG_SCALE:
        invalid_q_count = int(
            (df[q_column] <= 0).sum()
        )

        if invalid_q_count > 0:
            print(
                f"Warning: {invalid_q_count:,} zero or negative "
                "Q values were removed."
            )

            df = df.loc[
                df[q_column] > 0
            ].copy()

    if df.empty:
        raise ValueError(
            "No usable positive leak-rate Q values remain."
        )

    # The first timestamp becomes zero hours.
    experiment_start_time = df[time_column].min()

    df["elapsed_hours"] = (
        df[time_column] - experiment_start_time
    ).dt.total_seconds() / 3600.0

    return df


# =========================================================
# Select the period used for mode calculation
# =========================================================

def select_analysis_period(
    df: pd.DataFrame,
    selection_mode: str,
    last_hours: float,
    start_hour: float,
    end_hour: float,
) -> dict:
    """
    Select either:

    1. The final N hours, or
    2. A specific elapsed-hour range.
    """

    maximum_elapsed_hour = float(
        df["elapsed_hours"].max()
    )

    mode_name = selection_mode.strip().lower()

    if mode_name == "last":

        if last_hours <= 0:
            raise ValueError(
                "LAST_HOURS must be greater than zero."
            )

        selected_end_hour = maximum_elapsed_hour

        selected_start_hour = max(
            0.0,
            selected_end_hour - last_hours,
        )

        selection_description = (
            f"Final {last_hours:g} hours"
        )

    elif mode_name == "range":

        if start_hour < 0:
            raise ValueError(
                "START_HOUR cannot be negative."
            )

        if end_hour <= start_hour:
            raise ValueError(
                "END_HOUR must be greater than START_HOUR."
            )

        selected_start_hour = start_hour
        selected_end_hour = end_hour

        selection_description = (
            f"Elapsed hour {start_hour:g} "
            f"to {end_hour:g}"
        )

        if selected_start_hour > maximum_elapsed_hour:
            raise ValueError(
                "START_HOUR is outside the available data range.\n"
                f"Maximum available elapsed time: "
                f"{maximum_elapsed_hour:.6f} hours"
            )

        if selected_end_hour > maximum_elapsed_hour:
            print(
                "Warning: END_HOUR exceeds the available data.\n"
                f"Requested END_HOUR : {selected_end_hour:.6f}\n"
                f"Available end hour : {maximum_elapsed_hour:.6f}\n"
                "The analysis will use all available data until "
                "the end of the CSV."
            )

            selected_end_hour = maximum_elapsed_hour

    else:
        raise ValueError(
            "SELECTION_MODE must be either 'last' or 'range'."
        )

    # Extract only the selected period.
    selected_df = df.loc[
        (df["elapsed_hours"] >= selected_start_hour)
        & (df["elapsed_hours"] <= selected_end_hour)
    ].copy()

    if selected_df.empty:
        raise ValueError(
            "No data were found in the selected period."
        )

    return {
        "selected_df": selected_df,
        "selected_start_hour": selected_start_hour,
        "selected_end_hour": selected_end_hour,
        "selection_description": selection_description,
        "maximum_elapsed_hour": maximum_elapsed_hour,
    }


# =========================================================
# Calculate exact-value mode
# =========================================================

def calculate_mode(
    selected_df: pd.DataFrame,
    q_column: str,
) -> dict:
    """
    Calculate the exact-value mode of leak-rate Q.

    If several Q values have the same highest occurrence count,
    all tied mode values are returned.
    """

    frequency_counts = selected_df[
        q_column
    ].value_counts(dropna=True)

    if frequency_counts.empty:
        raise ValueError(
            "No valid Q values exist in the selected period."
        )

    maximum_count = int(
        frequency_counts.max()
    )

    mode_values = (
        frequency_counts.loc[
            frequency_counts == maximum_count
        ]
        .index
        .tolist()
    )

    total_count = int(
        len(selected_df)
    )

    frequency_percentage = (
        maximum_count / total_count * 100.0
    )

    actual_start_hour = float(
        selected_df["elapsed_hours"].min()
    )

    actual_end_hour = float(
        selected_df["elapsed_hours"].max()
    )

    actual_duration_hours = (
        actual_end_hour - actual_start_hour
    )

    if actual_duration_hours > 0:
        occurrences_per_hour = (
            maximum_count / actual_duration_hours
        )
    else:
        occurrences_per_hour = float("nan")

    first_timestamp = selected_df[
        TIME_COLUMN
    ].min()

    last_timestamp = selected_df[
        TIME_COLUMN
    ].max()

    return {
        "mode_values": mode_values,
        "mode_count": maximum_count,
        "total_count": total_count,
        "frequency_percentage": frequency_percentage,
        "occurrences_per_hour": occurrences_per_hour,
        "actual_start_hour": actual_start_hour,
        "actual_end_hour": actual_end_hour,
        "actual_duration_hours": actual_duration_hours,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
    }


# =========================================================
# Terminal output
# =========================================================

def print_results(
    input_csv: Path,
    df: pd.DataFrame,
    period_result: dict,
    mode_result: dict,
) -> None:
    """Print mode information to the terminal."""

    experiment_start = df[
        TIME_COLUMN
    ].min()

    experiment_end = df[
        TIME_COLUMN
    ].max()

    print()
    print("=" * 76)
    print("Leak-rate Q mode analysis")
    print("=" * 76)

    print(
        f"Input CSV                : "
        f"{input_csv.resolve()}"
    )

    print(
        f"Experiment start         : "
        f"{experiment_start}"
    )

    print(
        f"Experiment end           : "
        f"{experiment_end}"
    )

    print(
        f"Total experiment duration: "
        f"{period_result['maximum_elapsed_hour']:.6f} h"
    )

    print("-" * 76)

    print(
        f"Selection mode           : "
        f"{SELECTION_MODE}"
    )

    print(
        f"Selected period          : "
        f"{period_result['selection_description']}"
    )

    print(
        f"Selected elapsed range   : "
        f"{period_result['selected_start_hour']:.6f} "
        f"to "
        f"{period_result['selected_end_hour']:.6f} h"
    )

    print(
        f"Actual first data hour   : "
        f"{mode_result['actual_start_hour']:.6f} h"
    )

    print(
        f"Actual last data hour    : "
        f"{mode_result['actual_end_hour']:.6f} h"
    )

    print(
        f"Actual first timestamp   : "
        f"{mode_result['first_timestamp']}"
    )

    print(
        f"Actual last timestamp    : "
        f"{mode_result['last_timestamp']}"
    )

    print(
        f"Number of selected points: "
        f"{mode_result['total_count']:,}"
    )

    print("-" * 76)

    if len(mode_result["mode_values"]) == 1:
        print("Mode result")
    else:
        print(
            "Mode result "
            f"({len(mode_result['mode_values'])} tied values)"
        )

    for mode_number, mode_value in enumerate(
        mode_result["mode_values"],
        start=1,
    ):
        print(
            f"Mode Q #{mode_number:<15}: "
            f"{mode_value:.12e} mbar L/s"
        )

    print(
        f"Occurrence count         : "
        f"{mode_result['mode_count']:,}"
    )

    print(
        f"Frequency percentage     : "
        f"{mode_result['frequency_percentage']:.6f} %"
    )

    print(
        f"Occurrences per hour     : "
        f"{mode_result['occurrences_per_hour']:.3f} /h"
    )

    print("=" * 76)
    print()


# =========================================================
# Common graph formatting
# =========================================================

def configure_graph(
    ax: plt.Axes,
    title: str,
) -> None:
    """Apply common formatting to a graph."""

    ax.set_xlabel(
        "Elapsed time [h]"
    )

    ax.set_ylabel(
        "Leak rate Q [mbar L/s]"
    )

    ax.set_title(
        title
    )

    if USE_LOG_SCALE:
        ax.set_yscale(
            "log"
        )

    if FIX_Y_LIMIT:
        ax.set_ylim(
            Y_MIN,
            Y_MAX,
        )

    ax.grid(
        True,
        which="both",
        alpha=0.3,
    )

    # Main x-axis ticks every one hour.
    ax.xaxis.set_major_locator(
        MultipleLocator(1.0)
    )

    # Minor ticks every 0.25 hour = 15 minutes.
    ax.xaxis.set_minor_locator(
        MultipleLocator(0.25)
    )


# =========================================================
# Graph 1: complete leak-rate data
# =========================================================

def create_full_graph(
    df: pd.DataFrame,
    input_csv: Path,
    q_column: str,
) -> Path:
    """
    Create a dot graph of the complete experiment.

    The first timestamp is shown as elapsed time = 0 hours.
    """

    fig, ax = plt.subplots(
        figsize=(13, 6.5)
    )

    ax.scatter(
        df["elapsed_hours"],
        df[q_column],
        s=FULL_GRAPH_DOT_SIZE,
        alpha=0.55,
        label="Leak rate Q",
    )

    ax.set_xlim(
        left=0,
    )

    configure_graph(
        ax=ax,
        title="Full Leak-rate Q Data",
    )

    ax.legend()

    fig.tight_layout()

    output_path = input_csv.with_name(
        f"{input_csv.stem}_full_leakrate_dots.png"
    )

    if SAVE_GRAPHS:
        fig.savefig(
            output_path,
            dpi=GRAPH_DPI,
            bbox_inches="tight",
        )

        print(
            f"Saved full graph          : "
            f"{output_path.resolve()}"
        )

    return output_path


# =========================================================
# Graph 2: selected period and mode
# =========================================================

def create_selected_mode_graph(
    selected_df: pd.DataFrame,
    period_result: dict,
    mode_result: dict,
    input_csv: Path,
    q_column: str,
) -> Path:
    """
    Create a dot graph for the selected period.

    All data are shown as dots.
    Mode occurrences are shown using larger dots.
    """

    fig, ax = plt.subplots(
        figsize=(13, 6.5)
    )

    # All Q data in the selected period.
    ax.scatter(
        selected_df["elapsed_hours"],
        selected_df[q_column],
        s=SELECTED_GRAPH_DOT_SIZE,
        alpha=0.5,
        label="Selected leak rate Q",
    )

    # Identify all rows whose Q is one of the mode values.
    mode_mask = selected_df[
        q_column
    ].isin(
        mode_result["mode_values"]
    )

    mode_df = selected_df.loc[
        mode_mask
    ]

    # Highlight mode occurrences using larger dots.
    ax.scatter(
        mode_df["elapsed_hours"],
        mode_df[q_column],
        s=MODE_DOT_SIZE,
        alpha=0.9,
        label=(
            "Mode occurrence "
            f"(count = {mode_result['mode_count']:,})"
        ),
        zorder=3,
    )

    ax.set_xlim(
        period_result["selected_start_hour"],
        period_result["selected_end_hour"],
    )

    configure_graph(
        ax=ax,
        title=(
            "Leak-rate Q and Mode: "
            f"{period_result['selection_description']}"
        ),
    )

    ax.legend()

    fig.tight_layout()

    if SELECTION_MODE.lower() == "last":
        selection_label = (
            f"last_{LAST_HOURS:g}h"
        )
    else:
        selection_label = (
            f"hour_{START_HOUR:g}_to_{END_HOUR:g}"
        )

    selection_label = selection_label.replace(
        ".",
        "p",
    )

    output_path = input_csv.with_name(
        f"{input_csv.stem}_"
        f"{selection_label}_mode_dots.png"
    )

    if SAVE_GRAPHS:
        fig.savefig(
            output_path,
            dpi=GRAPH_DPI,
            bbox_inches="tight",
        )

        print(
            f"Saved selected graph      : "
            f"{output_path.resolve()}"
        )

    return output_path


# =========================================================
# Main program
# =========================================================

def main() -> None:
    # Load and clean the complete data.
    df = load_data(
        input_csv=INPUT_CSV,
        time_column=TIME_COLUMN,
        q_column=Q_COLUMN,
    )

    # Select the period used to calculate the mode.
    period_result = select_analysis_period(
        df=df,
        selection_mode=SELECTION_MODE,
        last_hours=LAST_HOURS,
        start_hour=START_HOUR,
        end_hour=END_HOUR,
    )

    selected_df = period_result[
        "selected_df"
    ]

    # Calculate the mode from only the selected period.
    mode_result = calculate_mode(
        selected_df=selected_df,
        q_column=Q_COLUMN,
    )

    # Print the mode and frequency information.
    print_results(
        input_csv=INPUT_CSV,
        df=df,
        period_result=period_result,
        mode_result=mode_result,
    )

    # Graph 1: complete experiment, starting at zero hours.
    create_full_graph(
        df=df,
        input_csv=INPUT_CSV,
        q_column=Q_COLUMN,
    )

    # Graph 2: selected period with mode points highlighted.
    create_selected_mode_graph(
        selected_df=selected_df,
        period_result=period_result,
        mode_result=mode_result,
        input_csv=INPUT_CSV,
        q_column=Q_COLUMN,
    )

    if SHOW_GRAPHS:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()