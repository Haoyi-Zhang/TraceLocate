# Reproducibility Artifact

This directory is independently runnable and contains the complete computational evidence for the accompanying paper.

## One-command reproduction

```bash
python reproduce.py --out results/reproduction
```

This regenerates and compares the original finite matrix, rebuilds the two-system RTL campaign from retained raw traces, checks all deterministic case fields and certificates, runs the bridge consumers and mutation suites, and executes the implementation-independent exhaustive oracle.

For source-level RTL re-simulation, supply an Icarus Verilog executable:

```bash
python reproduce.py \
  --out results/reproduction \
  --iverilog /path/to/iverilog
```

## Main directories

- `src/` — producer, consumers, campaign builders, evidence freeze, and release checker.
- `tests/` — regression, mutation, metamorphic, and independent exhaustive checks.
- `models/` — finite models and the UART, arbiter, and combined campaigns.
- `rtl/ben-marshall-uart/` — pinned UART source bridge, license, harness, raw traces, and import report.
- `rtl/bmartini-arbiter/` — pinned round-robin-arbiter bridge, license, harness, raw traces, and import report.
- `certificates/` — retained exact certificates for 432 finite and 52 RTL cases.
- `results/` — deterministic case matrices and all validation summaries.
- `literature/` — per-entry bibliography identity ledger and 22-paper full-text calibration ledger. Full-text PDF bytes are intentionally not redistributed.

## Frozen totals

- 484 exact cases: 105 feasible and 379 infeasible;
- 343 zero-loss full-interface aliases;
- 60 public-RTL traces and 2,880 rows;
- 64 verified, used bibliography entries;
- 22 validated identity and access-level records;
- 4,096 independent exhaustive selection instances;
- 20 rejected certificate mutations and 12 rejected RTL-bridge mutations.


## Interpretation

All guarantees are for finite, equal-length, synchronously sampled traces with independent loss of at most a declared number of whole rows. The artifact does not model physical trace routing, analog faults, arbitrary bit errors, or fabricated-silicon behavior.
