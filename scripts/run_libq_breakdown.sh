#!/usr/bin/env bash
# Breakdown of GhostMinion's overhead on libquantum: enable the mechanisms one
# at a time. Together with the other runs, the steps are:
#
#   m5out_dminion      --ghostminion                          (this script)
#   m5out_coher        --ghostminion --cache_coher            (this script)
#   m5out_nopf         ... --cache_coher --iminion            (scripts/run_nopf.sh)
#   m5out (full)       ... --cache_coher --iminion --prefetch_ordered
#                                                             (artefact's run_spec06.sh)
#
# --ghostminion includes TimeGuarding and Leapfrogging. The GhostMinion size is
# the artefact's default (2 KiB, 2-way) in every run.
#
# Usage:
#     source env/env.sh
#     scripts/run_libq_breakdown.sh

set -u
: "${ARTEFACT:?set ARTEFACT (source env/env.sh)}"
BASE=$ARTEFACT

bench=libquantum
IN=$(grep $bench $BASE/spec_confs/input.txt | awk -F':' '{print $2}' | xargs)
BIN=$(grep $bench $BASE/spec_confs/binaries.txt | awk -F':' '{print $2}' | xargs)
ARGS=$(grep $bench $BASE/spec_confs/args.txt | awk -F':' '{print $2}' | xargs)
cd $BASE/SPEC/benchspec/CPU2006/*$bench/run/run_base_ref_aarch64.0000

COMMON="--caches --l2cache --cpu-type=DerivO3CPU --maxinsts=1000000000 --fast-forward=1000000000 --mem-size=4096MB"
GEM5="nice $BASE/gem5/build/ARM/gem5.opt"
SE=$BASE/gem5/configs/example/se.py

$GEM5 -d m5out_dminion $SE -c "./${BIN}_base.aarch64" -o "$ARGS" -i "$IN" $COMMON --ghostminion &
$GEM5 -d m5out_coher   $SE -c "./${BIN}_base.aarch64" -o "$ARGS" -i "$IN" $COMMON --ghostminion --cache_coher &
wait
