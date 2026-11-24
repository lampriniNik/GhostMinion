#!/usr/bin/env bash
# Ablation: GhostMinion without the ordered prefetcher, on lbm and libquantum.
#
# Same options as the full GhostMinion run in the artefact's
# scripts/gem5_scripts/run_ghostminion.sh, minus --prefetch_ordered.
# This configuration is NOT secure; it is only used to measure the cost of
# training the prefetcher on committed accesses.
#
# For libquantum this is also the "D-Minion + coherence + I-Minion" step of
# the breakdown (see scripts/run_libq_breakdown.sh).
#
# Output: SPEC/benchspec/CPU2006/<bench>/run/run_base_ref_aarch64.0000/m5out_nopf/
#
# Usage:
#     source env/env.sh
#     scripts/run_nopf.sh

set -u
: "${ARTEFACT:?set ARTEFACT (source env/env.sh)}"
BASE=$ARTEFACT

for bench in lbm libquantum; do
  (
  IN=$(grep $bench $BASE/spec_confs/input.txt | awk -F':' '{print $2}' | xargs)
  BIN=$(grep $bench $BASE/spec_confs/binaries.txt | awk -F':' '{print $2}' | xargs)
  ARGS=$(grep $bench $BASE/spec_confs/args.txt | awk -F':' '{print $2}' | xargs)
  cd $BASE/SPEC/benchspec/CPU2006/*$bench/run/run_base_ref_aarch64.0000
  nice $BASE/gem5/build/ARM/gem5.opt -d m5out_nopf $BASE/gem5/configs/example/se.py \
      -c "./${BIN}_base.aarch64" -o "$ARGS" -i "$IN" \
      --caches --l2cache --cpu-type=DerivO3CPU \
      --maxinsts=1000000000 --fast-forward=1000000000 --mem-size=4096MB \
      --ghostminion --cache_coher --ghost_size="2kB" --iminion
  ) &
done
wait
