# Environment for building and running gem5.
# Source it in every new shell, do not execute it:
#
#     source env/env.sh
#
# The defaults match the layout used on the CSLab node. To use other paths,
# set any of these before sourcing:
#
#     MAMBA_ROOT_PREFIX   micromamba root (contains envs/ and pkgs/)
#     MICROMAMBA          the micromamba binary
#     ARTEFACT            the artefact checkout made by scripts/bootstrap.sh

export MAMBA_ROOT_PREFIX=${MAMBA_ROOT_PREFIX:-/local/$USER/mamba}
MICROMAMBA=${MICROMAMBA:-/local/$USER/bin/micromamba}
export ARTEFACT=${ARTEFACT:-/local/$USER/reproduce-ghostminion-paper}

eval "$("$MICROMAMBA" shell hook -s bash)"
micromamba activate gem5 2>/dev/null

# conda's compilers keep their target prefix in the name; tell SCons explicitly
export CC=x86_64-conda-linux-gnu-gcc
export CXX=x86_64-conda-linux-gnu-g++

# Headers and libraries of the environment (e.g. crypt.h from libxcrypt).
# gem5's SCons ignores CPATH unless patches/0001-gem5-scons-pass-CPATH.patch is applied.
export CPATH=$CONDA_PREFIX/include
export LIBRARY_PATH=$CONDA_PREFIX/lib
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

# Note: with LD_LIBRARY_PATH set, the system `watch` segfaults on Debian 13.
# Use:  env -u LD_LIBRARY_PATH watch ...
