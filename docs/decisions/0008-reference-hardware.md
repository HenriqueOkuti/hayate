# 0008: Reference hardware for latency

- **Status:** accepted
- **Date:** 2026-11-14

## Context

Every student's latency has to be measured the same way, on hardware that is cheap to reach every weekend and close enough to a small cloud instance that the cost line in [measurement.md](../measurement.md) means something. The only machine is Henrique's desktop: i7-13700F (8 P-cores with SMT, 8 E-cores, AVX2 and AVX-VNNI, no AVX-512 or AMX), 23 GB of RAM in WSL2, Docker available. Spending money needs a budget first.

## Options considered

1. **The desktop as it is, one pinned thread.** Free and always there, but WSL2 floats its virtual CPUs over P-cores and E-cores and the frequency cannot be locked, so absolute numbers drift with whatever Windows is doing.
2. **A Docker "small VPS" profile on the same desktop:** 2 CPUs (`--cpuset-cpus=0,1`, two threads of one core like two AWS vCPUs), 4 GB of memory, one inference thread. Same noise as option 1, but the resource limits of the instance the cost line assumes (c7i.large), so memory or thread problems show up.
3. **Native Linux on the desktop.** Cleaner numbers (frequency and core type can be pinned), but a dual-boot to maintain for every run.
4. **A cloud instance (c7i.large on spot).** The real target, but it costs money every run and is a different CPU generation from the desktop.

## Decision

Option 2 for the headline numbers, labeled "small-VPS profile on i7-13700F/WSL2", with option 1 (one pinned thread, no container) reported alongside. Runs happen with heavy apps closed, and each records CPU model and ISA flags, affinity, cgroup CPU limit, threads, library versions and the model hash (`scripts/bench_tier1.py`, `make bench-local`, `make bench-vps`).

Comparisons between students are what these numbers are for: they carry over to the cloud. Absolute cost per million pages stays an estimate until one calibration run on a c7i.large, which needs its own budget (under $1 on spot) and Henrique's go-ahead.

## Consequences

- Latency results are comparable across weekends only if the machine is quiet, so a noisy run has to be rerun rather than averaged in. The trial spread in every result shows when that happened.
- WSL2 may place the pinned CPU on an E-core in one run and a P-core in the next. If the trial spread gets wide, switch to native Linux (option 3) for headline runs.
- Revisit when the calibration run happens, or if a student needs an ISA the desktop lacks (AVX-512 or AMX for int8 encoders).
