#!/usr/bin/env python3
"""
Results tables and figures for the GhostMinion reproduction.

Reads the gem5 stats files straight from the SPEC CPU2006 run directories
(and, optionally, the Parsec CSV written on the cluster) and produces:

  spec06_raw.csv            sim_seconds and sim_insts for every benchmark and
                            configuration found on disk (long format)
  spec06_results.csv        per-benchmark overhead (%) for each configuration,
                            computed from the raw times, 3 decimals
  parsec_results.csv        Parsec ROI times and overhead (%), 3 decimals
                            (only with --parsec-csv)
  fig1_spec06_overhead      per-benchmark overhead, geomean, paper reference
  fig2_prefetcher_ablation  lbm / libquantum with and without --prefetch_ordered
  fig3_libquantum_breakdown libquantum overhead as each mechanism is added
  fig4_parsec_overhead      Parsec per-benchmark overhead and geomean
                            (only with --parsec-csv)

All geometric means are computed from the raw time ratios, never from the
rounded percentages. Figures show 2 decimals, CSV files 3.

Usage:
  python3 plot_ghostminion.py <SPEC root> [--out plots] [--parsec-csv FILE]

<SPEC root> is the directory that contains one folder per benchmark
(e.g. SPEC/benchspec/CPU2006 on the cluster, or a local copy with the
same layout: <bench>/run/run_base_ref_aarch64.0000/m5out*/...).
"""

import argparse
import csv
import glob
import math
import os

import matplotlib
matplotlib.use("Agg")  # no display needed on the cluster
import matplotlib.pyplot as plt
from matplotlib import colors

RUN_DIR = "run/run_base_ref_aarch64.0000"
PAPER_GEOMEAN = 2.5   # % SPEC CPU2006 geomean reported in the paper
PAPER_PARSEC = 0.0    # % the paper reports no measurable overhead on Parsec
EXPECTED_INSTS = 1.99e9  # every SPEC run simulates ~2B instructions in total

# Configuration name -> stats file, relative to the benchmark's run directory.
# "baseline" and "full" come from the upstream run script (both in m5out/);
# the other three are the ablation runs, each in its own output directory.
CONFIGS = [
    ("baseline", "m5out/statsno.txt"),
    ("full",     "m5out/statsghostminion.txt"),
    ("nopf",     "m5out_nopf/stats.txt"),
    ("dminion",  "m5out_dminion/stats.txt"),
    ("coher",    "m5out_coher/stats.txt"),
]
TEST_CONFIGS = [name for name, _ in CONFIGS if name != "baseline"]

# Blue palette, light -> dark
BLUE_LIGHT = "#c6dbef"
BLUE_MID = "#6baed6"
BLUE = "#2171b5"
BLUE_DARK = "#08306b"
GREY = "#7f7f7f"


