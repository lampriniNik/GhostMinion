#!/usr/bin/env bash
# Fetch the GhostMinion artefact at the exact version used for this
# reproduction and apply the patches in patches/.
#
# Usage:
#     source env/env.sh                  # sets MAMBA_ROOT_PREFIX
#     scripts/bootstrap.sh <workdir>
#
# Creates <workdir>/reproduce-ghostminion-paper. Nothing outside that
# directory is modified, and an existing directory is never overwritten.

set -euo pipefail

UPSTREAM=https://github.com/SamAinsworth/reproduce-ghostminion-paper
TAG=AEV3
COMMIT=38b24e003ff9489efada0043f427386875614d80   # what AEV3 pointed to when the runs were done

if [ $# -ne 1 ]; then
    echo "usage: $0 <workdir>" >&2
    exit 1
fi
: "${MAMBA_ROOT_PREFIX:?set MAMBA_ROOT_PREFIX first (source env/env.sh)}"

REPO=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$1"
WORKDIR=$(cd "$1" && pwd)
ARTEFACT=$WORKDIR/reproduce-ghostminion-paper

if [ -e "$ARTEFACT" ]; then
    echo "error: $ARTEFACT already exists, refusing to touch it" >&2
    exit 1
fi

# 1. Clone and check out the tagged version. The artefact contains the whole
#    modified gem5 tree, so this takes a while.
git clone "$UPSTREAM" "$ARTEFACT"
cd "$ARTEFACT"
git -c advice.detachedHead=false checkout "$TAG"

# 2. Make sure the tag still points to the commit that was used. If the author
#    ever moves the tag, check out $COMMIT instead.
actual=$(git rev-parse HEAD)
if [ "$actual" != "$COMMIT" ]; then
    echo "error: $TAG is $actual, expected $COMMIT" >&2
    exit 1
fi

# 3. Apply the patches (gem5 build fix, P=25, SPEC config).
git apply --verbose "$REPO"/patches/*.patch

# 4. Fill in the cross-compiler path in the SPEC config.
sed -i "s#@SPEC_CROSS_BIN@#$MAMBA_ROOT_PREFIX/envs/spec-cross/bin#" spec_confs/aarch64.cfg

echo
echo "Artefact ready at $ARTEFACT"
echo "If this is not the default location, run:  export ARTEFACT=$ARTEFACT"
