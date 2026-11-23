# Setting up the GhostMinion artefact without root access

This guide describes how I built and ran the GhostMinion artefact on a shared compute node of the CSLab cluster at NTUA. The node had no root access, no Docker and no usable system compiler, so everything is installed in user space with micromamba. The same steps should work on any x86-64 Linux machine in a similar situation.

None of the changes below touch GhostMinion's own code. The only file of the artefact that is modified is gem5's `site_scons/site_tools/default.py` (see [step 4](#4-build-gem5)).

Throughout the guide:

```bash
WORKDIR=/local/$USER                         # a fast local disk with enough space
ARTEFACT=$WORKDIR/reproduce-ghostminion-paper
MAMBA=$WORKDIR/mamba                         # micromamba root prefix
```

<!-- TODO: replace placeholders below with the exact contents of env.sh, the env YAML files and the git diff from haci3_files.tar.gz -->

## Contents

1. [The machine](#1-the-machine)
2. [Getting onto the node](#2-getting-onto-the-node)
3. [micromamba and the two environments](#3-micromamba-and-the-two-environments)
4. [Build gem5](#4-build-gem5)
5. [Build SPEC CPU2006](#5-build-spec-cpu2006)
6. [Run SPEC CPU2006](#6-run-spec-cpu2006)
7. [Parsec](#7-parsec)
8. [Known problems](#8-known-problems)

## 1. The machine

| | |
|---|---|
| Node | `haci3`, CSLab cluster |
| CPU | 2 × 14 physical cores (56 hardware threads) |
| Memory | 188 GB |
| OS | Debian 13 |
| Restrictions | no root, no Docker, no system `gcc` |
| Working directory | local disk (`/local/<user>`), not the shared home |

Running on the node's local disk rather than the network-mounted home matters: gem5 writes a lot of small files and the SPEC build creates thousands of them.

## 2. Getting onto the node

The cluster is reached through `scirouter.cslab.ece.ntua.gr`, which runs an old SSH server that only offers RSA host keys. Modern OpenSSH clients refuse it unless RSA is re-enabled explicitly:

```bash
ssh -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa <user>@scirouter.cslab.ece.ntua.gr
```

From there, an interactive session on the compute node is requested with `qsubx haci3`. Since simulations run for many hours, do this inside `screen` (or `tmux`) on scirouter so that the session survives a dropped connection.

To reach the node directly from a laptop, for example to copy results, scirouter can be used as a jump host:

```bash
ssh -o ServerAliveInterval=60 \
    -o "ProxyCommand=ssh -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa -i ~/.ssh/id_rsa -W %h:%p <user>@scirouter.cslab.ece.ntua.gr" \
    -i ~/.ssh/id_rsa <user>@haci3
```

`-W %h:%p` makes the first connection forward a raw TCP stream to the target host, and `ServerAliveInterval` keeps idle connections from being dropped.

## 3. micromamba and the two environments

micromamba is a single static binary, so it can be installed without root:

```bash
mkdir -p $MAMBA/bin && cd $MAMBA
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
export MAMBA_ROOT_PREFIX=$MAMBA
```

Two separate environments are used, because gem5 and the SPEC cross-compiler need different toolchains:

| Environment | Purpose | Main packages |
|---|---|---|
| `gem5` | building and running gem5 | Python 3.8, SCons 3.1.2, GCC/G++ 7.5, libxcrypt, glibc 2.17 sysroot, dtc |
| `spec-cross` | cross-compiling SPEC for AArch64 | aarch64 GCC/G++/GFortran 9.5 (conda-forge), `sysroot_linux-aarch64` 2.17 |

Create them from the exported files in [`env/`](../env/):

```bash
$MAMBA/bin/micromamba create -n gem5       -f env/environment-gem5.yml
$MAMBA/bin/micromamba create -n spec-cross -f env/environment-spec-cross.yml
```

The versions are pinned to exactly the ones that worked with gem5 v20.1; newer Python or SCons releases were not tested.

[`env/env.sh`](../env/env.sh) activates the `gem5` environment and exports the variables the build needs: `CC`, `CXX`, `CPATH`, `LIBRARY_PATH`, `LD_LIBRARY_PATH`, `AR`, `RANLIB` and `AS`. Source it in every new shell before building or running:

```bash
source env/env.sh
```

## 4. Build gem5

```bash
./scripts/bootstrap.sh $WORKDIR     # clone the artefact at the pinned commit and apply patches/
source env/env.sh
./scripts/build_gem5.sh
```

Four problems came up, in this order:

1. **SCons does not find the compiler.** conda's compilers have long target-prefixed names (`x86_64-conda-linux-gnu-gcc`). gem5's SCons scripts detect the compiler from the name of `CC`/`CXX`, so `env.sh` points them to names SCons recognises (`gcc`, `g++`).
2. **`Python.h` cannot find `crypt.h`.** Recent glibc versions no longer ship `crypt.h`; it now comes from libxcrypt, which is installed in the environment. SCons, however, does not pass the shell's environment to the compiler, so `CPATH` is ignored. The fix is to add `CPATH` to the list of variables SCons imports, in `site_scons/site_tools/default.py`. This is the only change to the artefact's files, kept as [`patches/gem5-cpath.patch`](../patches/).
3. **Linker error about `.relr.dyn`.** The host's system libraries (Debian 13) use a relocation format that the older linker in the environment does not understand. Linking against the glibc 2.17 sysroot in the environment, instead of the host's libraries, avoids it.
4. **`ar: not found`.** Some binutils tools exist only with their long conda names. Symlinks with the short names (`ar`, `ranlib`, `as`) in the environment's `bin/` fix this, together with the `AR`, `RANLIB`, `AS` exports in `env.sh`.

A successful build produces `$ARTEFACT/gem5/build/ARM/gem5.opt`.

## 5. Build SPEC CPU2006

The artefact expects a SPEC CPU2006 ISO in its root directory. I used the lab's existing installation of SPEC CPU2006 v1.1 instead. Whichever you use, SPEC must not be copied into this repository.

1. **Fix the `runspec` shebang.** The installed tree had been moved from its original location, so the shebang of `runspec` pointed to a Perl that no longer existed. SPEC provides a script for exactly this case:
   ```bash
   cd $ARTEFACT/SPEC && bin/relocate
   ```
2. **Install the config.** Copy [`spec/aarch64.cfg`](../spec/aarch64.cfg) to `$ARTEFACT/SPEC/config/`. Compared with the artefact's config, it
   - points the compilers to the `spec-cross` environment (`$MAMBA/envs/spec-cross/bin/aarch64-conda-linux-gnu-{gcc,g++,gfortran}`);
   - adds `-std=gnu++98` for `450.soplex`, whose sources do not compile as C++11 or later;
   - adds `-std=legacy` for `416.gamess`, which uses Fortran constructs that GFortran 9 rejects by default.
3. **Build.** `./scripts/build_spec06.sh`. As the artefact's README notes, the final step of `runspec` reports failures, because the cross-compiled AArch64 binaries cannot run on the x86 host. That is expected.
4. **Check the astar input.** In the installation I used, `473.astar`'s `BigLakes2048.cfg` did not match its MD5 checksum in SPEC's `MANIFEST`. I restored it from an older run directory and verified the checksum against the `MANIFEST` before running.
5. **Rename the run directories.** `runspec` created run directories ending in `.0001` or `.0002`, while the artefact's run script expects `run_base_ref_aarch64.0000`. Rename them before running.

<!-- TODO: compare spec/aarch64.cfg with the artefact's spec_confs/ version and list any other differences -->

## 6. Run SPEC CPU2006

```bash
source env/env.sh
./scripts/run_spec06.sh             # baseline and GhostMinion
./scripts/run_spec06_ablation.sh    # lbm and libquantum, partial configurations
```

`run_spec06.sh` follows the artefact's script, with the number of parallel simulations set to `P=25` so that all benchmarks run at once, one per physical core. Each benchmark fast-forwards 1 billion instructions and then simulates 1 billion in detail on the out-of-order CPU, once without and once with GhostMinion.

Results are written inside each benchmark's run directory:

```
SPEC/benchspec/CPU2006/<bench>/run/run_base_ref_aarch64.0000/
├── m5out/statsno.txt            baseline
├── m5out/statsghostminion.txt   full GhostMinion
├── m5out_nopf/stats.txt         ablation: without --prefetch_ordered
├── m5out_dminion/stats.txt      ablation: D-Minion only
└── m5out_coher/stats.txt        ablation: D-Minion + coherence
```

The ablation directories exist only for the benchmarks where those runs were done (lbm: `m5out_nopf`; libquantum: all three).

<!-- TODO: add wall-clock time per suite -->

## 7. Parsec

Parsec runs in full-system mode: the system boots on a simple CPU, a checkpoint is restored, and the out-of-order CPU takes over, on 4 cores with 4 threads and the sim-medium inputs.

```bash
./scripts/run_parsec.sh
./scripts/collect_parsec.sh        # writes run_parsec/parsec_results.csv
```

Outputs are in `run_parsec/<bench>/m5out/` (`statsno.txt` and `statsghostminion.txt`). Each stats file has two dumps: the first covers the region of interest and is the one used for the results; the second is cumulative up to the end of the simulation.

Two Parsec runs, freqmine and streamcluster, had to be repeated on their own because a second run had been started by mistake and would have overwritten their stats. Their GhostMinion results are therefore in `run_parsec/<bench>/m5out_gm/stats.txt`, and the collection script reads them from there.

<!-- TODO: disk image / kernel source and the exact Parsec build path used (full or simplified) -->

## 8. Known problems

- **`watch` crashes inside the environment.** With the environment's libraries on `LD_LIBRARY_PATH`, the system `watch` segfaults. Run it without that variable:
  ```bash
  env -u LD_LIBRARY_PATH watch -n 60 'ls m5out*'
  ```
- **Starting a run twice.** The run scripts do not check whether a simulation is already writing to the same output directory. Before restarting anything, check with `ps` or `pgrep gem5` that no earlier run is still active.
- **Determinism.** gem5 is deterministic: repeating a simulation with the same binary, inputs and options gives exactly the same `sim_seconds`. A different result after a re-run means something in the setup changed.
