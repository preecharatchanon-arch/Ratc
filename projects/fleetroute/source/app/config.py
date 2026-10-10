from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(os.getenv("VRP_RUNTIME_DIR", BASE_DIR / "runtime")).resolve()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR = RUNTIME_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    startup_id: str = os.getenv("VRP_STARTUP_ID", "")
    app_name: str = os.getenv("VRP_APP_NAME", "FleetRoute Routing Workspace")
    app_token: str = os.getenv("VRP_APP_TOKEN", "")
    geocoder_url: str = os.getenv(
        "VRP_GEOCODER_URL", "https://nominatim.openstreetmap.org/search"
    )
    reverse_geocoder_url: str = os.getenv(
        "VRP_REVERSE_GEOCODER_URL", "https://nominatim.openstreetmap.org/reverse"
    )
    geocoder_user_agent: str = os.getenv(
        "VRP_GEOCODER_USER_AGENT",
        "FleetRoute-Routing-Workspace/1.0 (configure contact in production)",
    )
    geocoder_min_interval_s: float = float(
        os.getenv("VRP_GEOCODER_MIN_INTERVAL_S", "1.05")
    )
    database_path: Path = Path(
        os.getenv("VRP_DATABASE_PATH", RUNTIME_DIR / "fleetroute.sqlite3")
    )
    solver_cpp: Path = Path(os.getenv("VRP_SOLVER_CPP", BASE_DIR / "solver.cpp"))
    solver_bin: Path = Path(os.getenv("VRP_SOLVER_BIN", RUNTIME_DIR / "solver"))
    solver_provenance: Path = Path(os.getenv("VRP_SOLVER_PROVENANCE", BASE_DIR / "solver_provenance.json"))
    cluster_cpp: Path = Path(os.getenv("VRP_CLUSTER_CPP", BASE_DIR / "cluster.cpp"))
    cluster_bin: Path = Path(os.getenv("VRP_CLUSTER_BIN", RUNTIME_DIR / "cluster"))

    osm_data_dir: Path = Path(
        os.getenv("VRP_OSM_DATA_DIR", RUNTIME_DIR / "osm-data")
    )
    network_graphml: Path = Path(
        os.getenv("VRP_NETWORK_GRAPHML", RUNTIME_DIR / "network.graphml")
    )
    network_pickle: Path = Path(
        os.getenv("VRP_NETWORK_PICKLE", RUNTIME_DIR / "network.fast.pkl")
    )
    network_overview_png: Path = Path(
        os.getenv("VRP_NETWORK_OVERVIEW", ARTIFACTS_DIR / "network_overview.png")
    )
    input_txt: Path = Path(os.getenv("VRP_INPUT_TXT", RUNTIME_DIR / "input.txt"))
    dataset_json: Path = Path(
        os.getenv("VRP_DATASET_JSON", RUNTIME_DIR / "dataset.json")
    )
    dataset_summary_json: Path = Path(
        os.getenv("VRP_DATASET_SUMMARY_JSON", RUNTIME_DIR / "dataset_summary.json")
    )
    clusters_csv: Path = Path(
        os.getenv("VRP_CLUSTERS_CSV", RUNTIME_DIR / "clusters.csv")
    )
    cluster_summary_csv: Path = Path(
        os.getenv("VRP_CLUSTER_SUMMARY", RUNTIME_DIR / "cluster_summary.csv")
    )
    cluster_timing_csv: Path = Path(
        os.getenv("VRP_CLUSTER_TIMING", RUNTIME_DIR / "cluster_timing.csv")
    )
    cluster_preview_png: Path = Path(
        os.getenv("VRP_CLUSTER_PREVIEW", ARTIFACTS_DIR / "selected_clustering.png")
    )
    solver_output: Path = Path(
        os.getenv("VRP_SOLVER_OUTPUT", RUNTIME_DIR / "solver_output.txt")
    )
    solver_stderr: Path = Path(
        os.getenv("VRP_SOLVER_STDERR", RUNTIME_DIR / "solver_stderr.txt")
    )
    solver_invocation_json: Path = Path(
        os.getenv("VRP_SOLVER_INVOCATION", RUNTIME_DIR / "solver_invocation.json")
    )
    convergence_csv: Path = Path(
        os.getenv("VRP_CONVERGENCE", RUNTIME_DIR / "convergence.csv")
    )
    run_summary_csv: Path = Path(
        os.getenv("VRP_RUN_SUMMARY", RUNTIME_DIR / "run_summary.csv")
    )
    routes_json: Path = Path(
        os.getenv("VRP_ROUTES_JSON", RUNTIME_DIR / "routes.json")
    )
    convergence_report_dir: Path = Path(
        os.getenv("VRP_CONVERGENCE_REPORT", RUNTIME_DIR / "ConvergenceReport")
    )
    clustering_benchmark_dir: Path = Path(
        os.getenv("VRP_CLUSTERING_BENCHMARK", RUNTIME_DIR / "Clustering")
    )
    driver_package_zip: Path = Path(
        os.getenv("VRP_DRIVER_PACKAGE", ARTIFACTS_DIR / "Driver_Operations_Package.zip")
    )
    run_package_zip: Path = Path(
        os.getenv("VRP_RUN_PACKAGE", ARTIFACTS_DIR / "FleetRoute_Run_Evidence.zip")
    )
    convergence_analyzer: Path = BASE_DIR / "tools" / "convergence_analyzer.py"
    clustering_benchmark_runner: Path = BASE_DIR / "tools" / "clustering_benchmark.py"


settings = Settings()
