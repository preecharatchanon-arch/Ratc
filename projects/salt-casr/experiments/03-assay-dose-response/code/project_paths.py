"""Repository input and output locations; scientific definitions live in the analysis modules."""
from pathlib import Path
EXPERIMENT=Path(__file__).resolve().parents[1]
PROJECT=EXPERIMENT.parent.parent
DATA=PROJECT/'data/saltiness'
RUN=EXPERIMENT/"runs/latest"
RUN.mkdir(parents=True,exist_ok=True)
ARCHIVE=PROJECT/"archives/casr-prior-reference"