# ----------------------------------------------------------------------------
# Reading gem5 stats
# ----------------------------------------------------------------------------
def read_stat(path, name):
    """First value of a stat in a gem5 stats.txt (None if missing or empty)."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == name:
                return float(parts[1])
    return None


def overhead(base_s, test_s):
    """Slowdown in % (positive = slower than baseline)."""
    if base_s is None or test_s is None:
        return None
    return (test_s / base_s - 1.0) * 100.0


def geomean_ratio(pairs):
    """Geometric mean of test/base time ratios, returned as % slowdown.

    `pairs` is a list of (base_seconds, test_seconds); entries with a
    missing value are ignored.
    """
    logs = [math.log(t / b) for b, t in pairs if b is not None and t is not None]
    return (math.exp(sum(logs) / len(logs)) - 1.0) * 100.0


def collect(spec_root):
    """One dict per benchmark: raw sim_seconds / sim_insts for every config."""
    results = []
    for bench_dir in sorted(glob.glob(os.path.join(spec_root, "*"))):
        run = os.path.join(bench_dir, RUN_DIR)
        if not os.path.isfile(os.path.join(run, CONFIGS[0][1])):
            continue  # no baseline -> not a benchmark we ran
        row = {"bench": os.path.basename(bench_dir)}
        for name, rel in CONFIGS:
            path = os.path.join(run, rel)
            row[name] = {
                "file": rel,
                "sim_seconds": read_stat(path, "sim_seconds"),
                "sim_insts": read_stat(path, "sim_insts"),
            }
        results.append(row)
    return results


def ovh(row, cfg):
    """Overhead (%) of configuration `cfg` for one benchmark row."""
    return overhead(row["baseline"]["sim_seconds"], row[cfg]["sim_seconds"])


def sanity_check(results):
    """Warn about short runs and about configs that ran a different workload."""
    for r in results:
        base_insts = r["baseline"]["sim_insts"]
        if base_insts is None or base_insts < EXPECTED_INSTS:
            print(f"  WARNING: {r['bench']} baseline has {base_insts} instructions")
            continue
        for cfg in TEST_CONFIGS:
            insts = r[cfg]["sim_insts"]
            if insts is not None and abs(insts / base_insts - 1.0) > 0.01:
                print(f"  WARNING: {r['bench']} {cfg} sim_insts differs from "
                      f"baseline by {100 * (insts / base_insts - 1):+.2f}%")


# ----------------------------------------------------------------------------
# CSV output
# ----------------------------------------------------------------------------
def fmt3(v):
    return "" if v is None else f"{v:.3f}"


def write_raw_csv(results, out_dir):
    """Long format: one line per (benchmark, configuration) that exists."""
    path = os.path.join(out_dir, "spec06_raw.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["bench", "config", "stats_file", "sim_seconds", "sim_insts"])
        for r in results:
            for name, _ in CONFIGS:
                c = r[name]
                if c["sim_seconds"] is None:
                    continue
                w.writerow([r["bench"], name, c["file"],
                            repr(c["sim_seconds"]), int(c["sim_insts"])])
    print("  wrote spec06_raw.csv")


def write_results_csv(results, out_dir):
    """Wide format: overhead (%) per benchmark, empty where a run is missing."""
    path = os.path.join(out_dir, "spec06_results.csv")
    cols = {
        "full": "overhead_full_pct",
        "nopf": "overhead_no_prefetch_ordered_pct",
        "dminion": "overhead_dminion_only_pct",
        "coher": "overhead_dminion_coher_pct",
    }
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["bench"] + list(cols.values()))
        for r in results:
            w.writerow([r["bench"]] + [fmt3(ovh(r, c)) for c in cols])
    print("  wrote spec06_results.csv")


def read_parsec(csv_path):
    """Parsec CSV from the cluster: bench,base_roi_s,gm_roi_s[,overhead_pct].

    The overhead column, if present, is ignored and recomputed from the times.
    """
    rows = []
    with open(csv_path, newline="") as f:
        for rec in csv.DictReader(f):
            rows.append((rec["bench"], float(rec["base_roi_s"]), float(rec["gm_roi_s"])))
    return rows


def write_parsec_csv(rows, out_dir):
    path = os.path.join(out_dir, "parsec_results.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["bench", "base_roi_s", "gm_roi_s", "overhead_pct"])
        for bench, b, g in rows:
            w.writerow([bench, f"{b:.6f}", f"{g:.6f}", fmt3(overhead(b, g))])
    print("  wrote parsec_results.csv")


# ----------------------------------------------------------------------------
# Plot helpers
# ----------------------------------------------------------------------------
def style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axhline(0, color="black", linewidth=0.8)


def label_bars(ax, bars, values, fmt="{:.2f}%", fontsize=8):
    for bar, v in zip(bars, values):
        y = bar.get_height()
        va = "bottom" if v >= 0 else "top"
        offset = 0.3 if v >= 0 else -0.3
        ax.text(bar.get_x() + bar.get_width() / 2, y + offset, fmt.format(v),
                ha="center", va=va, fontsize=fontsize)


def save(fig, out_dir, name):
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out_dir, f"{name}.{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}.png / .pdf")


def short(bench):
    """'470.lbm' -> 'lbm'"""
    return bench.split(".", 1)[-1]


# ----------------------------------------------------------------------------
# Figure 1: per-benchmark overhead
# ----------------------------------------------------------------------------
def fig_overhead(results, out_dir):
    rows = [r for r in results if ovh(r, "full") is not None]
    rows.sort(key=lambda r: ovh(r, "full"), reverse=True)
    names = [short(r["bench"]) for r in rows]
    vals = [ovh(r, "full") for r in rows]
    gm = geomean_ratio([(r["baseline"]["sim_seconds"], r["full"]["sim_seconds"]) for r in rows])

    # Shade each bar by its overhead (light blue = small, dark blue = large)
    norm = colors.Normalize(vmin=min(0, min(vals)), vmax=max(vals))
    cmap = plt.get_cmap("Blues")
    bar_colors = [cmap(0.3 + 0.7 * norm(v)) for v in vals]

    names.append("geomean")
    vals.append(gm)
    bar_colors.append(BLUE_DARK)

    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = range(len(names))
    bars = ax.bar(x, vals, color=bar_colors, edgecolor="none", width=0.75)
    style(ax)
    label_bars(ax, bars, vals, fontsize=6.5)

    ax.axhline(PAPER_GEOMEAN, color=GREY, linestyle="--", linewidth=1,
               label=f"Paper geomean ({PAPER_GEOMEAN}%)")
    ax.axhline(gm, color=BLUE_DARK, linestyle=":", linewidth=1,
               label=f"This work geomean ({gm:.2f}%)")

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=60, ha="right", fontsize=9)
    ax.set_ylabel("Slowdown vs. baseline (%)")
    ax.set_title("GhostMinion overhead on SPEC CPU2006 (1B instructions after 1B fast-forward)")
    ax.legend(frameon=False, loc="upper right")
    save(fig, out_dir, "fig1_spec06_overhead")
    return gm, rows


# ----------------------------------------------------------------------------
# Figure 2: with vs. without ordered prefetcher
# ----------------------------------------------------------------------------
def fig_prefetcher(results, out_dir):
    rows = [r for r in results if ovh(r, "nopf") is not None and ovh(r, "full") is not None]
    if not rows:
        print("  skipped fig2 (no m5out_nopf results)")
        return
    names = [short(r["bench"]) for r in rows]
    full = [ovh(r, "full") for r in rows]
    nopf = [ovh(r, "nopf") for r in rows]

    fig, ax = plt.subplots(figsize=(6, 4))
    w = 0.36
    x = list(range(len(rows)))
    b1 = ax.bar([i - w / 2 for i in x], full, w, color=BLUE_DARK, label="Full GhostMinion")
    b2 = ax.bar([i + w / 2 for i in x], nopf, w, color=BLUE_MID,
                label="Without --prefetch_ordered (diagnostic only, not secure)")
    style(ax)
    label_bars(ax, b1, full)
    label_bars(ax, b2, nopf)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Slowdown vs. baseline (%)")
    ax.set_title("Cost of committed-only prefetcher training")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_ylim(bottom=min(0, min(nopf + full)) - 3, top=max(full) * 1.35)
    save(fig, out_dir, "fig2_prefetcher_ablation")


# ----------------------------------------------------------------------------
# Figure 3: libquantum breakdown
# ----------------------------------------------------------------------------
def fig_breakdown(results, out_dir, bench="462.libquantum"):
    r = next((r for r in results if r["bench"] == bench), None)
    if r is None or any(ovh(r, c) is None for c in ("dminion", "coher", "nopf", "full")):
        print(f"  skipped fig3 (no complete breakdown results for {bench})")
        return
    # "nopf" (everything except --prefetch_ordered) is exactly the
    # "D-Minion + coherence + I-Minion" step of the incremental breakdown.
    steps = [
        ("D-Minion\n(+TimeGuarding,\nLeapfrogging)", ovh(r, "dminion")),
        ("+ Coherence", ovh(r, "coher")),
        ("+ I-Minion", ovh(r, "nopf")),
        ("+ Ordered prefetcher\n(full GhostMinion)", ovh(r, "full")),
    ]
    labels = [s[0] for s in steps]
    vals = [s[1] for s in steps]
    shades = [BLUE_LIGHT, BLUE_MID, BLUE, BLUE_DARK]

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(range(len(vals)), vals, color=shades, width=0.6)
    style(ax)
    label_bars(ax, bars, vals)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Slowdown vs. baseline (%)")
    ax.set_title(f"{short(bench)}: overhead as each mechanism is enabled")
    ax.set_ylim(bottom=min(0, min(vals)) - 3, top=max(vals) * 1.2)
    save(fig, out_dir, "fig3_libquantum_breakdown")


# ----------------------------------------------------------------------------
# Figure 4: Parsec
# ----------------------------------------------------------------------------
def fig_parsec(rows, out_dir):
    if not rows:
        print("  skipped fig4 (empty Parsec CSV)")
        return None
    rows = sorted(rows, key=lambda r: overhead(r[1], r[2]), reverse=True)
    names = [r[0] for r in rows]
    vals = [overhead(b, g) for _, b, g in rows]
    gm = geomean_ratio([(b, g) for _, b, g in rows])

    norm = colors.Normalize(vmin=min(vals), vmax=max(vals))
    cmap = plt.get_cmap("Blues")
    bar_colors = [cmap(0.3 + 0.6 * norm(v)) for v in vals]
    names.append("geomean")
    vals.append(gm)
    bar_colors.append(BLUE_DARK)

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(range(len(names)), vals, color=bar_colors, width=0.65)
    style(ax)
    label_bars(ax, bars, vals)
    ax.axhline(PAPER_PARSEC, color=GREY, linestyle="--", linewidth=1,
               label=f"Paper (~{PAPER_PARSEC:.0f}%)")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylabel("Slowdown vs. baseline (%)")
    ax.set_title("GhostMinion overhead on Parsec (sim-medium, 4 threads, full-system)")
    ax.set_ylim(min(vals) - 2, max(vals) + 2)
    ax.legend(frameon=False, loc="upper right")
    save(fig, out_dir, "fig4_parsec_overhead")
    return gm


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec_root", help="directory with one folder per SPEC benchmark")
    ap.add_argument("--out", default="plots", help="output directory")
    ap.add_argument("--parsec-csv", help="parsec_results.csv from run_parsec/ (optional)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    results = collect(args.spec_root)
    print(f"Found {len(results)} benchmarks with baseline stats")
    for cfg in TEST_CONFIGS:
        n = sum(r[cfg]["sim_seconds"] is not None for r in results)
        print(f"  {cfg:8s}: {n} benchmark(s)")
    sanity_check(results)

    write_raw_csv(results, args.out)
    write_results_csv(results, args.out)

    gm, rows = fig_overhead(results, args.out)
    excl = ("462.libquantum", "470.lbm")
    gm_excl = geomean_ratio([(r["baseline"]["sim_seconds"], r["full"]["sim_seconds"])
                             for r in rows if r["bench"] not in excl])
    full = [ovh(r, "full") for r in rows]
    print(f"SPEC geomean overhead: {gm:.2f}% over {len(rows)} benchmarks (paper: {PAPER_GEOMEAN}%)")
    print(f"  without lbm, libquantum: {gm_excl:.2f}%")
    print(f"  below 5%: {sum(v < 5 for v in full)}, below 1%: {sum(v < 1 for v in full)}")

    fig_prefetcher(results, args.out)
    fig_breakdown(results, args.out)

    if args.parsec_csv:
        prow = read_parsec(args.parsec_csv)
        write_parsec_csv(prow, args.out)
        pgm = fig_parsec(prow, args.out)
        if pgm is not None:
            print(f"Parsec geomean overhead: {pgm:.2f}% (paper: ~{PAPER_PARSEC:.0f}%)")


if __name__ == "__main__":
    main()
