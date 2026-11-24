#!/usr/bin/env bash
# Build SPEC CPU2006 for AArch64 without root.
#
# Replaces the artefact's scripts/build_spec06.sh, which mounts the ISO with
# sudo and installs SPEC from it. Here SPEC is expected to be installed
# already in $ARTEFACT/SPEC (for example copied from an existing installation,
# as was done on the CSLab node). SPEC itself is not part of this repository.
#
# Usage:
#     source env/env.sh
#     scripts/build_spec06_noroot.sh

set -uo pipefail     # no -e: runspec reports errors that are expected (see below)
: "${ARTEFACT:?set ARTEFACT (source env/env.sh)}"

SPEC=$ARTEFACT/SPEC
BENCHES="astar bwaves bzip2 cactusADM calculix gamess gcc GemsFDTD gobmk gromacs
         h264ref hmmer lbm leslie3d libquantum mcf milc namd omnetpp povray sjeng
         soplex tonto xalancbmk zeusmp"

if [ ! -x "$SPEC/bin/runspec" ]; then
    echo "error: no SPEC CPU2006 installation in $SPEC" >&2
    exit 1
fi
cd "$SPEC"

# 1. An installation that was moved still has the old paths in the shebangs of
#    its tools (runspec fails with "bad interpreter"). SPEC's own script fixes them.
bin/relocate

# 2. Config with the conda cross-compilers (patched by scripts/bootstrap.sh).
cp "$ARTEFACT/spec_confs/aarch64.cfg" config/

# 3. Build, then create the run directories. These are the artefact's commands.
#    The "run" step reports failures because the AArch64 binaries cannot run on
#    the x86 host; only the run directories it creates are needed.
. ./shrc
runspec --config=aarch64.cfg --action=build $BENCHES -I
runspec --config=aarch64.cfg --action=run --size=ref $BENCHES --noreportable --iterations=1 -I

# 4. The artefact's run scripts expect run/run_base_ref_aarch64.0000. If runspec
#    numbered the directory .0001 or higher, rename the newest one.
for dir in benchspec/CPU2006/*/run; do
    [ -d "$dir/run_base_ref_aarch64.0000" ] && continue
    latest=$(ls -d "$dir"/run_base_ref_aarch64.* 2>/dev/null | sort | tail -1)
    if [ -n "$latest" ]; then
        echo "renaming $latest -> run_base_ref_aarch64.0000"
        mv "$latest" "$dir/run_base_ref_aarch64.0000"
    fi
done

# 5. On the CSLab installation, astar's BigLakes2048.cfg did not match SPEC's
#    MANIFEST. Print both checksums so they can be compared by eye; if they
#    differ, restore the file from the installation and check again.
echo
echo "astar input check (the two checksums must match):"
grep 'BigLakes2048.cfg' MANIFEST
md5sum benchspec/CPU2006/473.astar/run/run_base_ref_aarch64.0000/BigLakes2048.cfg
