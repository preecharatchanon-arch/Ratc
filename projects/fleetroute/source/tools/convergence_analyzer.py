
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator, NullFormatter

try:
    from IPython.display import Image, Markdown, display
except Exception:
    Image = None
    Markdown = None
    display = print


# =============================================================================
# USER CONFIGURATION
# =============================================================================

# Normal use: leave these as None. The cell finds the newest raw convergence
# file and then pairs run_summary, solver_output, and colab_output from the same
# folder/run tag.
EXPLICIT_RUN_DIR: Path | None = Path(os.environ["SOLVER_RUN_DIR"]) if os.environ.get("SOLVER_RUN_DIR") else None
EXPLICIT_CONVERGENCE_PATH: Path | None = None

# Optional environment overrides, useful outside Colab:
#   SOLVER_RUN_DIR=/path/to/rep02
#   CONVERGENCE_PATH=/path/to/convergence_....csv
if os.environ.get("SOLVER_RUN_DIR"):
    EXPLICIT_RUN_DIR = Path(os.environ["SOLVER_RUN_DIR"])

if os.environ.get("CONVERGENCE_PATH"):
    EXPLICIT_CONVERGENCE_PATH = Path(
        os.environ["CONVERGENCE_PATH"]
    )

SEARCH_ROOTS = [EXPLICIT_RUN_DIR] if EXPLICIT_RUN_DIR else [Path(".")]

OUTPUT_DIR_NAME = "ConvergenceReport"
FLUSH_OUTPUT_DIR = True
SAVE_DPI = 250
DISPLAY_TABLES_INLINE = False
DISPLAY_FIGURES_INLINE = False
DISPLAY_ALL_FIGURES_INLINE = False
CREATE_ZIP = True

# No road-instance BKS is invented.
#
# Leave None to:
#   1. parse an explicitly printed BKS / best-known value from available logs;
#   2. omit the reference line when no such value exists.
#
# Set a number manually only for a benchmark with a legitimate external
# reference objective.
REFERENCE_OBJECTIVE: float | None = None
REFERENCE_LABEL = "External reference"

# The zoom is computed from the actual convergence trajectory. There are no
# hard-coded "+20", "+180", or instance-specific objective limits.
ZOOM_IMPROVEMENT_FRACTION = 0.18
ZOOM_MIN_TIME_FRACTION = 0.05


def source_file_receipt(path: Path | None) -> dict[str, Any] | None:
    """Content identity used to prove that figures match one raw run."""
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": digest.hexdigest(),
    }


# =============================================================================
# TECHNICAL VISUAL SYSTEM
# =============================================================================

COLORS = {
    "navy": "#0B1F3A",
    "ink": "#172033",
    "teal": "#0F766E",
    "blue": "#2563EB",
    "cyan": "#0E7490",
    "amber": "#B7791F",
    "slate": "#64748B",
    "light_slate": "#94A3B8",
    "grid": "#E2E8F0",
    "border": "#CBD5E1",
    "paper": "#FFFFFF",
    "panel": "#F8FAFC",
    "success": "#15803D",
    "danger": "#B91C1C",
}


def choose_font() -> str:
    preferred = [
        "Inter",
        "Aptos",
        "Arial",
        "Liberation Sans",
        "DejaVu Sans",
    ]

    available = {
        entry.name
        for entry in font_manager.fontManager.ttflist
        if getattr(entry, "name", None)
    }

    for name in preferred:
        if name in available:
            return name

    return "DejaVu Sans"


PRESENTATION_FONT = choose_font()

plt.rcParams.update(
    {
        "font.family": PRESENTATION_FONT,
        "font.size": 10.5,
        "axes.titlesize": 15,
        "axes.titleweight": "semibold",
        "axes.labelsize": 10.5,
        "axes.labelcolor": COLORS["slate"],
        "axes.edgecolor": COLORS["border"],
        "axes.linewidth": 0.8,
        "xtick.color": COLORS["slate"],
        "ytick.color": COLORS["slate"],
        "text.color": COLORS["ink"],
        "figure.facecolor": COLORS["paper"],
        "axes.facecolor": COLORS["paper"],
        "savefig.facecolor": COLORS["paper"],
        "savefig.edgecolor": COLORS["paper"],
        "grid.color": COLORS["grid"],
        "grid.linewidth": 0.65,
        "grid.alpha": 0.75,
        "legend.frameon": True,
        "legend.framealpha": 0.96,
        "legend.edgecolor": COLORS["border"],
    }
)


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            default=lambda value: (
                value.item()
                if isinstance(value, np.generic)
                else str(value)
            ),
        ),
        encoding="utf-8",
    )


def reset_directory(path: Path) -> None:
    if path.exists() and FLUSH_OUTPUT_DIR:
        shutil.rmtree(path)

    path.mkdir(parents=True, exist_ok=True)


def format_objective(value: float, _position: int | None = None) -> str:
    magnitude = abs(value)

    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if magnitude >= 1_000:
        return f"{value / 1_000:.0f}k"

    return f"{value:.0f}"


def style_axis(ax, *, grid_axis: str = "both") -> None:
    ax.set_axisbelow(True)
    ax.grid(
        True,
        axis=grid_axis,
        linestyle=(0, (2, 4)),
        linewidth=0.6,
        alpha=0.8,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["border"])
    ax.spines["bottom"].set_color(COLORS["border"])


def add_figure_header(
    fig,
    title: str,
    subtitle: str,
) -> None:
    fig.suptitle(
        title,
        x=0.085,
        y=0.975,
        ha="left",
        va="top",
        fontsize=17.5,
        fontweight="semibold",
        color=COLORS["navy"],
    )

    fig.text(
        0.085,
        0.935,
        subtitle,
        ha="left",
        va="top",
        fontsize=9.6,
        color=COLORS["slate"],
    )

    fig.add_artist(
        Line2D(
            [0.085, 0.94],
            [0.914, 0.914],
            transform=fig.transFigure,
            color=COLORS["teal"],
            linewidth=1.7,
        )
    )


def save_figure(
    fig,
    path: Path,
    *,
    left: float = 0.085,
    right: float = 0.96,
    bottom: float = 0.10,
    top: float = 0.89,
) -> None:
    fig.subplots_adjust(
        left=left,
        right=right,
        bottom=bottom,
        top=top,
    )

    fig.savefig(
        path,
        dpi=SAVE_DPI,
        bbox_inches="tight",
        facecolor=COLORS["paper"],
    )
    plt.close(fig)



# =============================================================================
# PERIODIC SEARCH-STREAM RECONSTRUCTION
# =============================================================================

SEARCH_SEED_COLORS = [
    "#2563EB",  # blue
    "#0E7490",  # cyan
    "#4F46E5",  # indigo
    "#0F766E",  # teal
    "#64748B",  # slate
    "#B7791F",  # amber
    "#7C3AED",  # violet
    "#15803D",  # green
]

SEARCH_SEED_MARKERS = ["o", "s", "^", "D", "P", "X", "v", ">"]

SEARCH_STREAM_LINESTYLES = {
    0: "-",
    1: (0, (5, 2)),
    2: (0, (1, 1)),
    3: (0, (7, 2, 1, 2)),
}

SEARCH_STREAM_MARKERS = {
    0: "o",
    1: "s",
    2: "^",
    3: "D",
}


def stream_suffix(index: int) -> str:
    if 0 <= index < 26:
        return chr(ord("A") + index)

    return str(index + 1)


