"""Rebuild repository figures from the frozen submission CSVs."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "svg.fonttype": "none"})

def rows(name):
    with (ROOT / "tables" / name).open(newline="") as f:
        return list(csv.DictReader(f))

def save(fig, name):
    fig.savefig(OUT / f"{name}.svg", facecolor="white", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)

r = rows("current_public_reference_gaps.csv")
assert len(r) == 18 and all(int(x["valid_seeds"]) == 3 for x in r)
assert all(x["contains_recovery"].lower() == "false" for x in r)
best = np.array([float(x["best_gap_to_reference_pct"]) for x in r])
mean = np.array([float(x["mean_gap_to_reference_pct"]) for x in r])
best[np.abs(best) < 1e-9] = 0
mean[np.abs(mean) < 1e-9] = 0
fig, ax = plt.subplots(figsize=(11, 9))
y = np.arange(len(r))
ax.hlines(y, best, mean, color="#d6e3ed", lw=4)
ax.scatter(mean, y, s=48, color="#b4c3d0", label="Mean of three seeds", zorder=3)
ax.scatter(best, y, s=65, color="#087e8b", label="Best of three seeds", zorder=4)
for i, x in enumerate(best):
    ax.annotate(f"{x:.2f}%", (x, i), xytext=(5, 8), textcoords="offset points",
                fontsize=9, color="#075c65")
ax.set_yticks(y, [x["instance"] for x in r])
ax.invert_yaxis()
ax.set_xlim(-.25, max(mean) + .75)
ax.set_xlabel("Distance gap to the retained reference (%) — lower is better")
ax.grid(axis="x", alpha=.15)
ax.set_axisbelow(True)
for boundary in [2.5, 8.5, 14.5]:
    ax.axhline(boundary, color="#e5e7eb", lw=1)
ax.legend(loc="lower right", frameon=False)
fig.suptitle("Current solver · public reference gaps", x=.12, ha="left", fontsize=21)
fig.text(.12, .925, f"18 instances · 3 seeds each · {best.mean():.2f}% mean best-of-three gap",
         fontsize=12, color="#465565")
fig.text(.12, .02, "Frozen benchmark Current; original results only. Reference costs use the package's common evaluator.\n"
         "Families: Augerat-A, Solomon, Gehring–Homberger-200, CVRPLIB-X. This is not an app-integration rerun.",
         fontsize=9, color="#465565")
fig.subplots_adjust(top=.89, bottom=.12, left=.15)
save(fig, "public_reference_gaps")

r = rows("osm_four_way_common_metric.csv")
assert len(r) == 4
fig, ax = plt.subplots(figsize=(11, 5.8))
x = np.arange(4)
colors = {"legacy": "#96a3b2", "v31": "#7b6ca8", "current": "#087e8b"}
labels = {"legacy": "Legacy", "v31": "V31", "current": "Current"}
for offset, solver in [(-.18, "legacy"), (0, "v31"), (.18, "current")]:
    base = np.array([float(z["or_tools_best_of_12_common_distance_m"]) for z in r])
    mid = np.array([float(z[f"{solver}_mean_m"]) for z in r]) / base * 100
    low = np.array([float(z[f"{solver}_best_m"]) for z in r]) / base * 100
    high = np.array([float(z[f"{solver}_worst_m"]) for z in r]) / base * 100
    ax.errorbar(x + offset, mid, yerr=[np.maximum(mid-low, 0), np.maximum(high-mid, 0)],
                fmt="o", ms=8, color=colors[solver], capsize=4,
                label=f"{labels[solver]} · mean and min–max of 3 seeds")
ax.axhline(100, color="#d37a36", ls="--", lw=1.5,
           label="OR-Tools · best of 12 configurations")
ax.set_xticks(x, ["50 customers", "100 customers", "300 customers", "450 customers"])
ax.set_ylabel("Route distance / OR-Tools reference (%)")
ax.grid(axis="y", alpha=.15)
ax.set_axisbelow(True)
ax.legend(loc="upper left", frameon=False, fontsize=10)
fig.suptitle("Directed-road routing · distance quality", x=.12, ha="left", fontsize=21)
fig.text(.12, .89, "100% = OR-Tools best-of-12 distance · lower is better", color="#465565")
fig.text(.12, .02, "Common evaluator; frozen software and inputs. Different aggregation: 3 seeds versus 12 OR-Tools configurations.\n"
         "This figure compares solution distance, not matched runtime, CPU cost, or measured field savings.",
         fontsize=9, color="#465565")
fig.subplots_adjust(top=.83, bottom=.19)
save(fig, "directed_road_quality")

print("Rebuilt 2 figures from retained CSVs; no benchmark execution.")
