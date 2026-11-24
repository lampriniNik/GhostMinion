#!/usr/bin/env bash
# Region-of-interest time of each Parsec benchmark, baseline vs. GhostMinion.
#
# Reads the stats written by the artefact's scripts/run_parsec.sh and writes
# $ARTEFACT/run_parsec/parsec_results.csv, the input of
# analysis/plot_ghostminion.py --parsec-csv.
#
# Each stats file has two dumps: the region of interest, then a cumulative one
# up to the end of the simulation. Only the first is used (grep -m1).
#
# Usage:
#     source env/env.sh
#     scripts/collect_parsec.sh

set -euo pipefail
: "${ARTEFACT:?set ARTEFACT (source env/env.sh)}"

cd "$ARTEFACT/run_parsec"
out=parsec_results.csv

echo "bench,base_roi_s,gm_roi_s,overhead_pct" > $out
for b in blackscholes canneal ferret fluidanimate freqmine streamcluster swaptions; do
  base=$b/m5out/statsno.txt
  gm=$b/m5out/statsghostminion.txt
  # freqmine and streamcluster were re-run on their own, into m5out_gm/
  # (see docs/setup_cslab.md); use that output when it exists
  [ -s $b/m5out_gm/stats.txt ] && gm=$b/m5out_gm/stats.txt

  t0=$(grep -m1 '^sim_seconds' $base | awk '{print $2}')
  t1=$(grep -m1 '^sim_seconds' $gm | awk '{print $2}')
  awk -v n=$b -v a=$t0 -v x=$t1 'BEGIN{printf "%s,%.6f,%.6f,%.3f\n", n, a, x, (x/a-1)*100}' >> $out
done

cat $out