def reconstruct_periodic_search_streams(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Recover independent monotonic SA traces hidden under the same seed.

    The solver can log more than one SA trajectory with the same seed. The
    old plot grouped only by seed, so rows from concurrent trajectories were
    connected into one polyline. That produced false late-stage jumps.

    New logs carry an explicit ``stream_id`` from C++ and need no inference.
    Historical logs use a reset/gap-aware fallback.  The fallback uses
    ``itertuples`` instead of ``iterrows`` because archive traces can contain
    hundreds of thousands of records.
    """
    if frame.empty:
        return frame.copy()

    required = {
        "seed",
        "time_s",
        "iter",
        "best_obj",
        "temp",
    }

    missing = required - set(frame.columns)

    if missing:
        raise ValueError(
            "Cannot reconstruct search streams; missing columns: "
            + ", ".join(sorted(missing))
        )

    reconstructed_parts: list[pd.DataFrame] = []
    has_explicit_stream = (
        "stream_id" in frame.columns
        and pd.to_numeric(frame["stream_id"], errors="coerce").gt(0).any()
    )

    for seed, seed_frame in frame.groupby(
        "seed",
        sort=True,
    ):
        seed_frame = seed_frame.sort_values(
            ["time_s", "iter"],
            kind="mergesort",
            na_position="last",
        ).copy()

        if has_explicit_stream:
            explicit = pd.to_numeric(
                seed_frame["stream_id"], errors="coerce"
            ).fillna(0).astype("int64")
            positive_ids = sorted(value for value in explicit.unique() if value > 0)
            index_by_id = {value: index for index, value in enumerate(positive_ids)}
            # Periodic rows produced by v1.9.7 always have a positive id.  Keep
            # malformed/legacy zero rows isolated rather than attaching them to
            # a real trajectory.
            zero_index = len(index_by_id)
            assignments = [index_by_id.get(int(value), zero_index) for value in explicit]
            seed_frame["stream_index"] = assignments
            seed_frame["search_stream"] = [
                f"{int(seed)}-S{int(value)}" if int(value) > 0
                else f"{int(seed)}-legacy-{row_index}"
                for row_index, value in enumerate(explicit)
            ]
            seed_frame["stream_identity"] = "explicit"
        else:
            times = seed_frame["time_s"].to_numpy(dtype=float)
            positive_dt = np.diff(np.unique(times[np.isfinite(times)]))
            positive_dt = positive_dt[positive_dt > 0]
            median_dt = float(np.median(positive_dt)) if positive_dt.size else 0.25
            # A real sampled stream should not disappear for many sample
            # intervals and then resume.  Breaking such gaps prevents later SA
            # phases with reused seeds from being bridged into old traces.
            maximum_gap_s = max(2.0, min(15.0, median_dt * 12.0))
            tracks: list[dict[str, float]] = []
            assignments: list[int] = []

            columns = ["time_s", "iter"]
            if "attempted_moves" in seed_frame.columns:
                columns.append("attempted_moves")
            for row in seed_frame[columns].itertuples(index=False, name=None):
                current_time = float(row[0])
                current_iter = safe_float(row[1])
                current_attempted = safe_float(row[2]) if len(row) > 2 else None
                compatible: list[tuple[float, float, int]] = []
                if current_iter is not None:
                    for track_index, track in enumerate(tracks):
                        attempted_ok = (
                            current_attempted is None
                            or track["last_attempted"] == -math.inf
                            or track["last_attempted"] < current_attempted
                        )
                        if (
                            track["last_iter"] < current_iter
                            and 0.0 <= current_time - track["last_time"] <= maximum_gap_s
                            and attempted_ok
                        ):
                            compatible.append((track["last_iter"], track["last_time"], track_index))
                if compatible:
                    _, _, chosen_track = max(compatible)
                else:
                    chosen_track = len(tracks)
                    tracks.append({
                        "last_iter": -math.inf,
                        "last_time": -math.inf,
                        "last_attempted": -math.inf,
                    })
                if current_iter is not None:
                    tracks[chosen_track]["last_iter"] = current_iter
                if current_attempted is not None:
                    tracks[chosen_track]["last_attempted"] = current_attempted
                tracks[chosen_track]["last_time"] = current_time
                assignments.append(chosen_track)

            seed_frame["stream_index"] = assignments
            seed_frame["search_stream"] = [
                f"{int(seed)}-{stream_suffix(int(index))}"
                for index in assignments
            ]
            seed_frame["stream_identity"] = "legacy_reconstructed"

        reconstructed_parts.append(seed_frame)

    reconstructed = pd.concat(
        reconstructed_parts,
        ignore_index=True,
    )

    reconstructed = reconstructed.sort_values(
        [
            "seed",
            "stream_index",
            "time_s",
            "iter",
        ],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    reconstructed[
        "stream_best_so_far"
    ] = (
        reconstructed
        .groupby(
            "search_stream",
            sort=False,
        )["best_obj"]
        .cummin()
    )

    def first_positive_temperature(
        values: pd.Series,
    ) -> float:
        positive = values[
            pd.to_numeric(
                values,
                errors="coerce",
            )
            > 0
        ]

        if positive.empty:
            return np.nan

        return float(positive.iloc[0])

    reconstructed[
        "stream_initial_temp"
    ] = (
        reconstructed
        .groupby(
            "search_stream",
            sort=False,
        )["temp"]
        .transform(
            first_positive_temperature
        )
    )

    reconstructed[
        "normalized_temp"
    ] = (
        reconstructed["temp"]
        / reconstructed[
            "stream_initial_temp"
        ]
    )

    reconstructed[
        "stream_max_iter"
    ] = (
        reconstructed
        .groupby(
            "search_stream",
            sort=False,
        )["iter"]
        .transform("max")
    )

    reconstructed[
        "iteration_progress_percent"
    ] = (
        reconstructed["iter"]
        / reconstructed[
            "stream_max_iter"
        ]
        * 100.0
    )

    stream_start_time = (
        reconstructed
        .groupby("search_stream", sort=False)["time_s"]
        .transform("min")
    )
    stream_end_time = (
        reconstructed
        .groupby("search_stream", sort=False)["time_s"]
        .transform("max")
    )
    stream_duration = stream_end_time - stream_start_time
    reconstructed["stream_elapsed_s"] = reconstructed["time_s"] - stream_start_time
    reconstructed["time_progress_percent"] = np.where(
        stream_duration > 0,
        reconstructed["stream_elapsed_s"] / stream_duration * 100.0,
        0.0,
    )

    previous_temperature = (
        reconstructed
        .groupby(
            "search_stream",
            sort=False,
        )["temp"]
        .shift(1)
    )

    reconstructed[
        "is_reheat"
    ] = (
        (reconstructed["temp"] > 0)
        & (previous_temperature > 0)
        & (
            reconstructed["temp"]
            > previous_temperature * 1.01
        )
    )

    # Cumulative acceptance is useful as a final worker statistic, but it hides
    # local search behavior and turns counter resets into sharp artifacts.  A
    # reset-safe interval rate is the honest quantity for time-series plots.
    accepted_delta = reconstructed.groupby("search_stream", sort=False)["accepted_moves"].diff()
    attempted_delta = reconstructed.groupby("search_stream", sort=False)["attempted_moves"].diff()
    interval_acceptance = (accepted_delta / attempted_delta).where(attempted_delta > 0)
    reconstructed["interval_acceptance_rate"] = interval_acceptance.clip(0.0, 1.0)
    reconstructed["smoothed_interval_acceptance_rate"] = (
        reconstructed.groupby("search_stream", sort=False)["interval_acceptance_rate"]
        .transform(lambda values: values.rolling(window=5, min_periods=1, center=True).median())
    ).where(reconstructed["interval_acceptance_rate"].notna())

    # Audit monotonicity after reconstruction.
    invalid_streams: list[str] = []

    for stream_name, stream_frame in (
        reconstructed.groupby(
            "search_stream",
            sort=False,
        )
    ):
        ordered = stream_frame.sort_values(
            ["time_s", "iter"],
            kind="mergesort",
            na_position="last",
        )

        valid_iter = ordered[
            "iter"
        ].dropna()

        if (
            not valid_iter.empty
            and not valid_iter.is_monotonic_increasing
        ):
            invalid_streams.append(
                str(stream_name)
            )

    if invalid_streams:
        raise RuntimeError(
            "Search-stream reconstruction produced "
            "non-monotonic iteration traces: "
            + ", ".join(invalid_streams)
        )

    return reconstructed


def build_search_stream_summary(
    periodic_streams: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    if periodic_streams.empty:
        return pd.DataFrame()

    for (
        search_stream,
        group,
    ) in periodic_streams.groupby(
        "search_stream",
        sort=True,
    ):
        group = group.sort_values(
            ["time_s", "iter"],
            kind="mergesort",
            na_position="last",
        )

        best_series = group[
            "stream_best_so_far"
        ]

        best_objective = float(
            best_series.min()
        )

        first_best_rows = group[
            np.isclose(
                best_series,
                best_objective,
            )
        ]

        rows.append(
            {
                "search_stream": (
                    str(search_stream)
                ),
                "seed": int(
                    group["seed"].iloc[0]
                ),
                "stream_index": int(
                    group[
                        "stream_index"
                    ].iloc[0]
                ),
                "rows": int(len(group)),
                "first_iter": safe_float(
                    group["iter"].iloc[0]
                ),
                "max_iter": safe_float(
                    group["iter"].max()
                ),
                "first_time_s": float(
                    group["time_s"].min()
                ),
                "last_time_s": float(
                    group["time_s"].max()
                ),
                "first_best_obj": float(
                    best_series.iloc[0]
                ),
                "best_obj": best_objective,
                "time_to_best_s": float(
                    first_best_rows[
                        "time_s"
                    ].iloc[0]
                ),
                "initial_temperature": (
                    safe_float(
                        group[
                            "stream_initial_temp"
                        ].iloc[0]
                    )
                ),
                "final_positive_temperature": (
                    safe_float(
                        group.loc[
                            group["temp"] > 0,
                            "temp",
                        ].iloc[-1]
                    )
                    if (
                        group["temp"] > 0
                    ).any()
                    else None
                ),
                "minimum_positive_temperature": (
                    safe_float(
                        group.loc[
                            group["temp"] > 0,
                            "temp",
                        ].min()
                    )
                    if (
                        group["temp"] > 0
                    ).any()
                    else None
                ),
                "nonpositive_temperature_rows": int(
                    (group["temp"] <= 0).sum()
                ),
                "reheat_events": int(
                    group["is_reheat"].sum()
                ),
                "final_acceptance_rate": (
                    safe_float(
                        group[
                            "acceptance_rate"
                        ].dropna().iloc[-1]
                    )
                    if group[
                        "acceptance_rate"
                    ].notna().any()
                    else None
                ),
                "max_stagnation": (
                    safe_float(
                        group[
                            "stagnation"
                        ].dropna().max()
                    )
                    if group[
                        "stagnation"
                    ].notna().any()
                    else None
                ),
            }
        )

    summary = pd.DataFrame(rows)

    if summary.empty:
        return summary

    summary["rank"] = (
        summary["best_obj"]
        .rank(
            method="min",
            ascending=True,
        )
        .astype(int)
    )

    return summary.sort_values(
        [
            "seed",
            "stream_index",
        ]
    ).reset_index(drop=True)


def search_seed_color_map(
    periodic_streams: pd.DataFrame,
) -> dict[int, str]:
    seeds = sorted(
        {
            int(seed)
            for seed
            in periodic_streams[
                "seed"
            ].dropna()
        }
    )

    return {
        seed: SEARCH_SEED_COLORS[
            index
            % len(
                SEARCH_SEED_COLORS
            )
        ]
        for index, seed
        in enumerate(seeds)
    }


def add_search_stream_legends(
    ax,
    periodic_streams: pd.DataFrame,
    seed_colors: dict[int, str],
    *,
    seed_location: str = "upper right",
    style_location: str = "lower left",
    observations_only: bool = False,
    seed_markers: dict[int, str] | None = None,
) -> None:
    seeds = sorted(
        seed_colors
    )

    seed_handles = [
        Line2D(
            [0],
            [0],
            color=seed_colors[seed],
            linewidth=0 if observations_only else 2.1,
            marker=(seed_markers or {}).get(seed, "o" if observations_only else None),
            markersize=5.0 if observations_only or seed_markers else 0,
            label=f"seed {seed}",
        )
        for seed in seeds
    ]

    stream_indices = sorted(
        {
            int(index)
            for index
            in periodic_streams[
                "stream_index"
            ].dropna()
        }
    )[:4]
    if len(stream_indices) <= 1:
        stream_indices = []

    style_handles = [
        Line2D(
            [0],
            [0],
            color=COLORS["ink"],
            linewidth=0 if observations_only else 1.8,
            linestyle=(
                "None"
                if observations_only
                else SEARCH_STREAM_LINESTYLES.get(
                    stream_index,
                    "-",
                )
            ),
            marker=SEARCH_STREAM_MARKERS.get(
                stream_index,
                "o",
            ),
            markersize=4.5,
            markevery=[0],
            label=(
                "stream "
                + stream_suffix(
                    stream_index
                )
            ),
        )
        for stream_index
        in stream_indices
    ]

    if seed_handles:
        seed_legend = ax.legend(
            handles=seed_handles,
            loc=seed_location,
            fontsize=7.6,
            ncol=2,
            title="Seed color",
            title_fontsize=8.0,
        )
        ax.add_artist(seed_legend)

    if style_handles:
        ax.legend(
            handles=style_handles,
            loc=style_location,
            fontsize=7.6,
            title="Stream style (sample)",
            title_fontsize=8.0,
        )


def thin_stream_frame(frame: pd.DataFrame, max_points: int = 900) -> pd.DataFrame:
    """Deterministically thin one ordered trace without joining its segments."""
    if len(frame) <= max_points:
        return frame
    positions = np.linspace(0, len(frame) - 1, max_points, dtype=int)
    return frame.iloc[np.unique(positions)]


def contiguous_observation_runs(
    x_values,
    *y_values,
    maximum_gap: float | None = None,
) -> list[np.ndarray]:
    """Return valid adjacent runs without bridging missing/reset samples."""
    x = np.asarray(x_values, dtype=float)
    value_arrays = [np.asarray(values, dtype=float) for values in y_values]
    if any(len(values) != len(x) for values in value_arrays):
        raise ValueError("Observation arrays must have equal lengths")

    valid = np.isfinite(x)
    for values in value_arrays:
        valid &= np.isfinite(values)

    if maximum_gap is None:
        finite_x = x[valid]
        positive_gaps = np.diff(finite_x)
        positive_gaps = positive_gaps[positive_gaps > 0]
        typical_gap = float(np.median(positive_gaps)) if positive_gaps.size else math.inf
        maximum_gap = typical_gap * 3.5

    runs: list[np.ndarray] = []
    current: list[int] = []
    previous_index: int | None = None
    for index in range(len(x)):
        connects = (
            bool(valid[index])
            and previous_index is not None
            and index == previous_index + 1
            and x[index] > x[previous_index]
            and x[index] - x[previous_index] <= maximum_gap + 1e-12
        )
        if not bool(valid[index]):
            if current:
                runs.append(np.asarray(current, dtype=int))
                current = []
            previous_index = None
            continue
        if current and not connects:
            runs.append(np.asarray(current, dtype=int))
            current = []
        current.append(index)
        previous_index = index
    if current:
        runs.append(np.asarray(current, dtype=int))
    return runs


# =============================================================================
# RUN-BUNDLE DISCOVERY
# =============================================================================

RAW_CONVERGENCE_PATTERN = re.compile(
    r"^convergence(?:_.+)?\.csv$",
    flags=re.IGNORECASE,
)


def is_raw_convergence_candidate(path: Path) -> bool:
    if not path.is_file():
        return False

    if not RAW_CONVERGENCE_PATTERN.match(path.name):
        return False

    lowered_parts = {
        part.lower()
        for part in path.parts
    }

    blocked_parts = {
        OUTPUT_DIR_NAME.lower(),
        "csv",
        "solver_analysis_report",
        "convergencereport",
    }

    if lowered_parts & blocked_parts:
        return False

    lowered_name = path.name.lower()

    blocked_tokens = [
        "cleaned",
        "combined",
        "global_best",
        "analysis",
        "report",
    ]

    return not any(token in lowered_name for token in blocked_tokens)


def find_convergence_path() -> Path:
    if EXPLICIT_CONVERGENCE_PATH is not None:
        path = EXPLICIT_CONVERGENCE_PATH.expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"Explicit convergence file was not found: {path}"
            )

        return path

    if EXPLICIT_RUN_DIR is not None:
        run_dir = EXPLICIT_RUN_DIR.expanduser().resolve()

        if not run_dir.exists():
            raise FileNotFoundError(
                f"Explicit run directory was not found: {run_dir}"
            )

        candidates = [
            path
            for path in run_dir.glob("convergence*.csv")
            if is_raw_convergence_candidate(path)
        ]
    else:
        candidates: list[Path] = []

        for root in SEARCH_ROOTS:
            if not root.exists():
                continue

            try:
                for path in root.rglob("convergence*.csv"):
                    if is_raw_convergence_candidate(path):
                        candidates.append(path.resolve())
            except (OSError, PermissionError):
                continue

    candidates = list(dict.fromkeys(candidates))

    if not candidates:
        raise FileNotFoundError(
            "No raw convergence CSV was found. Expected convergence.csv "
            "or convergence_<run-tag>.csv."
        )

    candidates.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    print("Raw convergence candidates:")

    for index, path in enumerate(candidates[:10]):
        print(
            f"  {index}: {path} "
            f"[modified={path.stat().st_mtime:.0f}]"
        )

    chosen = candidates[0]

    print(f"\nUsing convergence file:\n  {chosen}\n")

    return chosen


def extract_run_suffix(convergence_path: Path) -> str:
    stem = convergence_path.stem

    if stem == "convergence":
        return ""

    if stem.startswith("convergence_"):
        return stem[len("convergence_"):]

    return ""


def find_companion_file(
    directory: Path,
    prefix: str,
    suffix: str,
    extension: str,
) -> Path | None:
    exact_candidates = []

    if suffix:
        exact_candidates.append(
            directory / f"{prefix}_{suffix}{extension}"
        )

    exact_candidates.append(
        directory / f"{prefix}{extension}"
    )

    for candidate in exact_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    wildcard_candidates = [
        path.resolve()
        for path in directory.glob(f"{prefix}*{extension}")
        if path.is_file()
    ]

    if not wildcard_candidates:
        return None

    wildcard_candidates.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return wildcard_candidates[0]


def discover_run_bundle() -> dict[str, Path | None]:
    convergence_path = find_convergence_path()
    directory = convergence_path.parent.resolve()
    suffix = extract_run_suffix(convergence_path)

    return {
        "run_directory": directory,
        "convergence": convergence_path,
        "run_summary": find_companion_file(
            directory,
            "run_summary",
            suffix,
            ".csv",
        ),
        "solver_output": find_companion_file(
            directory,
            "solver_output",
            suffix,
            ".txt",
        ),
        "colab_output": find_companion_file(
            directory,
            "colab_output",
            suffix,
            ".txt",
        ),
        "config": find_companion_file(
            directory,
            "config",
            suffix,
            ".txt",
        ),
    }


# =============================================================================
# CONVERGENCE CSV LOADING
# =============================================================================

def load_convergence(path: Path) -> tuple[pd.DataFrame, bool]:
    frame = pd.read_csv(path)

    if frame.empty:
        raise ValueError(f"{path.name} exists but is empty.")

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]

    required_basic = {
        "time_s",
        "seed",
        "best_obj",
    }

    if not required_basic.issubset(frame.columns):
        raise ValueError(
            "Unknown convergence format.\n"
            f"Found columns: {list(frame.columns)}\n"
            f"Required columns: {sorted(required_basic)}"
        )

    expanded_columns = {
        "iter",
        "current_obj",
        "temp",
        "accepted_moves",
        "attempted_moves",
        "acceptance_rate",
        "stagnation",
        "event",
    }

    is_expanded = expanded_columns.issubset(frame.columns)

    numeric_columns = [
        "time_s",
        "seed",
        "best_obj",
        "global_best_obj",
        "iter",
        "current_obj",
        "temp",
        "accepted_moves",
        "attempted_moves",
        "acceptance_rate",
        "stagnation",
        "stream_id",
    ]

    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            )

    if "iter" not in frame.columns:
        frame["iter"] = np.nan

    if "current_obj" not in frame.columns:
        frame["current_obj"] = frame["best_obj"]

    if "temp" not in frame.columns:
        frame["temp"] = np.nan

    if "accepted_moves" not in frame.columns:
        frame["accepted_moves"] = np.nan

    if "attempted_moves" not in frame.columns:
        frame["attempted_moves"] = np.nan

    if "acceptance_rate" not in frame.columns:
        frame["acceptance_rate"] = np.nan

    if "stagnation" not in frame.columns:
        frame["stagnation"] = np.nan

    if "event" not in frame.columns:
        frame["event"] = "checkpoint"

    frame["event"] = (
        frame["event"]
        .fillna("unknown")
        .astype(str)
        .str.strip()
    )

    frame = frame.dropna(
        subset=[
            "time_s",
            "seed",
            "best_obj",
        ]
    ).copy()

    frame = frame[
        (frame["time_s"] >= 0)
        & (frame["best_obj"] > 0)
    ].copy()

    if frame.empty:
        raise ValueError(
            "No valid convergence rows remained after numeric cleaning."
        )

    frame["seed"] = frame["seed"].astype(int)

    duplicate_identity = [
        "time_s", "seed", "iter", "best_obj", "event",
    ]
    if "stream_id" in frame.columns:
        duplicate_identity.insert(2, "stream_id")

    frame = (
        frame
        .sort_values(
            ["time_s", "seed", "iter"],
            kind="mergesort",
            na_position="last",
        )
        .drop_duplicates(
            subset=duplicate_identity,
            keep="last",
        )
        .reset_index(drop=True)
    )

    frame["seed_best_so_far"] = (
        frame
        .groupby("seed", sort=False)["best_obj"]
        .cummin()
    )
    # v1.9.5 writes the process-global best explicitly. Historical files only
    # contain worker-local best_obj, so derive the same monotone contract.
    if "global_best_obj" in frame.columns:
        frame["process_global_best"] = pd.to_numeric(frame["global_best_obj"], errors="coerce").ffill().cummin()
    else:
        frame["process_global_best"] = frame["best_obj"].cummin()

    return frame, is_expanded


# =============================================================================
# SOLVER / COLAB OUTPUT PARSING
# =============================================================================

NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def read_optional_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def parse_algorithm_comparison(text: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    pattern = re.compile(
        rf"^\s*"
        r"([A-Za-z][A-Za-z0-9_+\-]*)"
        rf"\s+({NUMBER_PATTERN})"
        rf"\s+({NUMBER_PATTERN})"
        rf"\s+({NUMBER_PATTERN})"
        rf"\s+({NUMBER_PATTERN})\s*$",
        flags=re.MULTILINE,
    )

    allowed_names = {
        "Savings",
        "Greedy",
        "SA_no_cross",
        "SA_full",
        "Final",
        "ALNS",
        "HGS",
        "HGS_lite",
        "Cluster",
    }

    for match in pattern.finditer(text):
        name = match.group(1)

        if name not in allowed_names:
            continue

        rows.append(
            {
                "algorithm": name,
                "objective": float(match.group(2)),
                "distance_m": float(match.group(3)),
                "co2_g": float(match.group(4)),
                "time_s": float(match.group(5)),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "algorithm",
                "objective",
                "distance_m",
                "co2_g",
                "time_s",
            ]
        )

    return (
        pd.DataFrame(rows)
        .drop_duplicates(
            subset=[
                "algorithm",
                "objective",
                "time_s",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )


def parse_anytime_improvements(
    text: str,
    source: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    pattern = re.compile(
        rf"\[Anytime\]\s+meaningful\s+best\s+"
        rf"({NUMBER_PATTERN})\s*->\s*({NUMBER_PATTERN})"
        rf".*?\belapsed=({NUMBER_PATTERN})s",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        rows.append(
            {
                "time_s": float(match.group(3)),
                "objective": float(match.group(2)),
                "raw_previous_objective": float(match.group(1)),
                "source": source,
                "event": "anytime_meaningful_improvement",
                "seed": np.nan,
            }
        )

    return pd.DataFrame(rows)


def parse_initial_candidates(
    text: str,
    algorithm_table: pd.DataFrame,
    source: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    if not algorithm_table.empty:
        for _, row in algorithm_table.iterrows():
            if str(row["algorithm"]) not in {
                "Savings",
                "Greedy",
            }:
                continue

            rows.append(
                {
                    "time_s": max(0.0, float(row["time_s"])),
                    "objective": float(row["objective"]),
                    "source": source,
                    "event": (
                        f"{str(row['algorithm']).lower()}_checkpoint"
                    ),
                    "seed": np.nan,
                }
            )

    patterns = [
        (
            "savings_warm_start",
            re.compile(
                rf"savings\s+warm\s+start.*?\bobj=({NUMBER_PATTERN})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "initial_best",
            re.compile(
                rf"\binitial\s+(?:global\s+)?best\s*[:=]\s*"
                rf"({NUMBER_PATTERN})",
                flags=re.IGNORECASE,
            ),
        ),
    ]

    for event_name, pattern in patterns:
        for match in pattern.finditer(text):
            rows.append(
                {
                    "time_s": 0.0,
                    "objective": float(match.group(1)),
                    "source": source,
                    "event": event_name,
                    "seed": np.nan,
                }
            )

    return pd.DataFrame(rows)


def parse_explicit_reference(text: str) -> tuple[float | None, str | None]:
    patterns = [
        (
            "BKS",
            re.compile(
                rf"\bBKS\b\s*(?:[:=]|is)\s*({NUMBER_PATTERN})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "Best-known solution",
            re.compile(
                rf"\bbest[-\s]?known(?:\s+solution)?\b"
                rf"\s*(?:[:=]|is)\s*({NUMBER_PATTERN})",
                flags=re.IGNORECASE,
            ),
        ),
    ]

    for label, pattern in patterns:
        match = pattern.search(text)

        if match:
            value = safe_float(match.group(1))

            if value is not None and value > 0:
                return value, label

    return None, None


def parse_solver_metadata(
    solver_text: str,
    colab_text: str,
) -> tuple[
    dict[str, Any],
    pd.DataFrame,
    pd.DataFrame,
]:
    combined_text = "\n".join(
        text
        for text in [
            solver_text,
            colab_text,
        ]
        if text
    )

    algorithm_table = parse_algorithm_comparison(
        combined_text
    )

    metadata: dict[str, Any] = {
        "objective_mode": None,
        "best_algorithm": None,
        "final_feasible": None,
        "pipeline_runtime_s": None,
        "final_objective": None,
        "final_time_s": None,
        "final_distance_m": None,
        "explicit_reference_objective": None,
        "explicit_reference_label": None,
    }

    match = re.search(
        r"Objective\s+mode\s*:\s*([A-Za-z0-9_+\-]+)",
        combined_text,
        flags=re.IGNORECASE,
    )
    if match:
        metadata["objective_mode"] = match.group(1).strip()

    match = re.search(
        r"Best\s+algorithm\s*:\s*(.+)",
        combined_text,
        flags=re.IGNORECASE,
    )
    if match:
        metadata["best_algorithm"] = match.group(1).strip()

    match = re.search(
        r"Final\s+solution\s+feasible\s*:\s*(YES|NO)",
        combined_text,
        flags=re.IGNORECASE,
    )
    if match:
        metadata["final_feasible"] = match.group(1).upper()

    runtime_patterns = [
        re.compile(
            rf"Pipeline\s+runtime\s*:\s*({NUMBER_PATTERN})\s*s",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\brun\s+time\s*:\s*({NUMBER_PATTERN})\s*s",
            flags=re.IGNORECASE,
        ),
    ]

    for pattern in runtime_patterns:
        matches = list(pattern.finditer(combined_text))

        if matches:
            metadata["pipeline_runtime_s"] = float(
                matches[-1].group(1)
            )
            break

    if not algorithm_table.empty:
        final_rows = algorithm_table[
            algorithm_table["algorithm"].eq("Final")
        ]

        if not final_rows.empty:
            final_row = final_rows.iloc[-1]

            metadata["final_objective"] = float(
                final_row["objective"]
            )
            metadata["final_time_s"] = float(
                final_row["time_s"]
            )
            metadata["final_distance_m"] = float(
                final_row["distance_m"]
            )

    explicit_patterns = [
        re.compile(
            rf"\bglobal\s+best(?:\s+objective)?\s*[:=]\s*"
            rf"({NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\bfinal\s+objective\s*[:=]\s*"
            rf"({NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        ),
    ]

    if metadata["final_objective"] is None:
        for pattern in explicit_patterns:
            matches = list(pattern.finditer(combined_text))

            if matches:
                metadata["final_objective"] = float(
                    matches[-1].group(1)
                )
                break

    if metadata["final_time_s"] is None:
        metadata["final_time_s"] = (
            metadata["pipeline_runtime_s"]
        )

    reference_value, reference_label = (
        parse_explicit_reference(combined_text)
    )

    metadata["explicit_reference_objective"] = (
        reference_value
    )
    metadata["explicit_reference_label"] = (
        reference_label
    )

    anytime_frames = []

    if solver_text:
        anytime_frames.append(
            parse_anytime_improvements(
                solver_text,
                "solver_output",
            )
        )

    if colab_text:
        anytime_frames.append(
            parse_anytime_improvements(
                colab_text,
                "colab_output",
            )
        )

    anytime_frames = [
        frame
        for frame in anytime_frames
        if not frame.empty
    ]

    if anytime_frames:
        anytime = (
            pd.concat(
                anytime_frames,
                ignore_index=True,
            )
            .drop_duplicates(
                subset=[
                    "time_s",
                    "objective",
                ],
                keep="first",
            )
            .sort_values("time_s")
            .reset_index(drop=True)
        )
    else:
        anytime = pd.DataFrame(
            columns=[
                "time_s",
                "objective",
                "source",
                "event",
                "seed",
            ]
        )

    initial_frames = []

    if solver_text:
        initial_frames.append(
            parse_initial_candidates(
                solver_text,
                algorithm_table,
                "solver_output",
            )
        )

    if colab_text:
        initial_frames.append(
            parse_initial_candidates(
                colab_text,
                algorithm_table,
                "colab_output",
            )
        )

    initial_frames = [
        frame
        for frame in initial_frames
        if not frame.empty
    ]

    if initial_frames:
        initial_candidates = (
            pd.concat(
                initial_frames,
                ignore_index=True,
            )
            .drop_duplicates(
                subset=[
                    "time_s",
                    "objective",
                    "event",
                ],
                keep="first",
            )
            .reset_index(drop=True)
        )
    else:
        initial_candidates = pd.DataFrame(
            columns=[
                "time_s",
                "objective",
                "source",
                "event",
                "seed",
            ]
        )

    combined_columns = list(
        dict.fromkeys(
            [
                *initial_candidates.columns,
                *anytime.columns,
            ]
        )
    )
    combined_frames = [
        frame.dropna(axis=1, how="all")
        for frame in [initial_candidates, anytime]
        if not frame.empty
    ]
    combined_candidates = (
        pd.concat(combined_frames, ignore_index=True)
        if combined_frames else pd.DataFrame()
    ).reindex(columns=combined_columns)
    return metadata, algorithm_table, combined_candidates


# =============================================================================
# RUN-SUMMARY SELECTION
# =============================================================================

def load_run_summary(
    path: Path | None,
) -> pd.DataFrame | None:
    if path is None or not path.exists():
        return None

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        print(
            f"WARNING: could not read {path.name}: {exc}"
        )
        return None

    if frame.empty:
        return None

    frame.columns = [
        str(column).strip()
        for column in frame.columns
    ]

    return frame


def select_run_summary_row(
    frame: pd.DataFrame | None,
    solver_metadata: dict[str, Any],
) -> tuple[pd.Series | None, int | None]:
    if frame is None or frame.empty:
        return None, None

    working = frame.copy()

    for column in [
        "objective",
        "distance_m",
        "runtime_s",
        "seed",
    ]:
        if column in working.columns:
            working[column] = pd.to_numeric(
                working[column],
                errors="coerce",
            )

    final_objective = safe_float(
        solver_metadata.get("final_objective")
    )
    final_runtime = safe_float(
        solver_metadata.get("final_time_s")
    )

    scores = pd.Series(
        np.zeros(len(working), dtype=float),
        index=working.index,
    )

    if final_objective is not None and "objective" in working.columns:
        scale = max(abs(final_objective), 1.0)
        scores += (
            (working["objective"] - final_objective)
            .abs()
            .fillna(scale * 1000)
            / scale
        )

    if final_runtime is not None and "runtime_s" in working.columns:
        scale = max(abs(final_runtime), 1.0)
        scores += 0.20 * (
            (working["runtime_s"] - final_runtime)
            .abs()
            .fillna(scale * 1000)
            / scale
        )

    if (
        final_objective is None
        and final_runtime is None
    ):
        selected_index = working.index[-1]
    else:
        selected_index = scores.idxmin()

    return working.loc[selected_index], int(selected_index)


def complete_solver_metadata_from_summary(
    metadata: dict[str, Any],
    selected_row: pd.Series | None,
) -> dict[str, Any]:
    result = dict(metadata)

    if selected_row is None:
        return result

    if result.get("final_objective") is None:
        result["final_objective"] = safe_float(
            selected_row.get("objective")
        )

    if result.get("final_distance_m") is None:
        result["final_distance_m"] = safe_float(
            selected_row.get("distance_m")
        )

    if result.get("final_time_s") is None:
        result["final_time_s"] = safe_float(
            selected_row.get("runtime_s")
        )

    if result.get("pipeline_runtime_s") is None:
        result["pipeline_runtime_s"] = safe_float(
            selected_row.get("runtime_s")
        )

    if result.get("objective_mode") is None:
        mode = selected_row.get("objective_mode")

        if pd.notna(mode):
            result["objective_mode"] = str(mode)

    if result.get("final_feasible") is None:
        feasible = selected_row.get("feasible")

        if pd.notna(feasible):
            text = str(feasible).strip().upper()

            if text in {
                "1",
                "TRUE",
                "YES",
            }:
                result["final_feasible"] = "YES"
            elif text in {
                "0",
                "FALSE",
                "NO",
            }:
                result["final_feasible"] = "NO"

    return result


# =============================================================================
# GLOBAL-BEST CURVE CONSTRUCTION
# =============================================================================

def construct_global_curve(
    convergence: pd.DataFrame,
    parsed_log_points: pd.DataFrame,
    solver_metadata: dict[str, Any],
    selected_summary_row: pd.Series | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    convergence_points = pd.DataFrame(
        {
            "time_s": convergence["time_s"],
            "objective": convergence.get("process_global_best", convergence["best_obj"]),
            "source": "convergence_csv",
            "event": convergence["event"],
            "seed": convergence["seed"],
        }
    )

    frames = [
        convergence_points,
    ]

    if not parsed_log_points.empty:
        frames.append(
            parsed_log_points[
                [
                    "time_s",
                    "objective",
                    "source",
                    "event",
                    "seed",
                ]
            ].copy()
        )

    final_objective = safe_float(
        solver_metadata.get("final_objective")
    )
    final_time = safe_float(
        solver_metadata.get("final_time_s")
    )

    if final_objective is None and selected_summary_row is not None:
        final_objective = safe_float(
            selected_summary_row.get("objective")
        )

    if final_time is None and selected_summary_row is not None:
        final_time = safe_float(
            selected_summary_row.get("runtime_s")
        )

    if final_objective is not None:
        if final_time is None:
            final_time = float(
                convergence["time_s"].max()
            )

        frames.append(
            pd.DataFrame(
                [
                    {
                        "time_s": max(0.0, final_time),
                        "objective": final_objective,
                        "source": "solver_final",
                        "event": "final_solution",
                        "seed": np.nan,
                    }
                ]
            )
        )

    all_points = pd.concat(
        frames,
        ignore_index=True,
    )

    all_points["time_s"] = pd.to_numeric(
        all_points["time_s"],
        errors="coerce",
    )
    all_points["objective"] = pd.to_numeric(
        all_points["objective"],
        errors="coerce",
    )

    all_points = all_points.dropna(
        subset=[
            "time_s",
            "objective",
        ]
    )

    all_points = all_points[
        (all_points["time_s"] >= 0)
        & (all_points["objective"] > 0)
    ].copy()

    source_priority = {
        "solver_final": 0,
        "colab_output": 1,
        "solver_output": 2,
        "convergence_csv": 3,
    }

    all_points["source_priority"] = (
        all_points["source"]
        .map(source_priority)
        .fillna(9)
    )

    all_points = (
        all_points
        .sort_values(
            [
                "time_s",
                "source_priority",
                "objective",
            ],
            kind="mergesort",
        )
        .drop_duplicates(
            subset=[
                "time_s",
                "objective",
                "source",
                "event",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    all_points["global_best"] = (
        all_points["objective"].cummin()
    )

    all_points["is_improvement"] = (
        all_points["global_best"]
        .diff()
        .fillna(-1)
        < 0
    )

    # Keep every actual global improvement plus the final runtime endpoint.
    curve = all_points[
        all_points["is_improvement"]
    ].copy()

    final_source_rows = all_points[
        all_points["source"].eq("solver_final")
    ]

    if not final_source_rows.empty:
        final_endpoint = final_source_rows.iloc[[-1]].copy()

        if curve.empty or not (
            np.isclose(
                curve.iloc[-1]["time_s"],
                final_endpoint.iloc[0]["time_s"],
            )
            and np.isclose(
                curve.iloc[-1]["global_best"],
                final_endpoint.iloc[0]["global_best"],
            )
        ):
            curve = pd.concat(
                [
                    curve,
                    final_endpoint,
                ],
                ignore_index=True,
            )

    curve = (
        curve
        .sort_values(
            [
                "time_s",
                "source_priority",
            ],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    curve["global_best"] = (
        curve["objective"].cummin()
    )

    first_best = float(
        curve["global_best"].iloc[0]
    )
    final_best = float(
        curve["global_best"].min()
    )

    curve["improvement_percent"] = (
        (
            first_best
            - curve["global_best"]
        )
        / first_best
        * 100.0
        if first_best != 0
        else 0.0
    )

    curve["gap_to_final_percent"] = (
        (
            curve["global_best"]
            - final_best
        )
        / final_best
        * 100.0
        if final_best != 0
        else 0.0
    )

    return all_points, curve


# =============================================================================
# WORKER AND RUN SUMMARIES
# =============================================================================

def build_worker_summary(
    convergence: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for seed, group in convergence.groupby("seed"):
        group = group.sort_values(
            [
                "time_s",
                "iter",
            ],
            kind="mergesort",
            na_position="last",
        )

        seed_best = group["best_obj"].cummin()
        best_objective = float(seed_best.min())

        first_best_index = seed_best[
            np.isclose(
                seed_best,
                best_objective,
            )
        ].index[0]

        first_objective = float(
            seed_best.iloc[0]
        )
        final_objective = float(
            seed_best.iloc[-1]
        )

        rows.append(
            {
                "seed": int(seed),
                "first_best_obj": first_objective,
                "final_best_obj": final_objective,
                "best_obj": best_objective,
                "time_to_best_s": float(
                    convergence.loc[
                        first_best_index,
                        "time_s",
                    ]
                ),
                "last_logged_time_s": float(
                    group["time_s"].max()
                ),
                "improvement_percent": (
                    (
                        first_objective
                        - final_objective
                    )
                    / first_objective
                    * 100.0
                    if first_objective != 0
                    else 0.0
                ),
                "log_rows": int(len(group)),
                "last_iter": (
                    float(group["iter"].dropna().max())
                    if group["iter"].notna().any()
                    else np.nan
                ),
                "final_acceptance_rate": (
                    float(
                        group[
                            "acceptance_rate"
                        ].dropna().iloc[-1]
                    )
                    if group[
                        "acceptance_rate"
                    ].notna().any()
                    else np.nan
                ),
                "max_stagnation": (
                    float(
                        group[
                            "stagnation"
                        ].dropna().max()
                    )
                    if group[
                        "stagnation"
                    ].notna().any()
                    else np.nan
                ),
            }
        )

    worker_summary = pd.DataFrame(rows)

    if worker_summary.empty:
        return worker_summary

    worker_summary["rank"] = (
        worker_summary["best_obj"]
        .rank(
            method="min",
            ascending=True,
        )
        .astype(int)
    )

    best_worker = float(
        worker_summary["best_obj"].min()
    )

    worker_summary["gap_to_best_worker_percent"] = (
        (
            worker_summary["best_obj"]
            - best_worker
        )
        / best_worker
        * 100.0
        if best_worker != 0
        else 0.0
    )

    return worker_summary.sort_values(
        [
            "rank",
            "seed",
        ]
    ).reset_index(drop=True)


def calculate_safe_zoom(
    curve: pd.DataFrame,
    reference_objective: float | None,
) -> dict[str, float]:
    times = curve["time_s"].to_numpy(dtype=float)
    values = curve["global_best"].to_numpy(dtype=float)

    final_value = float(np.min(values))
    initial_value = float(values[0])
    final_time = float(np.max(times))

    total_improvement = max(
        initial_value - final_value,
        0.0,
    )

    if total_improvement > 0:
        objective_threshold = (
            final_value
            + ZOOM_IMPROVEMENT_FRACTION
            * total_improvement
        )

        eligible = np.where(
            values <= objective_threshold
        )[0]

        if eligible.size:
            start_index = int(eligible[0])
        else:
            start_index = max(
                0,
                len(values) - 10,
            )
    else:
        start_index = max(
            0,
            len(values) - 10,
        )

    minimum_time = (
        ZOOM_MIN_TIME_FRACTION
        * final_time
    )

    time_eligible = np.where(
        times >= minimum_time
    )[0]

    if time_eligible.size:
        start_index = max(
            start_index,
            int(time_eligible[0]),
        )

    zoom_times = times[start_index:]
    zoom_values = values[start_index:]

    if zoom_times.size == 0:
        zoom_times = times
        zoom_values = values

    y_candidates = list(
        zoom_values[
            np.isfinite(zoom_values)
        ]
    )

    if (
        reference_objective is not None
        and math.isfinite(reference_objective)
    ):
        y_candidates.append(
            float(reference_objective)
        )

    y_min_data = min(y_candidates)
    y_max_data = max(y_candidates)
    y_span = y_max_data - y_min_data

    minimum_margin = max(
        abs(final_value) * 0.006,
        1.0,
    )

    margin = max(
        y_span * 0.10,
        minimum_margin,
    )

    y_lower = max(
        0.0,
        y_min_data - margin,
    )
    y_upper = y_max_data + margin

    if not math.isfinite(y_lower):
        y_lower = max(
            0.0,
            final_value * 0.98,
        )

    if not math.isfinite(y_upper):
        y_upper = final_value * 1.02

    if y_upper <= y_lower:
        y_upper = y_lower + max(
            abs(final_value) * 0.02,
            1.0,
        )

    x_lower = max(
        0.0,
        float(zoom_times[0]),
    )
    x_upper = max(
        final_time,
        x_lower + 1e-6,
    )

    return {
        "x_lower": x_lower,
        "x_upper": x_upper,
        "y_lower": y_lower,
        "y_upper": y_upper,
        "start_index": float(start_index),
    }


# =============================================================================
# ANALYSIS WORKFLOW
# =============================================================================

bundle = discover_run_bundle()
run_directory = bundle["run_directory"]

if not isinstance(run_directory, Path):
    raise RuntimeError(
        "Could not determine the run directory."
    )

output_directory = (
    run_directory / OUTPUT_DIR_NAME
)
png_directory = output_directory / "PNG"
csv_directory = output_directory / "CSV"
json_directory = output_directory / "JSON"

reset_directory(output_directory)

for directory in [
    png_directory,
    csv_directory,
    json_directory,
]:
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

print("Run bundle:")

for key, value in bundle.items():
    print(f"  {key}: {value}")

convergence, is_expanded_format = load_convergence(
    bundle["convergence"]
)

solver_text = read_optional_text(
    bundle["solver_output"]
)
colab_text = read_optional_text(
    bundle["colab_output"]
)

solver_metadata, algorithm_comparison, parsed_log_points = (
    parse_solver_metadata(
        solver_text,
        colab_text,
    )
)

run_summary = load_run_summary(
    bundle["run_summary"]
)

selected_summary_row, selected_summary_index = (
    select_run_summary_row(
        run_summary,
        solver_metadata,
    )
)

solver_metadata = complete_solver_metadata_from_summary(
    solver_metadata,
    selected_summary_row,
)

all_global_points, global_curve = construct_global_curve(
    convergence,
    parsed_log_points,
    solver_metadata,
    selected_summary_row,
)

worker_summary = build_worker_summary(
    convergence
)

# Legitimate reference selection:
# manual reference > explicitly printed BKS > no reference.
if REFERENCE_OBJECTIVE is not None:
    reference_objective = float(
        REFERENCE_OBJECTIVE
    )
    reference_label = REFERENCE_LABEL
elif (
    solver_metadata.get(
        "explicit_reference_objective"
    )
    is not None
):
    reference_objective = float(
        solver_metadata[
            "explicit_reference_objective"
        ]
    )
    reference_label = str(
        solver_metadata.get(
            "explicit_reference_label"
        )
        or REFERENCE_LABEL
    )
else:
    reference_objective = None
    reference_label = None

first_global_objective = float(
    global_curve["global_best"].iloc[0]
)
final_global_objective = float(
    global_curve["global_best"].min()
)
final_runtime_s = float(
    global_curve["time_s"].max()
)

best_rows = global_curve[
    np.isclose(
        global_curve["global_best"],
        final_global_objective,
    )
]

time_to_global_best_s = float(
    best_rows["time_s"].min()
)

objective_mode = (
    solver_metadata.get("objective_mode")
    or (
        str(
            selected_summary_row.get(
                "objective_mode"
            )
        )
        if selected_summary_row is not None
        and pd.notna(
            selected_summary_row.get(
                "objective_mode"
            )
        )
        else "unknown"
    )
)

overall_improvement_percent = (
    (
        first_global_objective
        - final_global_objective
    )
    / first_global_objective
    * 100.0
    if first_global_objective != 0
    else 0.0
)

reference_gap_percent = None

if (
    reference_objective is not None
    and reference_objective != 0
):
    reference_gap_percent = (
        (
            final_global_objective
            - reference_objective
        )
        / reference_objective
        * 100.0
    )

analysis_summary = {
    "convergence_format": (
        "expanded"
        if is_expanded_format
        else "basic"
    ),
    "objective_mode": objective_mode,
    "raw_convergence_rows": int(
        len(convergence)
    ),
    "worker_count": int(
        convergence["seed"].nunique()
    ),
    "parsed_anytime_or_initial_points": int(
        len(parsed_log_points)
    ),
    "combined_global_points": int(
        len(all_global_points)
    ),
    "global_curve_points": int(
        len(global_curve)
    ),
    "first_global_objective": (
        first_global_objective
    ),
    "final_global_objective": (
        final_global_objective
    ),
    "overall_improvement_percent": (
        overall_improvement_percent
    ),
    "time_to_global_best_s": (
        time_to_global_best_s
    ),
    "final_runtime_s": final_runtime_s,
    "solver_final_objective": (
        solver_metadata.get(
            "final_objective"
        )
    ),
    "solver_final_time_s": (
        solver_metadata.get(
            "final_time_s"
        )
    ),
    "solver_best_algorithm": (
        solver_metadata.get(
            "best_algorithm"
        )
    ),
    "solver_final_feasible": (
        solver_metadata.get(
            "final_feasible"
        )
    ),
    "selected_run_summary_index": (
        selected_summary_index
    ),
    "reference_objective": (
        reference_objective
    ),
    "reference_label": reference_label,
    "gap_to_reference_percent": (
        reference_gap_percent
    ),
    "font": PRESENTATION_FONT,
}

# Save clean data before plotting.
convergence.to_csv(
    csv_directory / "ConvergenceAllEvents.csv",
    index=False,
)

periodic_convergence = convergence[
    convergence["event"]
    .str.lower()
    .eq("periodic")
].copy()

if periodic_convergence.empty:
    periodic_convergence = convergence.copy()

periodic_convergence = (
    reconstruct_periodic_search_streams(
        periodic_convergence
    )
)

search_stream_summary = (
    build_search_stream_summary(
        periodic_convergence
    )
)

search_seed_colors = (
    search_seed_color_map(
        periodic_convergence
    )
)
search_seed_markers = {
    seed: SEARCH_SEED_MARKERS[index % len(SEARCH_SEED_MARKERS)]
    for index, seed in enumerate(sorted(search_seed_colors))
}

periodic_convergence.to_csv(
    csv_directory
    / "ConvergencePeriodicStreams.csv",
    index=False,
)

# Compatibility copy, now with reconstructed stream columns included.
periodic_convergence.to_csv(
    csv_directory
    / "ConvergencePeriodic.csv",
    index=False,
)

search_stream_summary.to_csv(
    csv_directory
    / "SearchStreamSummary.csv",
    index=False,
)

analysis_summary[
    "seed_label_count"
] = int(
    periodic_convergence[
        "seed"
    ].nunique()
)

analysis_summary[
    "reconstructed_search_stream_count"
] = int(
    periodic_convergence[
        "search_stream"
    ].nunique()
)

analysis_summary[
    "duplicate_iteration_excess"
] = int(
    len(periodic_convergence)
    - len(
        periodic_convergence.drop_duplicates(
            subset=[
                "seed",
                "iter",
            ],
            keep="first",
        )
    )
)

analysis_summary[
    "stream_reconstruction_method"
] = (
    "explicit C++ stream_id"
    if (
        "stream_identity" in periodic_convergence.columns
        and periodic_convergence["stream_identity"].eq("explicit").all()
    )
    else "reset/gap-aware monotonic reconstruction for historical logs"
)

analysis_summary[
    "temperature_reheat_events"
] = int(
    periodic_convergence[
        "is_reheat"
    ].sum()
)

analysis_summary[
    "nonpositive_temperature_rows"
] = int(
    (
        periodic_convergence[
            "temp"
        ]
        <= 0
    ).sum()
)

all_global_points.to_csv(
    csv_directory / "GlobalPointsCombined.csv",
    index=False,
)

global_curve.to_csv(
    csv_directory / "GlobalBestCurve.csv",
    index=False,
)

worker_summary.to_csv(
    csv_directory / "WorkerSummary.csv",
    index=False,
)

algorithm_comparison.to_csv(
    csv_directory / "AlgorithmComparison.csv",
    index=False,
)

parsed_log_points.to_csv(
    csv_directory / "ParsedLogImprovements.csv",
    index=False,
)

if run_summary is not None:
    run_summary.to_csv(
        csv_directory / "RunSummaryAllRows.csv",
        index=False,
    )

if selected_summary_row is not None:
    pd.DataFrame(
        [selected_summary_row.to_dict()]
    ).to_csv(
        csv_directory / "RunSummarySelectedRow.csv",
        index=False,
    )

write_json(
    json_directory / "AnalysisSummary.json",
    analysis_summary,
)

write_json(
    json_directory / "ParsedSolverOutput.json",
    solver_metadata,
)

source_manifest = {
    key: source_file_receipt(value)
    for key, value in bundle.items()
}

write_json(
    json_directory / "SourceManifest.json",
    source_manifest,
)


# =============================================================================
# PLOT 1 — CHAPTER 7 PUBLICATION CONVERGENCE
# =============================================================================

saved_figures: list[Path] = []

fig, ax = plt.subplots(
    figsize=(12.4, 7.1)
)

# Internal workers are contextual evidence, not the headline.
worker_palette = [
    COLORS["blue"],
    COLORS["cyan"],
    COLORS["light_slate"],
    "#4F46E5",
    "#15803D",
    "#7C3AED",
]

for index, (seed, group) in enumerate(
    convergence.groupby("seed")
):
    group = group.sort_values(
        [
            "time_s",
            "iter",
        ],
        kind="mergesort",
        na_position="last",
    )

    ax.step(
        group["time_s"],
        group["seed_best_so_far"],
        where="post",
        linewidth=0.75,
        alpha=0.18,
        color=worker_palette[
            index % len(worker_palette)
        ],
        rasterized=True,
    )

ax.step(
    global_curve["time_s"],
    global_curve["global_best"],
    where="post",
    linewidth=2.8,
    color=COLORS["teal"],
    label="Global best-so-far",
    zorder=5,
)

final_point = global_curve.iloc[-1]

ax.scatter(
    [float(final_point["time_s"])],
    [float(final_point["global_best"])],
    s=58,
    facecolor=COLORS["navy"],
    edgecolor="white",
    linewidth=0.9,
    zorder=7,
    label="Final solver result",
)

if reference_objective is not None:
    ax.axhline(
        reference_objective,
        color=COLORS["amber"],
        linestyle=(0, (6, 4)),
        linewidth=1.55,
        label=(
            f"{reference_label}: "
            f"{reference_objective:,.3f}"
        ),
    )

ax.annotate(
    (
        f"{final_global_objective:,.3f}\n"
        f"t = {time_to_global_best_s:.2f} s"
    ),
    xy=(
        time_to_global_best_s,
        final_global_objective,
    ),
    xytext=(12, 18),
    textcoords="offset points",
    fontsize=8.7,
    color=COLORS["navy"],
    arrowprops={
        "arrowstyle": "-",
        "color": COLORS["slate"],
        "linewidth": 0.8,
    },
    bbox={
        "boxstyle": "round,pad=0.35",
        "facecolor": "white",
        "edgecolor": COLORS["border"],
        "alpha": 0.97,
    },
)

ax.set_xlabel("Elapsed time (s)")
ax.set_ylabel(
    f"Objective ({objective_mode})"
)
ax.yaxis.set_major_formatter(
    FuncFormatter(format_objective)
)
ax.xaxis.set_major_locator(
    MaxNLocator(nbins=9)
)
ax.yaxis.set_major_locator(
    MaxNLocator(nbins=8)
)
style_axis(ax)

subtitle_parts = [
    (
        f"{convergence['seed'].nunique()} internal workers"
    ),
    (
        f"{overall_improvement_percent:.2f}% "
        "improvement"
    ),
    (
        f"final runtime {final_runtime_s:.2f} s"
    ),
]

if solver_metadata.get("best_algorithm"):
    subtitle_parts.append(
        "best algorithm "
        + str(
            solver_metadata[
                "best_algorithm"
            ]
        )
    )

add_figure_header(
    fig,
    "Global best-so-far convergence",
    "  ·  ".join(subtitle_parts),
)

ax.legend(
    loc="upper right",
    fontsize=8.8,
)

publication_path = (
    png_directory
    / "01_Publication_Convergence.png"
)

save_figure(
    fig,
    publication_path,
)
saved_figures.append(publication_path)


# =============================================================================
# PLOT 2 — SAFE AUTOMATIC ZOOM
# =============================================================================

zoom = calculate_safe_zoom(
    global_curve,
    reference_objective,
)

fig, ax = plt.subplots(
    figsize=(12.4, 7.1)
)

ax.step(
    global_curve["time_s"],
    global_curve["global_best"],
    where="post",
    linewidth=2.8,
    color=COLORS["teal"],
    label="Global best-so-far",
)

ax.scatter(
    [float(final_point["time_s"])],
    [float(final_point["global_best"])],
    s=58,
    facecolor=COLORS["navy"],
    edgecolor="white",
    linewidth=0.9,
    zorder=6,
    label="Final solver result",
)

if reference_objective is not None:
    ax.axhline(
        reference_objective,
        color=COLORS["amber"],
        linestyle=(0, (6, 4)),
        linewidth=1.55,
        label=(
            f"{reference_label}: "
            f"{reference_objective:,.3f}"
        ),
    )

ax.set_xlim(
    zoom["x_lower"],
    zoom["x_upper"],
)
ax.set_ylim(
    zoom["y_lower"],
    zoom["y_upper"],
)

ax.set_xlabel("Elapsed time (s)")
ax.set_ylabel(
    f"Objective ({objective_mode})"
)
ax.yaxis.set_major_formatter(
    FuncFormatter(format_objective)
)
ax.xaxis.set_major_locator(
    MaxNLocator(nbins=9)
)
ax.yaxis.set_major_locator(
    MaxNLocator(nbins=8)
)
style_axis(ax)

add_figure_header(
    fig,
    "Late-stage convergence — automatic focus",
    (
        "Limits computed from the actual trajectory; "
        "no hard-coded BKS, global best, or objective window"
    ),
)

ax.legend(
    loc="upper right",
    fontsize=8.8,
)

zoom_path = (
    png_directory
    / "02_Publication_Convergence_Zoom.png"
)

save_figure(
    fig,
    zoom_path,
)
saved_figures.append(zoom_path)


# =============================================================================
# PLOT 3 — GLOBAL IMPROVEMENT
# =============================================================================

fig, ax = plt.subplots(
    figsize=(12.0, 6.6)
)

ax.step(
    global_curve["time_s"],
    global_curve["improvement_percent"],
    where="post",
    linewidth=2.5,
    color=COLORS["blue"],
)

ax.scatter(
    [float(final_point["time_s"])],
    [
        float(
            final_point[
                "improvement_percent"
            ]
        )
    ],
    s=48,
    color=COLORS["navy"],
    edgecolor="white",
    linewidth=0.8,
    zorder=5,
)

ax.set_xlabel("Elapsed time (s)")
ax.set_ylabel(
    "Improvement from first accepted solution (%)"
)
style_axis(ax)

add_figure_header(
    fig,
    "Cumulative objective improvement",
    (
        f"Final improvement "
        f"{overall_improvement_percent:.3f}%"
    ),
)

improvement_path = (
    png_directory
    / "03_Global_Improvement_Percent.png"
)

save_figure(
    fig,
    improvement_path,
)
saved_figures.append(improvement_path)


# =============================================================================
# PLOT 4 — INTERNAL WORKER DIAGNOSTIC
# =============================================================================

fig, ax = plt.subplots(
    figsize=(12.4, 7.1)
)

diagnostic_frame = (
    periodic_convergence.copy()
)

current_values = (
    diagnostic_frame["current_obj"]
    .dropna()
    .to_numpy(dtype=float)
)
best_values = (
    diagnostic_frame["stream_best_so_far"]
    .dropna()
    .to_numpy(dtype=float)
)

if current_values.size:
    upper_quantile = float(
        np.nanquantile(
            current_values,
            0.995,
        )
    )
else:
    upper_quantile = float(
        np.nanmax(best_values)
    )

lower_value = float(
    min(
        np.nanmin(best_values),
        final_global_objective,
    )
)

diagnostic_upper = max(
    upper_quantile,
    lower_value * 1.02,
)

diagnostic_margin = max(
    (
        diagnostic_upper
        - lower_value
    )
    * 0.04,
    abs(lower_value) * 0.006,
    1.0,
)

for (
    search_stream,
    group,
) in diagnostic_frame.groupby(
    "search_stream",
    sort=True,
):
    group = group.sort_values(
        [
            "time_s",
            "iter",
        ],
        kind="mergesort",
        na_position="last",
    )

    seed = int(
        group["seed"].iloc[0]
    )
    stream_index = int(
        group[
            "stream_index"
        ].iloc[0]
    )
    color = search_seed_colors[seed]
    linestyle = (
        SEARCH_STREAM_LINESTYLES.get(
            stream_index,
            "-",
        )
    )

    if group["current_obj"].notna().any():
        ax.plot(
            group["time_s"],
            group["current_obj"],
            linewidth=0.38,
            alpha=0.075,
            color=color,
            linestyle=linestyle,
            rasterized=True,
        )

    ax.step(
        group["time_s"],
        group["stream_best_so_far"],
        where="post",
        linewidth=0.82,
        alpha=0.38,
        color=color,
        linestyle=linestyle,
    )

ax.step(
    global_curve["time_s"],
    global_curve["global_best"],
    where="post",
    linewidth=2.5,
    color=COLORS["teal"],
    label="Combined global best",
)

ax.set_ylim(
    max(
        0.0,
        lower_value - diagnostic_margin,
    ),
    diagnostic_upper + diagnostic_margin,
)

ax.set_xlabel("Elapsed time (s)")
ax.set_ylabel("Objective")
ax.yaxis.set_major_formatter(
    FuncFormatter(format_objective)
)
style_axis(ax)

add_figure_header(
    fig,
    "Internal worker-search diagnostic",
    (
        "Independent repeated-iteration streams are reconstructed first; "
        "faint traces are current objectives and darker traces are "
        "stream best-so-far"
    ),
)

ax.legend(
    loc="upper right",
    fontsize=8.8,
)

diagnostic_path = (
    png_directory
    / "04_Worker_Search_Diagnostic.png"
)

save_figure(
    fig,
    diagnostic_path,
)
saved_figures.append(diagnostic_path)


# =============================================================================
# PLOT 5 — FINAL WORKER OBJECTIVES
# =============================================================================

if not worker_summary.empty:
    plot_frame = worker_summary.sort_values(
        "best_obj",
        ascending=True,
    )

    fig_height = max(
        4.8,
        0.42 * len(plot_frame) + 2.4,
    )

    fig, ax = plt.subplots(
        figsize=(10.8, fig_height)
    )

    positions = np.arange(
        len(plot_frame)
    )

    bars = ax.barh(
        positions,
        plot_frame["best_obj"],
        color=COLORS["blue"],
        alpha=0.88,
    )

    ax.set_yticks(positions)
    ax.set_yticklabels(
        plot_frame["seed"].astype(str)
    )
    ax.invert_yaxis()
    ax.set_xlabel("Best objective")
    ax.set_ylabel("Internal worker seed")
    ax.xaxis.set_major_formatter(
        FuncFormatter(format_objective)
    )
    style_axis(
        ax,
        grid_axis="x",
    )

    baseline = float(
        plot_frame["best_obj"].min()
    )

    left_limit = max(
        0.0,
        baseline
        - max(
            (
                plot_frame["best_obj"].max()
                - baseline
            )
            * 0.18,
            abs(baseline) * 0.01,
            1.0,
        ),
    )

    ax.set_xlim(
        left=left_limit,
    )

    for bar, value in zip(
        bars,
        plot_frame["best_obj"],
    ):
        ax.text(
            float(value),
            bar.get_y()
            + bar.get_height() / 2,
            f"  {float(value):,.1f}",
            va="center",
            fontsize=8.0,
            color=COLORS["slate"],
        )

    add_figure_header(
        fig,
        "Best objective reached by each internal worker",
        (
            "Diagnostic only; the full pipeline can improve "
            "beyond these worker endpoints"
        ),
    )

    worker_objective_path = (
        png_directory
        / "05_Worker_Final_Objectives.png"
    )

    save_figure(
        fig,
        worker_objective_path,
        left=0.13,
    )
    saved_figures.append(
        worker_objective_path
    )


# =============================================================================
# PLOT 6 — TIME TO BEST BY WORKER
# =============================================================================

if not worker_summary.empty:
    plot_frame = worker_summary.sort_values(
        "time_to_best_s",
        ascending=True,
    )

    fig_height = max(
        4.8,
        0.42 * len(plot_frame) + 2.4,
    )

    fig, ax = plt.subplots(
        figsize=(10.8, fig_height)
    )

    positions = np.arange(
        len(plot_frame)
    )

    bars = ax.barh(
        positions,
        plot_frame["time_to_best_s"],
        color=COLORS["cyan"],
        alpha=0.90,
    )

    ax.set_yticks(positions)
    ax.set_yticklabels(
        plot_frame["seed"].astype(str)
    )
    ax.invert_yaxis()
    ax.set_xlabel("Time to worker best (s)")
    ax.set_ylabel("Internal worker seed")
    style_axis(
        ax,
        grid_axis="x",
    )

    for bar, value in zip(
        bars,
        plot_frame["time_to_best_s"],
    ):
        ax.text(
            float(value),
            bar.get_y()
            + bar.get_height() / 2,
            f"  {float(value):.2f}",
            va="center",
            fontsize=8.0,
            color=COLORS["slate"],
        )

    add_figure_header(
        fig,
        "Time to best solution by internal worker",
        (
            "Measured from convergence.csv; "
            "pipeline-level improvements are shown separately"
        ),
    )

    time_to_best_path = (
        png_directory
        / "06_Worker_Time_to_Best.png"
    )

    save_figure(
        fig,
        time_to_best_path,
        left=0.13,
    )
    saved_figures.append(
        time_to_best_path
    )


# =============================================================================
# PLOT 7 — RECONSTRUCTED SA STREAM COVERAGE
# =============================================================================

has_acceptance = (
    periodic_convergence[
        "smoothed_interval_acceptance_rate"
    ]
    .notna()
    .any()
)
has_temperature = (
    periodic_convergence[
        "temp"
    ]
    .notna()
    .any()
)

if not search_stream_summary.empty:
    displayed_stream_summary = (
        search_stream_summary
        .nlargest(32, "rows")
        .sort_values(["first_time_s", "seed", "stream_index"], kind="mergesort")
        .reset_index(drop=True)
    )
    omitted_streams = max(0, len(search_stream_summary) - len(displayed_stream_summary))
    fig, ax = plt.subplots(
        figsize=(12.2, float(np.clip(4.8 + 0.28 * len(displayed_stream_summary), 5.2, 13.0)))
    )

    lane_labels: list[str] = []
    for lane, (_, row) in enumerate(displayed_stream_summary.iterrows()):
        seed = int(row["seed"])
        stream_index = int(row["stream_index"])
        first_time = float(row["first_time_s"])
        last_time = float(row["last_time_s"])
        color = search_seed_colors[seed]
        ax.hlines(
            lane,
            first_time,
            last_time,
            color=color,
            linewidth=4.4,
            alpha=0.72,
            zorder=2,
        )
        ax.scatter(
            [first_time, last_time],
            [lane, lane],
            s=[34, 52],
            marker=SEARCH_STREAM_MARKERS.get(stream_index, "o"),
            facecolor=["white", color],
            edgecolor=color,
            linewidth=1.25,
            zorder=4,
        )
        ax.annotate(
            f"{int(row['rows']):,} obs · max iter {float(row['max_iter']):,.0f}",
            (last_time, lane),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.0,
            color=COLORS["slate"],
        )
        lane_labels.append(f"seed {seed} · {str(row['search_stream'])}")

    first_observed = float(displayed_stream_summary["first_time_s"].min())
    last_observed = float(displayed_stream_summary["last_time_s"].max())
    time_span = max(1.0, last_observed - first_observed)
    ax.set_xlim(max(0.0, first_observed - 0.025 * time_span), last_observed + 0.30 * time_span)
    ax.set_yticks(np.arange(len(lane_labels)))
    ax.set_yticklabels(lane_labels, fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlabel("Process elapsed time (s)")
    ax.set_ylabel("Exact C++ search stream")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.1f}"))
    style_axis(ax)
    ax.grid(False, axis="y")

    add_figure_header(
        fig,
        "Exact search-stream coverage timeline",
        (
            f"{len(search_stream_summary)} monotonic traces recovered from "
            f"{periodic_convergence['seed'].nunique()} seeds; every lane is one stream, "
            f"so concurrent or restarted searches are never joined"
            + (f" · showing the 32 densest streams ({omitted_streams} omitted)" if omitted_streams else "")
        ),
    )

    # Seed and stream identity are already written directly on every lane.
    # A second legend obscures endpoint receipts on short runs and adds no data.

    stream_audit_path = (
        png_directory
        / "07_Search_Stream_Reconstruction.png"
    )

    save_figure(
        fig,
        stream_audit_path,
        left=0.20,
        right=0.97,
    )
    saved_figures.append(
        stream_audit_path
    )


# =============================================================================
# PLOT 8 — EVENT COUNTS
# =============================================================================

event_counts = (
    convergence["event"]
    .fillna("unknown")
    .astype(str)
    .value_counts()
    .rename_axis("event")
    .reset_index(name="count")
)

if not event_counts.empty:
    fig, ax = plt.subplots(
        figsize=(10.8, 5.8)
    )

    bars = ax.bar(
        event_counts["event"],
        event_counts["count"],
        color=COLORS["slate"],
        alpha=0.86,
    )

    ax.set_xlabel("Event")
    ax.set_ylabel("Rows")
    ax.tick_params(
        axis="x",
        rotation=22,
    )
    style_axis(
        ax,
        grid_axis="y",
    )

    for bar, count in zip(
        bars,
        event_counts["count"],
    ):
        ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            bar.get_height(),
            f"{int(count):,}",
            ha="center",
            va="bottom",
            fontsize=8.0,
            color=COLORS["slate"],
        )

    add_figure_header(
        fig,
        "Convergence-log event composition",
        (
            f"{len(convergence):,} cleaned rows from "
            f"{convergence['seed'].nunique()} workers"
        ),
    )

    events_path = (
        png_directory
        / "08_Event_Counts.png"
    )

    save_figure(
        fig,
        events_path,
        bottom=0.16,
    )
    saved_figures.append(
        events_path
    )



# =============================================================================
# PLOT 9 — RAW SA TEMPERATURE OBSERVATIONS
# =============================================================================

if has_temperature:
    positive_temperature_all = (
        periodic_convergence[
            periodic_convergence[
                "temp"
            ]
            > 0
        ].copy()
    )

    if not positive_temperature_all.empty:
        fig, ax = plt.subplots(
            figsize=(12.4, 7.0)
        )
        displayed_temperature_streams = set(
            search_stream_summary.nlargest(24, "rows")["search_stream"].astype(str)
            if not search_stream_summary.empty else []
        )
        temperature_seed_rank = {
            seed: index
            for index, seed in enumerate(sorted(search_seed_colors))
        }

        for (
            search_stream,
            group,
        ) in positive_temperature_all.groupby(
            "search_stream",
            sort=True,
        ):
            if displayed_temperature_streams and str(search_stream) not in displayed_temperature_streams:
                continue
            group = group.sort_values(
                [
                    "time_s",
                    "iter",
                ],
                kind="mergesort",
                na_position="last",
            )
            group = thin_stream_frame(group, 900)

            seed = int(
                group["seed"].iloc[0]
            )
            stream_index = int(
                group[
                    "stream_index"
                ].iloc[0]
            )

            # Connect only consecutive observations from this exact stream.
            # Invalid samples, timestamp resets, or a gap larger than 3.5
            # normal sample intervals split the line, so the graph is readable
            # without recreating the cross-stream "needles" from older reports.
            # Align each stream at its own start. Absolute process time makes
            # sequential SA restarts look like one sawtooth even though they
            # are independent schedules; graph 7 already carries real timing.
            times = group["stream_elapsed_s"].to_numpy(dtype=float)
            temperatures = group["temp"].to_numpy(dtype=float)
            runs = contiguous_observation_runs(times, temperatures)
            for run in runs:
                if len(run) >= 2:
                    ax.plot(
                        times[run],
                        temperatures[run],
                        color=search_seed_colors[seed],
                        linestyle=SEARCH_STREAM_LINESTYLES.get(stream_index, "-"),
                        linewidth=1.35,
                        alpha=0.40,
                        zorder=2,
                    )
                    # Identical cooling schedules legitimately overlap. Plot
                    # actual observations at staggered indices so every seed is
                    # visible without offsetting or inventing any measurement.
                    marker_stride = max(len(temperature_seed_rank), len(run) // 10, 1)
                    marker_offset = temperature_seed_rank.get(seed, 0) % marker_stride
                    marker_rows = run[marker_offset::marker_stride]
                    if not len(marker_rows):
                        marker_rows = run[-1:]
                    ax.scatter(
                        times[marker_rows],
                        temperatures[marker_rows],
                        s=24,
                        alpha=0.90,
                        facecolor=search_seed_colors[seed],
                        edgecolor="white",
                        linewidth=0.55,
                        marker=search_seed_markers.get(seed, "o"),
                        zorder=5,
                    )
                else:
                    ax.scatter(
                        times[run],
                        temperatures[run],
                        s=25,
                        alpha=0.82,
                        facecolor=search_seed_colors[seed],
                        edgecolor="white",
                        linewidth=0.55,
                        marker=search_seed_markers.get(seed, "o"),
                        zorder=4,
                    )

        ax.set_yscale("log")
        ax.set_xlabel("Elapsed time within each SA stream (s)")
        ax.set_ylabel(
            "Raw SA temperature"
        )
        ax.yaxis.set_minor_formatter(
            NullFormatter()
        )
        style_axis(ax)
        ax.grid(
            True,
            which="minor",
            axis="y",
            linestyle=":",
            linewidth=0.42,
            alpha=0.14,
        )

        omitted_nonpositive = int(
            (
                periodic_convergence[
                    "temp"
                ]
                <= 0
            ).sum()
        )

        add_figure_header(
            fig,
            "Simulated-annealing temperature by search stream",
            (
                "Streams are aligned at their own first sample; lines connect only "
                "consecutive records from one C++ stream, and identical schedules may overlap exactly"
            ),
        )

        if omitted_nonpositive:
            ax.text(
                0.995,
                0.015,
                (
                    f"{omitted_nonpositive} nonpositive temperature "
                    "records omitted from the log axis"
                ),
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=7.6,
                color=COLORS["slate"],
                bbox={
                    "boxstyle": "round,pad=0.30",
                    "facecolor": "white",
                    "edgecolor": COLORS["border"],
                    "alpha": 0.94,
                },
            )

        add_search_stream_legends(
            ax,
            periodic_convergence,
            search_seed_colors,
            style_location="center right",
            observations_only=False,
            seed_markers=search_seed_markers,
        )

        temperature_path = (
            png_directory
            / "09_SA_Temperature_Decay.png"
        )

        save_figure(
            fig,
            temperature_path,
        )
        saved_figures.append(
            temperature_path
        )


# =============================================================================
# PLOT 9B — NORMALIZED SA COOLING OBSERVATIONS
# =============================================================================

normalized_temperature = (
    periodic_convergence[
        (
            periodic_convergence[
                "normalized_temp"
            ]
            > 0
        )
        & (
            periodic_convergence[
                "time_progress_percent"
            ]
            .notna()
        )
    ].copy()
)

if not normalized_temperature.empty:
    fig, ax = plt.subplots(
        figsize=(12.4, 7.0)
    )

    observed_profiles: list[pd.DataFrame] = []

    for (
        search_stream,
        group,
    ) in normalized_temperature.groupby(
        "search_stream",
        sort=True,
    ):
        group = (
            group
            .sort_values(
                "time_progress_percent"
            )
            .drop_duplicates(
                subset=[
                    "time_progress_percent"
                ],
                keep="last",
            )
        )
        group = thin_stream_frame(group, 1200)

        progress = group[
            "time_progress_percent"
        ].to_numpy(dtype=float)
        normalized = group[
            "normalized_temp"
        ].to_numpy(dtype=float)

        valid = (
            np.isfinite(progress)
            & np.isfinite(normalized)
            & (normalized > 0)
        )

        progress = progress[valid]
        normalized = normalized[valid]

        if len(progress) < 1:
            continue

        seed = int(
            group["seed"].iloc[0]
        )
        stream_index = int(
            group[
                "stream_index"
            ].iloc[0]
        )

        stream_gap = (
            max(10.0, float(np.median(np.diff(progress))) * 3.5)
            if len(progress) > 1 else 10.0
        )
        for run in contiguous_observation_runs(
            progress,
            normalized,
            maximum_gap=stream_gap,
        ):
            if len(run) >= 2:
                ax.plot(
                    progress[run],
                    normalized[run],
                    color=search_seed_colors[seed],
                    linestyle=SEARCH_STREAM_LINESTYLES.get(stream_index, "-"),
                    linewidth=1.15,
                    alpha=0.34,
                    marker=SEARCH_STREAM_MARKERS.get(stream_index, "o"),
                    markersize=3.0,
                    markeredgecolor="white",
                    markeredgewidth=0.35,
                    zorder=3,
                )
            else:
                ax.scatter(
                    progress[run],
                    normalized[run],
                    s=20,
                    alpha=0.38,
                    facecolor=search_seed_colors[seed],
                    edgecolor="white",
                    linewidth=0.4,
                    marker=SEARCH_STREAM_MARKERS.get(stream_index, "o"),
                    zorder=3,
                )

        observed_profiles.append(
            pd.DataFrame(
                {
                    "progress": progress,
                    "log_temperature": np.log10(normalized),
                }
            )
        )

    # Summarize in log space. The median/IQR line is split at empty bins: there
    # is no interpolation across gaps and therefore no invented cooling path.
    if observed_profiles:
        observed_frame = pd.concat(
            observed_profiles,
            ignore_index=True,
        )
        observed_max_progress = float(
            observed_frame["progress"].max()
        )
        bin_count = max(
            1,
            min(20, int(math.ceil(math.sqrt(len(observed_frame))))),
        )
        bin_edges = np.linspace(
            0.0,
            max(observed_max_progress, 1e-6),
            bin_count + 1,
        )
        if len(np.unique(bin_edges)) > 1:
            observed_frame["progress_bin"] = pd.cut(
                observed_frame["progress"],
                bins=bin_edges,
                include_lowest=True,
                duplicates="drop",
            )
            binned = (
                observed_frame
                .groupby("progress_bin", observed=False)
                .agg(
                    progress=("progress", "median"),
                    median_log=("log_temperature", "median"),
                    q25_log=("log_temperature", lambda values: values.quantile(0.25)),
                    q75_log=("log_temperature", lambda values: values.quantile(0.75)),
                    observations=("log_temperature", "size"),
                )
                .reset_index()
            )
            binned = binned[binned["observations"] >= 2]
            if not binned.empty:
                binned_progress = binned["progress"].to_numpy(dtype=float)
                binned_median = 10.0 ** binned["median_log"].to_numpy(dtype=float)
                binned_q25 = 10.0 ** binned["q25_log"].to_numpy(dtype=float)
                binned_q75 = 10.0 ** binned["q75_log"].to_numpy(dtype=float)
                bin_width = float(bin_edges[1] - bin_edges[0])
                binned_runs = contiguous_observation_runs(
                    binned_progress,
                    binned_median,
                    binned_q25,
                    binned_q75,
                    maximum_gap=bin_width * 1.75,
                )
                median_label_used = False
                band_label_used = False
                for run in binned_runs:
                    if len(run) >= 2:
                        ax.fill_between(
                            binned_progress[run],
                            binned_q25[run],
                            binned_q75[run],
                            color=COLORS["teal"],
                            alpha=0.13,
                            linewidth=0,
                            label=("Interquartile range" if not band_label_used else None),
                            zorder=4,
                        )
                        band_label_used = True
                        ax.plot(
                            binned_progress[run],
                            binned_median[run],
                            color=COLORS["teal"],
                            linewidth=2.25,
                            marker="o",
                            markersize=5.2,
                            markeredgecolor="white",
                            markeredgewidth=0.75,
                            label=("Cross-stream median" if not median_label_used else None),
                            zorder=6,
                        )
                        median_label_used = True
                    else:
                        ax.scatter(
                            binned_progress[run],
                            binned_median[run],
                            s=64,
                            facecolor=COLORS["teal"],
                            edgecolor="white",
                            linewidth=0.8,
                            label=("Cross-stream median" if not median_label_used else None),
                            zorder=6,
                        )
                        median_label_used = True

    ax.set_yscale("log")
    observed_progress_max = float(
        normalized_temperature["time_progress_percent"].max()
    )
    ax.set_xlim(0.0, min(100.0, max(5.0, observed_progress_max * 1.08)))
    ax.xaxis.set_major_locator(
        MaxNLocator(
            nbins=6,
            integer=True,
        )
    )
    ax.set_xlabel(
        "Elapsed wall-clock progress within each SA stream (%)"
    )
    ax.set_ylabel(
        r"Normalized temperature $T/T_0$"
    )
    ax.yaxis.set_minor_formatter(
        NullFormatter()
    )
    style_axis(ax)
    ax.grid(
        True,
        which="minor",
        axis="y",
        linestyle=":",
        linewidth=0.42,
        alpha=0.12,
    )

    add_figure_header(
        fig,
        "Normalized simulated-annealing cooling profile",
        (
            "Temperature divided by each stream's initial value; continuous "
            f"only across observed neighbors, with no interpolation across gaps in "
            f"{periodic_convergence['search_stream'].nunique()} "
            "independent streams"
        ),
    )

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(
            loc="upper right",
            fontsize=8.3,
        )

    normalized_temperature_path = (
        png_directory
        / "09B_SA_Normalized_Cooling_Profile.png"
    )

    save_figure(
        fig,
        normalized_temperature_path,
    )
    saved_figures.append(
        normalized_temperature_path
    )


# =============================================================================
# PLOT 10 — ACCEPTANCE RATE
# =============================================================================

if has_acceptance:
    fig, ax = plt.subplots(
        figsize=(12.2, 6.7)
    )

    acceptance_frame = periodic_convergence[
        periodic_convergence[
            "interval_acceptance_rate"
        ].notna()
    ].copy()

    # Show the actual per-stream signal first. Faint raw interval lines retain
    # the genuine seed-level zigzag; the thicker rolling-median line improves
    # legibility without joining streams, counter resets, or missing samples.
    displayed_acceptance_streams = set(
        acceptance_frame["search_stream"].value_counts().head(24).index.astype(str)
    )
    displayed_acceptance = acceptance_frame[
        acceptance_frame["search_stream"].astype(str).isin(displayed_acceptance_streams)
    ].copy()
    acceptance_seed_rank = {
        seed: index
        for index, seed in enumerate(sorted(search_seed_colors))
    }
    for search_stream, group in displayed_acceptance.groupby("search_stream", sort=True):
        group = (
            group
            .sort_values(["time_progress_percent", "iter"], kind="mergesort")
            .drop_duplicates(subset=["time_progress_percent"], keep="last")
        )
        group = thin_stream_frame(group, 1200)
        progress = group["time_progress_percent"].to_numpy(dtype=float)
        raw_rate = group["interval_acceptance_rate"].to_numpy(dtype=float)
        smooth_rate = group["smoothed_interval_acceptance_rate"].to_numpy(dtype=float)
        valid = np.isfinite(progress) & np.isfinite(raw_rate) & np.isfinite(smooth_rate)
        progress, raw_rate, smooth_rate = progress[valid], raw_rate[valid], smooth_rate[valid]
        if not len(progress):
            continue
        seed = int(group["seed"].iloc[0])
        stream_index = int(group["stream_index"].iloc[0])
        progress_gap = (
            max(5.0, float(np.median(np.diff(progress))) * 3.5)
            if len(progress) > 1 else 5.0
        )
        for run in contiguous_observation_runs(
            progress,
            raw_rate,
            smooth_rate,
            maximum_gap=progress_gap,
        ):
            if len(run) >= 2:
                ax.plot(
                    progress[run],
                    raw_rate[run],
                    color=search_seed_colors[seed],
                    linewidth=0.58,
                    alpha=0.20,
                    zorder=1,
                )
                marker_stride = max(len(acceptance_seed_rank), len(run) // 16, 1)
                marker_offset = acceptance_seed_rank.get(seed, 0) % marker_stride
                ax.plot(
                    progress[run],
                    smooth_rate[run],
                    color=search_seed_colors[seed],
                    linestyle=SEARCH_STREAM_LINESTYLES.get(stream_index, "-"),
                    linewidth=1.28,
                    alpha=0.72,
                    marker=search_seed_markers.get(seed, "o"),
                    markevery=(marker_offset, marker_stride),
                    markersize=3.1,
                    markeredgecolor="white",
                    markeredgewidth=0.35,
                    zorder=3,
                )
            else:
                ax.scatter(
                    progress[run],
                    smooth_rate[run],
                    s=20,
                    color=search_seed_colors[seed],
                    marker=search_seed_markers.get(seed, "o"),
                    edgecolor="white",
                    linewidth=0.4,
                    alpha=0.76,
                    zorder=3,
                )

    # Build a directly comparable cross-stream envelope on a 0–100% progress
    # axis. Empty bins remain empty, so no invented segment spans missing data.
    acceptance_bin_count = 50
    acceptance_edges = np.linspace(0.0, 100.0, acceptance_bin_count + 1)
    acceptance_centers = (acceptance_edges[:-1] + acceptance_edges[1:]) / 2.0
    acceptance_frame["profile_bin"] = np.clip(
        np.digitize(acceptance_frame["time_progress_percent"], acceptance_edges) - 1,
        0,
        acceptance_bin_count - 1,
    )
    acceptance_per_stream = (
        acceptance_frame
        .groupby(["search_stream", "profile_bin"], as_index=False)
        .agg(acceptance_rate=("smoothed_interval_acceptance_rate", "median"))
    )
    acceptance_pivot = acceptance_per_stream.pivot(
        index="profile_bin", columns="search_stream", values="acceptance_rate"
    ).reindex(range(acceptance_bin_count))
    acceptance_observed = acceptance_pivot.notna().any(axis=1)
    acceptance_median = acceptance_pivot.T.median().where(acceptance_observed)
    acceptance_q25 = acceptance_pivot.quantile(0.25, axis=1).where(acceptance_observed)
    acceptance_q75 = acceptance_pivot.quantile(0.75, axis=1).where(acceptance_observed)
    acceptance_active_streams = acceptance_pivot.notna().sum(axis=1)

    acceptance_profile = pd.DataFrame(
        {
            "stream_progress_percent": acceptance_centers,
            "median_acceptance_rate": acceptance_median.to_numpy(dtype=float),
            "q25_acceptance_rate": acceptance_q25.to_numpy(dtype=float),
            "q75_acceptance_rate": acceptance_q75.to_numpy(dtype=float),
            "active_streams": acceptance_active_streams.to_numpy(dtype=int),
        }
    )
    acceptance_profile.to_csv(
        csv_directory / "AcceptanceTimeProfile.csv",
        index=False,
    )

    valid_acceptance_profile = (
        np.isfinite(acceptance_median.to_numpy(dtype=float))
        & np.isfinite(acceptance_q25.to_numpy(dtype=float))
        & np.isfinite(acceptance_q75.to_numpy(dtype=float))
    )

    if valid_acceptance_profile.any():
        median_values = acceptance_median.to_numpy(dtype=float)[valid_acceptance_profile]
        q25_values = acceptance_q25.to_numpy(dtype=float)[valid_acceptance_profile]
        q75_values = acceptance_q75.to_numpy(dtype=float)[valid_acceptance_profile]
        acceptance_profile_times = acceptance_centers[valid_acceptance_profile]
        acceptance_bin_width = float(acceptance_edges[1] - acceptance_edges[0])
        acceptance_runs = contiguous_observation_runs(
            acceptance_profile_times,
            median_values,
            q25_values,
            q75_values,
            maximum_gap=acceptance_bin_width * 2.25,
        )
        median_label_used = False
        band_label_used = False
        for run in acceptance_runs:
            if len(run) >= 2:
                ax.fill_between(
                    acceptance_profile_times[run],
                    q25_values[run],
                    q75_values[run],
                    color=COLORS["teal"],
                    alpha=0.18,
                    linewidth=0,
                    label=("Interquartile range" if not band_label_used else None),
                    zorder=2,
                )
                band_label_used = True
                ax.plot(
                    acceptance_profile_times[run],
                    median_values[run],
                    color=COLORS["navy"],
                    linewidth=2.25,
                    label=("Median across active streams" if not median_label_used else None),
                    zorder=3,
                )
                median_label_used = True
            else:
                ax.scatter(
                    acceptance_profile_times[run],
                    median_values[run],
                    s=24,
                    color=COLORS["navy"],
                    label=("Median across active streams" if not median_label_used else None),
                    zorder=3,
                )
                median_label_used = True

    ax.set_xlim(0.0, 100.0)
    finite_acceptance = np.concatenate(
        [
            displayed_acceptance["interval_acceptance_rate"].to_numpy(dtype=float),
            acceptance_median.to_numpy(dtype=float),
            acceptance_q75.to_numpy(dtype=float),
        ]
    )
    finite_acceptance = finite_acceptance[np.isfinite(finite_acceptance)]
    observed_acceptance_upper = (
        float(np.quantile(finite_acceptance, 0.99))
        if finite_acceptance.size else 1.0
    )
    acceptance_axis_upper = min(
        1.0,
        max(
            0.10,
            math.ceil(observed_acceptance_upper * 1.18 / 0.05) * 0.05,
        ),
    )
    ax.set_ylim(0.0, acceptance_axis_upper)

    ax.set_xlabel("Elapsed wall-clock progress within each SA stream (%)")
    ax.set_ylabel("Moves accepted")
    ax.yaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value * 100:.0f}%"
        )
    )
    style_axis(ax)

    add_figure_header(
        fig,
        "Local move-acceptance rate over time",
        (
            "Faint lines are raw reset-safe interval rates; colored seed traces are "
            "five-sample medians, with a cross-stream median/IQR that never bridges gaps"
        ),
    )

    aggregate_handles = [
        Line2D([0], [0], color=COLORS["navy"], linewidth=2.25, label="Cross-stream median"),
        Patch(facecolor=COLORS["teal"], alpha=0.18, edgecolor="none", label="Interquartile range"),
    ]
    aggregate_legend = ax.legend(handles=aggregate_handles, loc="upper right", fontsize=8.1)
    ax.add_artist(aggregate_legend)
    acceptance_seeds = sorted({int(value) for value in displayed_acceptance["seed"].dropna()})
    seed_handles = [
        Line2D([0], [0], color=search_seed_colors[seed], linewidth=1.5, marker=search_seed_markers.get(seed, "o"), markersize=4, label=f"seed {seed}")
        for seed in acceptance_seeds
    ]
    if seed_handles:
        ax.legend(
            handles=seed_handles,
            loc="lower right",
            fontsize=7.4,
            ncol=2,
            title="Seed traces",
            title_fontsize=7.7,
        )

    acceptance_path = (
        png_directory
        / "10_Acceptance_Rate.png"
    )

    save_figure(
        fig,
        acceptance_path,
    )
    saved_figures.append(
        acceptance_path
    )


# =============================================================================
# PLOT 11 — RESET-AWARE STAGNATION DYNAMICS
# =============================================================================

has_stagnation = (
    periodic_convergence["stagnation"]
    .notna()
    .any()
)

if has_stagnation:
    stagnation_frame = periodic_convergence[
        periodic_convergence["stagnation"].notna()
    ].copy()

    stagnation_frame = stagnation_frame.sort_values(
        [
            "search_stream",
            "time_s",
            "iter",
        ],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    reset_rows: list[dict[str, Any]] = []
    # Detect resets independently inside every stream. A stagnation counter is
    # discontinuous, so reset events are summarized separately instead of
    # drawing thousands of high-frequency segments that resemble needles.
    for search_stream, group in stagnation_frame.groupby(
        "search_stream",
        sort=True,
    ):
        group = group.sort_values(
            ["time_s", "iter"],
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)

        times = group["time_s"].to_numpy(dtype=float)
        values = group["stagnation"].to_numpy(dtype=float)

        for index in range(1, len(group)):
            previous_time = float(times[index - 1])
            current_time = float(times[index])
            previous_value = float(values[index - 1])
            current_value = float(values[index])

            if not all(
                math.isfinite(value)
                for value in [
                    previous_time,
                    current_time,
                    previous_value,
                    current_value,
                ]
            ):
                continue

            is_reset = current_value < previous_value

            if is_reset:
                row = group.iloc[index]

                reset_rows.append(
                    {
                        "search_stream": search_stream,
                        "seed": int(row["seed"]),
                        "stream_index": int(
                            row["stream_index"]
                        ),
                        "time_s": current_time,
                        "iter": safe_float(row["iter"]),
                        "stagnation_before": previous_value,
                        "stagnation_after": current_value,
                        "reset_magnitude": (
                            previous_value - current_value
                        ),
                        "current_obj": safe_float(
                            row.get("current_obj")
                        ),
                        "best_obj": safe_float(
                            row.get("best_obj")
                        ),
                        "accepted_moves": safe_float(
                            row.get("accepted_moves")
                        ),
                    }
                )

                continue

    reset_events = pd.DataFrame(reset_rows)

    if reset_events.empty:
        reset_events = pd.DataFrame(
            columns=[
                "search_stream",
                "seed",
                "stream_index",
                "time_s",
                "iter",
                "stagnation_before",
                "stagnation_after",
                "reset_magnitude",
                "current_obj",
                "best_obj",
                "accepted_moves",
            ]
        )

    reset_events.to_csv(
        csv_directory / "StagnationResetEvents.csv",
        index=False,
    )

    # Aggregate each stream once per time bin before combining streams. This
    # prevents densely logged streams from dominating the median/IQR profile.
    minimum_time = float(
        stagnation_frame["time_s"].min()
    )
    maximum_time = float(
        stagnation_frame["time_s"].max()
    )

    profile_bin_count = int(
        np.clip(
            round(
                math.sqrt(
                    max(
                        len(stagnation_frame),
                        1,
                    )
                )
            ),
            60,
            140,
        )
    )

    if maximum_time <= minimum_time:
        maximum_time = minimum_time + 1.0

    profile_edges = np.linspace(
        minimum_time,
        maximum_time,
        profile_bin_count + 1,
    )

    profile_centers = (
        profile_edges[:-1]
        + profile_edges[1:]
    ) / 2.0

    profile_width = float(
        profile_edges[1]
        - profile_edges[0]
    )

    stagnation_frame["profile_bin"] = np.clip(
        np.digitize(
            stagnation_frame["time_s"],
            profile_edges,
            right=False,
        )
        - 1,
        0,
        profile_bin_count - 1,
    )

    per_stream_profile = (
        stagnation_frame
        .groupby(
            [
                "search_stream",
                "profile_bin",
            ],
            as_index=False,
        )
        .agg(
            stagnation_median=(
                "stagnation",
                "median",
            ),
        )
    )

    profile_pivot = per_stream_profile.pivot(
        index="profile_bin",
        columns="search_stream",
        values="stagnation_median",
    ).reindex(
        range(profile_bin_count)
    )

    # Rolling smoothing may borrow neighbouring values, but it must never
    # manufacture a counter value for a time bin that had no observation at
    # all.  Keeping those bins missing also prevents a plotted line from
    # bridging telemetry gaps.
    profile_observed = profile_pivot.notna().any(
        axis=1
    )

    profile_median = profile_pivot.median(
        axis=1,
        skipna=True,
    ).rolling(
        window=3,
        center=True,
        min_periods=1,
    ).median().where(profile_observed)
    profile_q25 = profile_pivot.quantile(
        0.25,
        axis=1,
    ).rolling(
        window=3,
        center=True,
        min_periods=1,
    ).median().where(profile_observed)
    profile_q75 = profile_pivot.quantile(
        0.75,
        axis=1,
    ).rolling(
        window=3,
        center=True,
        min_periods=1,
    ).median().where(profile_observed)
    active_streams = profile_pivot.notna().sum(
        axis=1
    )

    if not reset_events.empty:
        reset_events["profile_bin"] = np.clip(
            np.digitize(
                reset_events["time_s"],
                profile_edges,
                right=False,
            )
            - 1,
            0,
            profile_bin_count - 1,
        )

        reset_counts = (
            reset_events
            .groupby("profile_bin")
            .size()
            .reindex(
                range(profile_bin_count),
                fill_value=0,
            )
            .astype(float)
        )
    else:
        reset_counts = pd.Series(
            np.zeros(
                profile_bin_count,
                dtype=float,
            ),
            index=range(profile_bin_count),
        )

    reset_rate = (
        reset_counts
        / active_streams.replace(0, np.nan)
    ).fillna(0.0)

    stagnation_profile = pd.DataFrame(
        {
            "time_s": profile_centers,
            "median_stagnation": (
                profile_median.to_numpy(
                    dtype=float
                )
            ),
            "q25_stagnation": (
                profile_q25.to_numpy(
                    dtype=float
                )
            ),
            "q75_stagnation": (
                profile_q75.to_numpy(
                    dtype=float
                )
            ),
            "active_streams": (
                active_streams.to_numpy(
                    dtype=int
                )
            ),
            "reset_count": (
                reset_counts.to_numpy(
                    dtype=float
                )
            ),
            "resets_per_active_stream": (
                reset_rate.to_numpy(
                    dtype=float
                )
            ),
        }
    )

    stagnation_profile.to_csv(
        csv_directory / "StagnationTimeProfile.csv",
        index=False,
    )

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(12.4, 8.2),
        sharex=True,
        gridspec_kw={
            "height_ratios": [
                3.35,
                1.0,
            ],
            "hspace": 0.09,
        },
    )

    trace_ax = axes[0]
    reset_ax = axes[1]

    valid_profile = (
        np.isfinite(profile_median.to_numpy())
        & np.isfinite(profile_q25.to_numpy())
        & np.isfinite(profile_q75.to_numpy())
    )

    if valid_profile.any():
        stagnation_median_values = profile_median.to_numpy(dtype=float)[valid_profile]
        stagnation_q25_values = profile_q25.to_numpy(dtype=float)[valid_profile]
        stagnation_q75_values = profile_q75.to_numpy(dtype=float)[valid_profile]
        stagnation_profile_times = profile_centers[valid_profile]
        stagnation_sample_gaps = (
            stagnation_frame
            .sort_values(["search_stream", "time_s"])
            .groupby("search_stream", sort=False)["time_s"]
            .diff()
            .dropna()
        )
        stagnation_sample_gaps = stagnation_sample_gaps[stagnation_sample_gaps > 0]
        stagnation_maximum_gap = max(
            profile_width * 2.0,
            (
                float(stagnation_sample_gaps.median()) * 2.5
                if not stagnation_sample_gaps.empty else profile_width * 2.0
            ),
        )
        stagnation_runs = contiguous_observation_runs(
            stagnation_profile_times,
            stagnation_median_values,
            stagnation_q25_values,
            stagnation_q75_values,
            maximum_gap=stagnation_maximum_gap,
        )
        band_label_used = False
        median_label_used = False
        for run in stagnation_runs:
            if len(run) >= 2:
                trace_ax.fill_between(
                    stagnation_profile_times[run],
                    stagnation_q25_values[run],
                    stagnation_q75_values[run],
                    step="post",
                    color=COLORS["teal"],
                    alpha=0.16,
                    linewidth=0,
                    label=("Interquartile range" if not band_label_used else None),
                    zorder=3,
                )
                band_label_used = True
                trace_ax.plot(
                    stagnation_profile_times[run],
                    stagnation_median_values[run],
                    drawstyle="steps-post",
                    color=COLORS["navy"],
                    linewidth=2.15,
                    label=("Median across active streams" if not median_label_used else None),
                    zorder=4,
                )
                median_label_used = True
            else:
                trace_ax.scatter(
                    stagnation_profile_times[run],
                    stagnation_median_values[run],
                    s=22,
                    color=COLORS["navy"],
                    label=("Median across active streams" if not median_label_used else None),
                    zorder=4,
                )
                median_label_used = True

    finite_stagnation = stagnation_frame[
        "stagnation"
    ].replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()

    if not finite_stagnation.empty:
        robust_upper = max(
            1.0,
            float(
                finite_stagnation.quantile(
                    0.995
                )
            ),
        )

        profile_upper = (
            float(
                np.nanmax(
                    profile_q75.to_numpy(
                        dtype=float
                    )
                )
            )
            if np.isfinite(
                profile_q75.to_numpy(
                    dtype=float
                )
            ).any()
            else 0.0
        )

        trace_ax.set_ylim(
            0.0,
            max(
                robust_upper,
                profile_upper,
            )
            * 1.06,
        )

    trace_ax.set_ylabel(
        "Stagnation counter"
    )
    style_axis(trace_ax)

    reset_ax.bar(
        profile_centers,
        reset_rate,
        width=profile_width * 0.90,
        color=COLORS["amber"],
        alpha=0.72,
        edgecolor="white",
        linewidth=0.25,
        zorder=2,
    )

    if (
        np.isfinite(
            reset_rate.to_numpy(
                dtype=float
            )
        ).any()
    ):
        reset_upper = max(
            0.05,
            float(
                reset_rate.quantile(
                    0.995
                )
            ),
        )

        reset_ax.set_ylim(
            0.0,
            reset_upper * 1.16,
        )

    reset_ax.set_xlabel(
        "Elapsed time (s)"
    )
    reset_ax.set_ylabel(
        "Resets /\nactive stream"
    )
    style_axis(
        reset_ax,
        grid_axis="y",
    )

    trace_ax.set_xlim(
        minimum_time,
        maximum_time,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            color=COLORS["navy"],
            linewidth=2.15,
            label="Median",
        ),
        Patch(
            facecolor=COLORS["teal"],
            edgecolor="none",
            alpha=0.16,
            label="Interquartile range",
        ),
        Patch(
            facecolor=COLORS["amber"],
            edgecolor="none",
            alpha=0.72,
            label="Reset density",
        ),
    ]

    trace_ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=8.0,
        ncol=2,
    )

    reset_count_total = int(
        len(reset_events)
    )

    add_figure_header(
        fig,
        "Reset-aware search stagnation dynamics",
        (
            f"{reset_count_total:,} observed counter resets"
            "  ·  one median per stream and time bin"
            "  ·  resets summarized separately below"
        ),
    )

    stagnation_path = (
        png_directory
        / "11_Stagnation_Counter.png"
    )

    save_figure(
        fig,
        stagnation_path,
        left=0.095,
        right=0.965,
        bottom=0.085,
        top=0.885,
    )
    saved_figures.append(
        stagnation_path
    )


# =============================================================================
# PLOT 12 — FINAL ACCEPTED AND ATTEMPTED MOVES
# =============================================================================

has_move_counts = (
    convergence["accepted_moves"]
    .notna()
    .any()
    and convergence["attempted_moves"]
    .notna()
    .any()
)

if has_move_counts:
    final_move_rows = (
        periodic_convergence
        .sort_values(
            ["seed", "time_s", "iter"],
            kind="mergesort",
            na_position="last",
        )
        .groupby(
            "search_stream",
            as_index=False,
        )
        .tail(1)
        .sort_values(
            [
                "seed",
                "stream_index",
            ]
        )
        .copy()
    )

    if not final_move_rows.empty:
        positions = np.arange(
            len(final_move_rows)
        )
        bar_width = 0.38

        fig, ax = plt.subplots(
            figsize=(
                max(
                    10.8,
                    len(final_move_rows) * 0.72,
                ),
                6.5,
            )
        )

        ax.bar(
            positions - bar_width / 2,
            final_move_rows[
                "accepted_moves"
            ],
            width=bar_width,
            color=COLORS["teal"],
            label="Accepted moves",
        )

        ax.bar(
            positions + bar_width / 2,
            final_move_rows[
                "attempted_moves"
            ],
            width=bar_width,
            color=COLORS["light_slate"],
            label="Attempted moves",
        )

        ax.set_xticks(positions)
        ax.set_xticklabels(
            final_move_rows[
                "search_stream"
            ].astype(str),
            rotation=25,
            ha="right",
        )
        ax.set_xlabel("Reconstructed SA stream")
        ax.set_ylabel("Cumulative move count")
        ax.yaxis.set_major_formatter(
            FuncFormatter(format_objective)
        )
        style_axis(
            ax,
            grid_axis="y",
        )

        add_figure_header(
            fig,
            "Accepted and attempted moves by worker",
            (
                "Final periodic cumulative counters after separating "
                "repeated iteration sequences"
            ),
        )

        ax.legend(
            loc="upper left",
            fontsize=8.5,
        )

        moves_path = (
            png_directory
            / "12_Accepted_Attempted_Moves.png"
        )

        save_figure(
            fig,
            moves_path,
            bottom=0.15,
        )
        saved_figures.append(
            moves_path
        )


# =============================================================================
# PLOT 13 — CURRENT OBJECTIVE VS BEST-SO-FAR
# =============================================================================

has_current_objective = (
    periodic_convergence[
        "current_obj"
    ].notna().any()
)

if has_current_objective:
    scatter_frame = periodic_convergence.dropna(
        subset=[
            "current_obj",
            "stream_best_so_far",
        ]
    ).copy()

    # Keep the graph responsive for very dense logs while preserving the
    # complete cleaned CSV.
    if len(scatter_frame) > 50_000:
        sample_step = int(
            math.ceil(
                len(scatter_frame) / 50_000
            )
        )
        scatter_frame = scatter_frame.iloc[
            ::sample_step
        ].copy()

    finite_values = np.concatenate(
        [
            scatter_frame[
                "stream_best_so_far"
            ].to_numpy(dtype=float),
            scatter_frame[
                "current_obj"
            ].to_numpy(dtype=float),
        ]
    )

    finite_values = finite_values[
        np.isfinite(finite_values)
    ]

    if finite_values.size:
        low = float(
            np.quantile(
                finite_values,
                0.001,
            )
        )
        high = float(
            np.quantile(
                finite_values,
                0.995,
            )
        )

        if high <= low:
            high = low + max(
                abs(low) * 0.02,
                1.0,
            )

        fig, ax = plt.subplots(
            figsize=(8.3, 7.4)
        )

        ax.scatter(
            scatter_frame[
                "stream_best_so_far"
            ],
            scatter_frame[
                "current_obj"
            ],
            s=9,
            alpha=0.14,
            color=COLORS["blue"],
            edgecolors="none",
            rasterized=True,
        )

        ax.plot(
            [low, high],
            [low, high],
            color=COLORS["navy"],
            linewidth=1.2,
            linestyle=(0, (5, 4)),
            label="Current = best-so-far",
        )

        ax.set_xlim(low, high)
        ax.set_ylim(low, high)
        ax.set_xlabel("Search-stream best-so-far objective")
        ax.set_ylabel("Current objective")
        ax.xaxis.set_major_formatter(
            FuncFormatter(format_objective)
        )
        ax.yaxis.set_major_formatter(
            FuncFormatter(format_objective)
        )
        style_axis(ax)

        add_figure_header(
            fig,
            "Current objective versus search-stream best-so-far",
            (
                f"{len(scatter_frame):,} periodic observations "
                "after deterministic down-sampling when necessary"
            ),
        )

        ax.legend(
            loc="upper left",
            fontsize=8.3,
        )

        current_best_path = (
            png_directory
            / "13_Current_vs_Best_Scatter.png"
        )

        save_figure(
            fig,
            current_best_path,
            left=0.12,
        )
        saved_figures.append(
            current_best_path
        )


# =============================================================================
# PLOT 14 — CURRENT-TO-BEST RELATIVE GAP DISTRIBUTION
# =============================================================================

if has_current_objective:
    gap_frame = periodic_convergence.dropna(
        subset=[
            "current_obj",
            "stream_best_so_far",
        ]
    ).copy()

    valid_denominator = (
        gap_frame["stream_best_so_far"] > 0
    )

    gap_frame = gap_frame[
        valid_denominator
    ].copy()

    gap_frame["current_gap_percent"] = (
        (
            gap_frame["current_obj"]
            - gap_frame["stream_best_so_far"]
        )
        / gap_frame["stream_best_so_far"]
        * 100.0
    )

    finite_gap = gap_frame[
        "current_gap_percent"
    ].replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()

    if not finite_gap.empty:
        robust_upper = max(
            0.1,
            float(
                finite_gap.quantile(0.995)
            ),
        )

        plotted_gap = finite_gap.clip(
            lower=0.0,
            upper=robust_upper,
        )

        fig, ax = plt.subplots(
            figsize=(10.8, 6.2)
        )

        ax.hist(
            plotted_gap,
            bins=48,
            color=COLORS["cyan"],
            alpha=0.88,
            edgecolor="white",
            linewidth=0.35,
        )

        ax.axvline(
            float(plotted_gap.median()),
            color=COLORS["navy"],
            linewidth=1.5,
            linestyle=(0, (5, 4)),
            label=(
                f"Median = "
                f"{float(plotted_gap.median()):.3f}%"
            ),
        )

        ax.set_xlabel(
            "Current objective gap above search-stream best-so-far (%)"
        )
        ax.set_ylabel("Periodic observations")
        style_axis(
            ax,
            grid_axis="y",
        )

        add_figure_header(
            fig,
            "Distribution of search excursions",
            (
                "Right tail is clipped only for visualization at "
                "the empirical 99.5th percentile"
            ),
        )

        ax.legend(
            loc="upper right",
            fontsize=8.3,
        )

        gap_distribution_path = (
            png_directory
            / "14_Current_Gap_Distribution.png"
        )

        save_figure(
            fig,
            gap_distribution_path,
        )
        saved_figures.append(
            gap_distribution_path
        )


# =============================================================================
# PLOT 15 — ALGORITHM-CANDIDATE OBJECTIVE COMPARISON
# =============================================================================

if not algorithm_comparison.empty:
    algorithm_plot = (
        algorithm_comparison
        .dropna(subset=["objective"])
        .sort_values(
            "objective",
            ascending=True,
        )
        .copy()
    )

    if not algorithm_plot.empty:
        fig_height = max(
            4.8,
            0.52 * len(algorithm_plot) + 2.3,
        )

        fig, ax = plt.subplots(
            figsize=(10.8, fig_height)
        )

        positions = np.arange(
            len(algorithm_plot)
        )

        bar_colors = [
            (
                COLORS["teal"]
                if name == "Final"
                else COLORS["blue"]
            )
            for name in algorithm_plot[
                "algorithm"
            ]
        ]

        bars = ax.barh(
            positions,
            algorithm_plot["objective"],
            color=bar_colors,
            alpha=0.90,
        )

        ax.set_yticks(positions)
        ax.set_yticklabels(
            algorithm_plot[
                "algorithm"
            ].astype(str)
        )
        ax.invert_yaxis()
        ax.set_xlabel(
            f"Objective ({objective_mode})"
        )
        ax.set_ylabel("Candidate / algorithm")
        ax.xaxis.set_major_formatter(
            FuncFormatter(format_objective)
        )
        style_axis(
            ax,
            grid_axis="x",
        )

        best_candidate = float(
            algorithm_plot[
                "objective"
            ].min()
        )
        worst_candidate = float(
            algorithm_plot[
                "objective"
            ].max()
        )

        span = max(
            worst_candidate - best_candidate,
            abs(best_candidate) * 0.01,
            1.0,
        )

        ax.set_xlim(
            max(
                0.0,
                best_candidate - 0.16 * span,
            ),
            worst_candidate + 0.22 * span,
        )

        for bar, value in zip(
            bars,
            algorithm_plot["objective"],
        ):
            ax.text(
                float(value),
                bar.get_y()
                + bar.get_height() / 2,
                f"  {float(value):,.3f}",
                va="center",
                fontsize=8.2,
                color=COLORS["slate"],
            )

        add_figure_header(
            fig,
            "Candidate objective comparison parsed from solver output",
            (
                "Final pipeline result is highlighted in teal; "
                "lower is better"
            ),
        )

        algorithm_path = (
            png_directory
            / "15_Algorithm_Objective_Comparison.png"
        )

        save_figure(
            fig,
            algorithm_path,
            left=0.16,
        )
        saved_figures.append(
            algorithm_path
        )


# =============================================================================
# PLOT 16 — FINAL TIME COMPOSITION
# =============================================================================

if selected_summary_row is not None:
    time_components = [
        (
            "Travel",
            safe_float(
                selected_summary_row.get(
                    "travel_time_s"
                )
            ),
        ),
        (
            "Service",
            safe_float(
                selected_summary_row.get(
                    "service_time_s"
                )
            ),
        ),
        (
            "Waiting",
            safe_float(
                selected_summary_row.get(
                    "waiting_s"
                )
            ),
        ),
        (
            "Lateness",
            safe_float(
                selected_summary_row.get(
                    "lateness_s"
                )
            ),
        ),
    ]

    time_components = [
        (label, value)
        for label, value in time_components
        if value is not None
        and value >= 0
    ]

    if time_components:
        labels = [
            label
            for label, _ in time_components
        ]
        values = np.array(
            [
                value
                for _, value in time_components
            ],
            dtype=float,
        )

        fig, ax = plt.subplots(
            figsize=(10.8, 5.8)
        )

        left = 0.0
        component_colors = [
            COLORS["blue"],
            COLORS["teal"],
            COLORS["light_slate"],
            COLORS["danger"],
        ]

        for label, value, color in zip(
            labels,
            values,
            component_colors,
        ):
            ax.barh(
                ["Final solution"],
                [value],
                left=left,
                color=color,
                label=(
                    f"{label}: {value:,.2f} s"
                ),
            )
            left += value

        ax.set_xlabel("Cumulative route time (s)")
        ax.set_ylabel("")
        ax.xaxis.set_major_formatter(
            FuncFormatter(format_objective)
        )
        style_axis(
            ax,
            grid_axis="x",
        )

        add_figure_header(
            fig,
            "Final route-time composition",
            (
                "Travel, service, waiting, and lateness are "
                "kept in the same physical unit"
            ),
        )

        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.13),
            ncol=2,
            fontsize=8.2,
        )

        time_composition_path = (
            png_directory
            / "16_Final_Time_Composition.png"
        )

        save_figure(
            fig,
            time_composition_path,
            bottom=0.22,
        )
        saved_figures.append(
            time_composition_path
        )


# =============================================================================
# PLOT 17 — WORKER GAP TO FINAL PIPELINE RESULT
# =============================================================================

if not worker_summary.empty:
    worker_gap = worker_summary.copy()

    worker_gap["gap_to_pipeline_percent"] = (
        (
            worker_gap["best_obj"]
            - final_global_objective
        )
        / final_global_objective
        * 100.0
        if final_global_objective != 0
        else 0.0
    )

    worker_gap = worker_gap.sort_values(
        "gap_to_pipeline_percent",
        ascending=True,
    )

    fig_height = max(
        4.8,
        0.43 * len(worker_gap) + 2.3,
    )

    fig, ax = plt.subplots(
        figsize=(10.8, fig_height)
    )

    positions = np.arange(
        len(worker_gap)
    )

    bars = ax.barh(
        positions,
        worker_gap[
            "gap_to_pipeline_percent"
        ],
        color=COLORS["amber"],
        alpha=0.88,
    )

    ax.set_yticks(positions)
    ax.set_yticklabels(
        worker_gap["seed"].astype(str)
    )
    ax.invert_yaxis()
    ax.set_xlabel(
        "Gap above final pipeline objective (%)"
    )
    ax.set_ylabel("Internal worker seed")
    style_axis(
        ax,
        grid_axis="x",
    )

    for bar, value in zip(
        bars,
        worker_gap[
            "gap_to_pipeline_percent"
        ],
    ):
        ax.text(
            float(value),
            bar.get_y()
            + bar.get_height() / 2,
            f"  {float(value):.3f}%",
            va="center",
            fontsize=8.0,
            color=COLORS["slate"],
        )

    add_figure_header(
        fig,
        "Worker gap to final pipeline result",
        (
            "Quantifies the value added after or across the "
            "internal worker searches"
        ),
    )

    worker_gap_path = (
        png_directory
        / "17_Worker_Gap_to_Final.png"
    )

    save_figure(
        fig,
        worker_gap_path,
        left=0.14,
    )
    saved_figures.append(
        worker_gap_path
    )


# =============================================================================
# PLOT 18 — WORKER IMPROVEMENT PERCENTAGE
# =============================================================================

if not worker_summary.empty:
    worker_improvement = worker_summary.sort_values(
        "improvement_percent",
        ascending=True,
    )

    fig_height = max(
        4.8,
        0.43 * len(worker_improvement) + 2.3,
    )

    fig, ax = plt.subplots(
        figsize=(10.8, fig_height)
    )

    positions = np.arange(
        len(worker_improvement)
    )

    bars = ax.barh(
        positions,
        worker_improvement[
            "improvement_percent"
        ],
        color=COLORS["teal"],
        alpha=0.88,
    )

    ax.set_yticks(positions)
    ax.set_yticklabels(
        worker_improvement[
            "seed"
        ].astype(str)
    )
    ax.invert_yaxis()
    ax.set_xlabel(
        "Improvement within worker (%)"
    )
    ax.set_ylabel("Internal worker seed")
    style_axis(
        ax,
        grid_axis="x",
    )

    for bar, value in zip(
        bars,
        worker_improvement[
            "improvement_percent"
        ],
    ):
        ax.text(
            float(value),
            bar.get_y()
            + bar.get_height() / 2,
            f"  {float(value):.3f}%",
            va="center",
            fontsize=8.0,
            color=COLORS["slate"],
        )

    add_figure_header(
        fig,
        "Objective improvement achieved by each worker",
        (
            "Measured from each worker's first logged best "
            "to its final best-so-far"
        ),
    )

    worker_improvement_path = (
        png_directory
        / "18_Worker_Improvement_Percent.png"
    )

    save_figure(
        fig,
        worker_improvement_path,
        left=0.14,
    )
    saved_figures.append(
        worker_improvement_path
    )


# =============================================================================
# PLOT 19 — EVENT TIMELINE
# =============================================================================

event_timeline = convergence[
    [
        "time_s",
        "event",
        "seed",
    ]
].dropna(
    subset=[
        "time_s",
        "event",
    ]
).copy()

if not event_timeline.empty:
    if len(event_timeline) > 60_000:
        step = int(
            math.ceil(
                len(event_timeline) / 60_000
            )
        )
        event_timeline = event_timeline.iloc[
            ::step
        ].copy()

    event_names = (
        event_timeline["event"]
        .astype(str)
        .value_counts()
        .index
        .tolist()
    )

    event_to_y = {
        event_name: index
        for index, event_name
        in enumerate(event_names)
    }

    event_timeline["event_y"] = (
        event_timeline["event"]
        .astype(str)
        .map(event_to_y)
    )

    event_color_map = {
        "periodic": COLORS["light_slate"],
        "improvement": COLORS["teal"],
        "final_refinement": COLORS["blue"],
        "best_checkpoint": COLORS["cyan"],
    }

    fig, ax = plt.subplots(
        figsize=(12.2, 5.9)
    )

    for event_name, group in event_timeline.groupby(
        "event"
    ):
        ax.scatter(
            group["time_s"],
            group["event_y"],
            s=8,
            alpha=(
                0.16
                if str(event_name).lower()
                == "periodic"
                else 0.72
            ),
            color=event_color_map.get(
                str(event_name).lower(),
                COLORS["amber"],
            ),
            edgecolors="none",
            rasterized=True,
            label=str(event_name),
        )

    ax.set_yticks(
        list(event_to_y.values())
    )
    ax.set_yticklabels(
        list(event_to_y.keys())
    )
    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Logged event")
    style_axis(
        ax,
        grid_axis="x",
    )

    add_figure_header(
        fig,
        "Convergence-event timeline",
        (
            "Shows where periodic checkpoints, improvements, "
            "and final refinement occur"
        ),
    )

    if len(event_names) <= 10:
        ax.legend(
            loc="upper right",
            fontsize=7.8,
        )

    event_timeline_path = (
        png_directory
        / "19_Event_Timeline.png"
    )

    save_figure(
        fig,
        event_timeline_path,
        left=0.15,
    )
    saved_figures.append(
        event_timeline_path
    )


# =============================================================================
# PLOT 20 — TEMPERATURE VS ACCEPTANCE RATE
# =============================================================================

if has_temperature and has_acceptance:
    relation_frame = periodic_convergence.dropna(
        subset=[
            "temp",
            "smoothed_interval_acceptance_rate",
        ]
    ).copy()

    relation_frame = relation_frame[
        relation_frame["temp"] > 0
    ]

    if len(relation_frame) > 50_000:
        step = int(
            math.ceil(
                len(relation_frame) / 50_000
            )
        )
        relation_frame = relation_frame.iloc[
            ::step
        ].copy()

    if not relation_frame.empty:
        fig, ax = plt.subplots(
            figsize=(8.8, 7.0)
        )

        for (
            search_stream,
            group,
        ) in relation_frame.groupby(
            "search_stream",
            sort=True,
        ):
            seed = int(
                group["seed"].iloc[0]
            )
            stream_index = int(
                group[
                    "stream_index"
                ].iloc[0]
            )

            ax.scatter(
                group["temp"],
                group["smoothed_interval_acceptance_rate"],
                s=9,
                alpha=0.13,
                color=search_seed_colors[
                    seed
                ],
                marker=SEARCH_STREAM_MARKERS.get(
                    stream_index,
                    "o",
                ),
                edgecolors="none",
                rasterized=True,
            )

        positive_temp = relation_frame[
            "temp"
        ]

        if (
            positive_temp.max()
            / max(
                positive_temp.min(),
                1e-300,
            )
            > 1000
        ):
            ax.set_xscale("log")

        ax.set_xlabel("SA temperature")
        ax.set_ylabel("Local interval acceptance rate")
        style_axis(ax)

        add_figure_header(
            fig,
            "Temperature–acceptance relationship",
            (
                f"{len(relation_frame):,} periodic observations; "
                "useful for diagnosing cooling aggressiveness"
            ),
        )

        temperature_acceptance_path = (
            png_directory
            / "20_Temperature_vs_Acceptance.png"
        )

        save_figure(
            fig,
            temperature_acceptance_path,
            left=0.11,
        )
        saved_figures.append(
            temperature_acceptance_path
        )


# Update the analysis JSON now that the complete graph suite is known.
analysis_summary[
    "generated_figure_count"
] = int(len(saved_figures))

analysis_summary[
    "available_diagnostics"
] = {
    "temperature": bool(has_temperature),
    "acceptance_rate": bool(has_acceptance),
    "stagnation": bool(has_stagnation),
    "move_counts": bool(has_move_counts),
    "current_objective": bool(
        has_current_objective
    ),
    "algorithm_comparison": bool(
        not algorithm_comparison.empty
    ),
    "run_summary": bool(
        selected_summary_row is not None
    ),
    "search_stream_reconstruction": True,
    "reconstructed_stream_count": int(
        periodic_convergence[
            "search_stream"
        ].nunique()
    ),
}

write_json(
    json_directory / "AnalysisSummary.json",
    analysis_summary,
)


# =============================================================================
# FIGURE MANIFEST, ZIP, AND INLINE OUTPUT
# =============================================================================

figure_descriptions = {
    "01_Publication_Convergence.png": (
        "Primary Chapter 7 convergence figure. Combines worker logs, "
        "Anytime improvements, and the parsed final solver result."
    ),
    "02_Publication_Convergence_Zoom.png": (
        "Automatic late-stage focus with safe data-derived limits."
    ),
    "03_Global_Improvement_Percent.png": (
        "Cumulative objective improvement from the first accepted solution."
    ),
    "04_Worker_Search_Diagnostic.png": (
        "Current-objective and worker-best traces with robust spike clipping."
    ),
    "05_Worker_Final_Objectives.png": (
        "Best objective reached by each internal worker."
    ),
    "06_Worker_Time_to_Best.png": (
        "Time required for each internal worker to reach its best result."
    ),
    "07_Search_Stream_Reconstruction.png": (
        "Lane timeline of exact C++ stream lifetimes, observation counts, and "
        "maximum iterations. Concurrent or restarted streams are never joined."
    ),
    "08_Event_Counts.png": (
        "Composition of periodic, improvement, and refinement log rows."
    ),
    "09_SA_Temperature_Decay.png": (
        "Raw per-stream SA temperatures aligned at each stream start. Lines "
        "break at gaps; identical schedules may overlap without invented offsets."
    ),
    "09B_SA_Normalized_Cooling_Profile.png": (
        "Wall-clock-normalized cooling traces plus a cross-stream median/IQR; "
        "empty observation bins are never interpolated."
    ),
    "10_Acceptance_Rate.png": (
        "Raw and five-sample-median acceptance traces for each seed, plus a "
        "reset-safe cross-stream median/IQR over comparable stream progress."
    ),
    "11_Stagnation_Counter.png": (
        "Reset-aware within-cycle stagnation traces, cross-stream median/IQR, "
        "and reset density. Counter drops are never connected by false lines."
    ),
    "12_Accepted_Attempted_Moves.png": (
        "Final accepted and attempted move counts by worker."
    ),
    "13_Current_vs_Best_Scatter.png": (
        "Relationship between current search state and worker best-so-far."
    ),
    "14_Current_Gap_Distribution.png": (
        "Distribution of current-objective excursions above worker best."
    ),
    "15_Algorithm_Objective_Comparison.png": (
        "Objective comparison parsed from the solver algorithm table."
    ),
    "16_Final_Time_Composition.png": (
        "Final travel, service, waiting, and lateness composition."
    ),
    "17_Worker_Gap_to_Final.png": (
        "Each worker's gap above the final full-pipeline result."
    ),
    "18_Worker_Improvement_Percent.png": (
        "Within-worker improvement from first to final best."
    ),
    "19_Event_Timeline.png": (
        "Timeline of periodic, improvement, and refinement events."
    ),
    "20_Temperature_vs_Acceptance.png": (
        "Relationship between SA temperature and move acceptance."
    ),
}

figure_manifest = pd.DataFrame(
    [
        {
            "figure": path.name,
            "description": figure_descriptions.get(
                path.name,
                "Convergence analysis figure.",
            ),
            "path": str(path),
        }
        for path in saved_figures
    ]
)

figure_manifest.to_csv(
    csv_directory / "FigureManifest.csv",
    index=False,
)

zip_path = (
    run_directory
    / "ConvergenceReport.zip"
)

if CREATE_ZIP:
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in output_directory.rglob("*"):
            if path.is_file():
                archive.write(
                    path,
                    path.relative_to(
                        output_directory.parent
                    ),
                )

print("\n" + "=" * 96)
print("CONVERGENCE ANALYSIS COMPLETE")
print("=" * 96)

for key, value in analysis_summary.items():
    if isinstance(value, float):
        print(f"{key:34s}: {value:.6f}")
    else:
        print(f"{key:34s}: {value}")

print(f"{'output_directory':34s}: {output_directory}")

if CREATE_ZIP:
    print(f"{'zip_report':34s}: {zip_path}")

print("\nPrimary Chapter 7 figures:")
print(
    " ",
    png_directory
    / "01_Publication_Convergence.png",
)
print(
    " ",
    png_directory
    / "02_Publication_Convergence_Zoom.png",
)

print(
    f"\nGenerated {len(saved_figures)} figures:"
)

for figure_path in saved_figures:
    print(" ", figure_path.name)

if DISPLAY_TABLES_INLINE:
    print("\nAnalysis summary:")
    display(
        pd.DataFrame(
            [
                {
                    "metric": key,
                    "value": value,
                }
                for key, value
                in analysis_summary.items()
            ]
        )
    )

    if not algorithm_comparison.empty:
        print("\nParsed algorithm comparison:")
        display(algorithm_comparison)

    if not worker_summary.empty:
        print("\nInternal worker summary:")
        display(worker_summary)

if (
    DISPLAY_FIGURES_INLINE
    and Image is not None
):
    if DISPLAY_ALL_FIGURES_INLINE:
        inline_figures = list(
            saved_figures
        )
    else:
        inline_figures = [
            png_directory
            / "01_Publication_Convergence.png",
            png_directory
            / "02_Publication_Convergence_Zoom.png",
            png_directory
            / "03_Global_Improvement_Percent.png",
            png_directory
            / "04_Worker_Search_Diagnostic.png",
        ]

    for path in inline_figures:
        if not path.exists():
            continue

        if Markdown is not None:
            display(
                Markdown(
                    f"### {path.stem}"
                )
            )

        display(
            Image(
                filename=str(path),
                width=1050,
            )
        )

print("\nRunner completed successfully. [EOF]")
