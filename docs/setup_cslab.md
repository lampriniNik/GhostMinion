# Setting up the GhostMinion artefact without root access

This guide describes how I built and ran the GhostMinion artefact on a shared compute node of the CSLab cluster at NTUA. The node had no root access, no Docker and no usable system compiler, so everything is installed in user space with micromamba. The same steps should work on any x86-64 Linux machine in a similar situation.

GhostMinion's own code is not modified. Three files of the artefact are patched (see [step 4](#4-get-the-artefact)): one gem5 build file, the SPEC run script and the SPEC config.

Paths used throughout, as on the CSLab node:

| Variable | Value | What |
|---|---|---|
| `WORKDIR` | `/local/$USER` | a fast local disk with enough space |
| `MAMBA_ROOT_PREFIX` | `$WORKDIR/mamba` | micromamba environments and package cache |
| micromamba binary | `$WORKDIR/bin/micromamba` | |
| `ARTEFACT` | `$WORKDIR/reproduce-ghostminion-paper` | the artefact, created by `scripts/bootstrap.sh` |

## Contents

1. [The machine](#1-the-machine)
2. [Getting onto the node](#2-getting-onto-the-node)
3. [micromamba and the two environments](#3-micromamba-and-the-two-environments)
4. [Get the artefact](#4-get-the-artefact)
5. [Build gem5](#5-build-gem5)
6. [Build SPEC CPU2006](#6-build-spec-cpu2006)
7. [Run SPEC CPU2006](#7-run-spec-cpu2006)
8. [Parsec](#8-parsec)
9. [Known problems](#9-known-problems)

## 1. The machine

| | |
|---|---|
| Node | `haci3`, CSLab cluster |
| CPU | 2 × 14 physical cores (56 hardware threads) |
| Memory | 188 GB |
| OS | Debian 13 |
| Restrictions | no root, no Docker, no system `gcc` |
| Working directory | node-local disk (`/local/<user>`), not the shared home |

Running on the node's local disk rather than the network-mounted home matters: gem5 writes many small files and the SPEC build creates thousands of them.

## 2. Getting onto the node

The cluster is reached through `scirouter.cslab.ece.ntua.gr`, which runs an old SSH server that only offers RSA host keys. Recent OpenSSH clients refuse it unless RSA is re-enabled explicitly:

```bash
ssh -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa <user>@scirouter.cslab.ece.ntua.gr
```

From there, an interactive session on the compute node is requested with `qsubx haci3`. Simulations run for many hours, so do this inside `screen` (or `tmux`) on scirouter, so that the session survives a dropped connection.

To reach the node directly from a laptop, for example to copy results, scirouter can be used as a jump host:

```bash
ssh -o ServerAliveInterval=60 \
    -o "ProxyCommand=ssh -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa -i ~/.ssh/id_rsa -W %h:%p <user>@scirouter.cslab.ece.ntua.gr" \
    -i ~/.ssh/id_rsa <user>@haci3
```

`-W %h:%p` makes the first connection forward a raw TCP stream to the target host, and `ServerAliveInterval` keeps idle connections from being dropped. The same `-o "ProxyCommand=..."` works with `scp`.

## 3. micromamba and the two environments

micromamba is a single static binary, so it can be installed without root:

```bash
WORKDIR=/local/$USER
mkdir -p $WORKDIR/bin && cd $WORKDIR
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
export MAMBA_ROOT_PREFIX=$WORKDIR/mamba
eval "$($WORKDIR/bin/micromamba shell hook -s bash)"
```

The last line defines the `micromamba` shell function for the current shell; `env/env.sh` does the same every time it is sourced.

Two separate environments are used, because gem5 and the SPEC cross-compiler need different toolchains:

| Environment | Purpose | Main packages |
|---|---|---|
| `gem5` | building and running gem5 | Python 3.8, SCons 3.1.2, GCC/G++ 7.5, libxcrypt, glibc 2.17 sysroot, dtc, git |
| `spec-cross` | cross-compiling SPEC for AArch64 | aarch64 GCC/G++/GFortran 9.5 (conda-forge), `sysroot_linux-aarch64` 2.17 |

Create them from the exported files in [`env/`](../env/), from the root of this repository:

```bash
micromamba create -n gem5       -f env/environment-gem5.yml
micromamba create -n spec-cross -f env/environment-spec-cross.yml
```

The files pin exact versions and builds, as they were on the node. The versions that matter are Python 3.8 and SCons 3.1.2, which work with gem5 v20.1; newer ones were not tested.

[`env/env.sh`](../env/env.sh) activates `gem5` and exports what the build and the simulations need:

| Variable | Value | Why |
|---|---|---|
| `CC`, `CXX` | `x86_64-conda-linux-gnu-gcc`, `-g++` | conda's compilers keep their target prefix in the name, so SCons has to be told explicitly |
| `CPATH` | `$CONDA_PREFIX/include` | headers of the environment, e.g. `crypt.h` |
| `LIBRARY_PATH` | `$CONDA_PREFIX/lib` | libraries at link time |
| `LD_LIBRARY_PATH` | `$CONDA_PREFIX/lib:...` | the same libraries when `gem5.opt` runs |

Source it in every new shell before building or running anything:

```bash
source env/env.sh
```

## 4. Get the artefact

```bash
scripts/bootstrap.sh $WORKDIR
```

`bootstrap.sh` clones [SamAinsworth/reproduce-ghostminion-paper](https://github.com/SamAinsworth/reproduce-ghostminion-paper), checks out tag `AEV3`, verifies that it is commit `38b24e003ff9489efada0043f427386875614d80`, and applies the patches in [`patches/`](../patches/). It refuses to overwrite an existing directory.

## 5. Build gem5

```bash
source env/env.sh
cd $ARTEFACT/scripts && ./build.sh        # scons -j4 build/ARM/gem5.opt
```

Four problems came up, in this order:

1. **SCons does not find the compiler.** There is no system `gcc`, and the environment's compilers are called `x86_64-conda-linux-gnu-gcc` and `-g++`. `env.sh` sets `CC` and `CXX` to these names.
2. **`Python.h` cannot find `crypt.h`.** The header comes from libxcrypt in the environment, and `CPATH` points to it, but gem5's SCons builds with a clean environment and only imports a fixed list of variables, which does not include `CPATH`. [`patches/0001-gem5-scons-pass-CPATH.patch`](../patches/0001-gem5-scons-pass-CPATH.patch) adds it to that list in `site_scons/site_tools/default.py`. This is the only change to gem5.
3. **Linker error about `.relr.dyn`.** The host's system libraries (Debian 13) use a relocation format that the older linker in the environment does not understand. The environment's glibc 2.17 sysroot (`sysroot_linux-64`), which the compiler then links against instead of the host's libraries, avoids it.
4. **`ar: not found`.** The build calls the binutils by their short names, which the environment only provides with the `x86_64-conda-linux-gnu-` prefix. Symlinks with the short names in the environment's `bin/` fix it. These are the five that were created on the node:
   ```bash
   cd $CONDA_PREFIX/bin
   for t in ar as nm ranlib strip; do ln -s x86_64-conda-linux-gnu-$t $t; done
   ```

A successful build produces `$ARTEFACT/gem5/build/ARM/gem5.opt`.

## 6. Build SPEC CPU2006

The artefact's `build_spec06.sh` mounts the SPEC ISO with `sudo mount -o loop`, which is not possible without root. I used the lab's existing installation of SPEC CPU2006 v1.1 instead, copied to `$ARTEFACT/SPEC`. SPEC must never be copied into this repository.

```bash
source env/env.sh
scripts/build_spec06_noroot.sh
```

The script does the following, in this order:

1. **Fix the moved installation.** The tree had been moved from where it was installed, so the shebang of `runspec` pointed to a Perl that no longer existed. SPEC's own `bin/relocate` rewrites these paths.
2. **Install the config.** It copies the patched `spec_confs/aarch64.cfg` to `SPEC/config/`. Compared with the artefact's config, [`patches/0003`](../patches/0003-spec-aarch64-cfg-conda-cross-compilers.patch)
   - points `CC`, `CXX` and `FC` to the `spec-cross` environment (`$MAMBA_ROOT_PREFIX/envs/spec-cross/bin/aarch64-conda-linux-gnu-{gcc,g++,gfortran}`) instead of Ubuntu's `aarch64-linux-gnu-gcc-5`;
   - adds `-std=gnu++98` for `450.soplex`, whose sources do not build as C++14, the GCC 9 default;
   - adds `-std=legacy` for `416.gamess`, which uses Fortran constructs that GFortran 9 rejects by default.
3. **Build and set up run directories,** with the artefact's two `runspec` commands. As the artefact's README notes, the `--action=run` step reports failures, because the cross-compiled AArch64 binaries cannot run on the x86 host. That is expected; only the run directories it creates are needed.
4. **Rename the run directories.** `runspec` created directories ending in `.0001` or `.0002`, while the run scripts expect `run_base_ref_aarch64.0000`. The script renames the newest one when `.0000` is missing.
5. **Check astar's input.** In the installation I used, `473.astar`'s `BigLakes2048.cfg` did not match its checksum in SPEC's `MANIFEST`. I restored it from an older run directory and checked the MD5 against the `MANIFEST` before running. The script prints both checksums so the comparison is easy to repeat.

## 7. Run SPEC CPU2006

```bash
source env/env.sh
cd $ARTEFACT/scripts
./run_spec06.sh                 # baseline and full GhostMinion, 25 benchmarks
cd -
scripts/run_nopf.sh             # lbm, libquantum without --prefetch_ordered
scripts/run_libq_breakdown.sh   # libquantum: D-Minion only, D-Minion + coherence
```

`run_spec06.sh` is the artefact's script with `P=25` ([`patches/0002`](../patches/0002-run_spec06-run-25-benchmarks-in-parallel.patch)), so that all benchmarks run at once, one per physical core. For each benchmark it calls `scripts/gem5_scripts/run_ghostminion.sh`, which runs gem5 twice: without and with GhostMinion. Each run fast-forwards 1 billion instructions on the atomic CPU and then simulates 1 billion in detail on `DerivO3CPU`.

Results are written inside each benchmark's run directory:

```
$ARTEFACT/SPEC/benchspec/CPU2006/<bench>/run/run_base_ref_aarch64.0000/
├── m5out/statsno.txt            baseline
├── m5out/statsghostminion.txt   full GhostMinion
├── m5out_nopf/stats.txt         run_nopf.sh           (lbm, libquantum)
├── m5out_dminion/stats.txt      run_libq_breakdown.sh (libquantum)
└── m5out_coher/stats.txt        run_libq_breakdown.sh (libquantum)
```

The statistics are reset when gem5 switches from the fast-forward CPU to the out-of-order CPU, so `sim_seconds` covers only the detailed part of the run.

Host time per run on the node, over the 25 benchmarks:

| | Baseline | GhostMinion |
|---|---|---|
| Mean | 2.6 h | 3.0 h |
| Fastest | 1.8 h (hmmer) | 2.0 h (h264ref) |
| Slowest | 7.0 h (mcf) | 9.2 h (mcf) |

Since every benchmark runs its two configurations one after the other, and all 25 run in parallel, the suite finishes after about 16 hours, when mcf does.

## 8. Parsec

Parsec runs in full-system mode, on 4 cores with 4 threads and the sim-medium inputs, using the artefact's simplified setup with a prebuilt disk image.

```bash
source env/env.sh
# download aarch64-ubuntu-trusty-headless.img.tar.gz from the artefact's
# Releases page into $ARTEFACT/aarch_system/disks/, then:
cd $ARTEFACT/scripts
./build_parsec_simplified.sh    # unpacks the disk image and kernel, builds the device tree (dtc)
./run_parsec.sh
cd -
scripts/collect_parsec.sh       # writes $ARTEFACT/run_parsec/parsec_results.csv
```

`run_parsec.sh` calls `scripts/gem5_scripts/run_ghostminion_fs_checkpoint.sh` for each benchmark. That script first boots the system with the benchmark's run script (`arm-gem5-rsk/parsec_rcs/<bench>_simmedium_4.rcS`), which takes a checkpoint, and then restores that checkpoint twice on the out-of-order CPU, without and with GhostMinion (`--ghostminion --cache_coher --iminion --prefetch_ordered`). The stats go to `run_parsec/<bench>/m5out/statsno.txt` and `statsghostminion.txt`.

Each Parsec stats file has two dumps. The first covers the region of interest and is the one used for the results; the second is cumulative up to the end of the simulation.

Two Parsec runs, freqmine and streamcluster, had to be repeated on their own, because a second run had been started by mistake and would have overwritten their stats. Their GhostMinion results are in `run_parsec/<bench>/m5out_gm/stats.txt`, and `collect_parsec.sh` reads them from there when that file exists.

## 9. Known problems

- **`watch` crashes inside the environment.** With the environment's libraries on `LD_LIBRARY_PATH`, the system `watch` segfaults. Run it without that variable:
  ```bash
  env -u LD_LIBRARY_PATH watch -n 60 'ls m5out*'
  ```
- **Starting a run twice.** The run scripts do not check whether a simulation is already writing to the same output directory. Before restarting anything, check with `pgrep -a gem5` that no earlier run is still active.
- **Determinism.** gem5 is deterministic: repeating a simulation with the same binary, inputs and options gives exactly the same `sim_seconds`. A different result after a re-run means that something in the setup changed.
