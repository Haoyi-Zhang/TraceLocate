# Reproducibility Artifact

This standalone directory contains the computational evidence for the paper's supported scope: 432 finite-model tasks and 28 tasks imported from one pinned public UART simulation bridge. Draft arbiter and PicoRV32 additions are not part of the claimed evidence and are not invoked or counted.

## Full one-command reproduction

A full replay requires an Icarus Verilog executable with a sibling `vvp`. The output must be a new descendant of this repository root's `reproductions/` directory; existing paths are refused and never deleted.

```bash
python reproduce.py \
  --iverilog /path/to/iverilog \
  --out reproductions/full-run
```

The command, in order:

1. tests output-path safety in disposable temporary fixtures;
2. regenerates and independently checks all 432 finite-model cases;
3. validates the retained UART source/trace/model bridge;
4. recompiles the pinned UART RTL in an isolated temporary copy and requires byte-identical traces, model, and 28-case campaign;
5. regenerates and independently checks all 28 UART cases;
6. runs the ten directed bridge mutations and the mask/fault regressions;
7. reruns the exact finite oracles, 24 certificate mutations, alias check, and bounded microbenchmarks; and
8. writes `summary.json` only after every prior stage succeeds.

For environments without a simulator, an explicitly weaker mode checks the retained UART traces and all downstream evidence but does not claim source-level re-simulation:

```bash
python reproduce.py \
  --retained-only \
  --out reproductions/retained-run
```

## Supported evidence

`src/scientific_checks.py --out /absolute/new/output` runs the finite campaigns,
independent oracles, and passive retained-UART checks without a simulator. Its
output must be new and outside this artifact directory. The accompanying
`scientific-checks.yml` workflow runs from this flat artifact repository on
Ubuntu 24.04, bounds the whole run, preserves failure gates, and uploads raw
attempts even after failure. This is a retained-data check, not an RTL replay,
paper build, or proof-assistant verification.

- `models/campaign.json` and six finite models: 432 cases, 85 feasible, 347 infeasible, and 327 zero-loss full-interface aliases.
- `models/rtl-campaign.json`: exactly 28 UART cases, 12 feasible, 16 infeasible, and 8 zero-loss aliases.
- `rtl/ben-marshall-uart/`: pinned MIT-licensed TX/RX source, declaration-only compatibility rewrite, deterministic testbench, 33 raw traces, 1,584 rows, manifest, and importer.
- `results/campaign/` and `results/rtl-campaign/`: one case record and one certificate per declared case.
- `src/check_certificate.py`: independent finite-model certificate consumer.
- `src/check_rtl_bridge.py`: independent source-to-language bridge checker, including the complete ordered mapping from 12 packed bits to CSV columns, RTL expressions, tap names, kinds, and costs.
- `tests/test_rtl_bridge.py`: ten directed bridge corruptions, including renamed/exchanged campaign identifiers, equal-cost `tx_busy`/`rxd` name exchange and a derived-fault cycle change with unchanged traces and hashes.
- `tests/test_uart_regressions.py`: verifies that mask 2176 is `{rxd, rx_sample}` and that mask 2050 is `{tx_busy, rx_sample}` and retains full-length cross-class aliases for `payload-5`, `h=24`, `d=0`.
- `tests/test_contract.py`: exact weighted oracles and 24 semantically invalid certificate packets, including four same-length multi-pair reorder/duplicate-replacement mutations.

## UART timebase

The testbench has ``timescale 1ns/1ps`` and toggles `clk` every 5 ns, so absolute simulated time corresponds to 100 MHz. Its RTL parameters `CLK_HZ=4_000_000` and `BIT_RATE=1_000_000` set cycle ratios inside the design. The experiment is interpreted only in sampled-cycle coordinates; it is not a measured 4 MHz clock or 1 MHz physical line-rate implementation.

## Boundaries

All guarantees concern finite, equal-length, synchronously sampled row languages with independent deletion of at most the declared number of complete rows. The artifact does not establish synthesis, routed probes, trace-buffer implementation, area, power, timing, FPGA or silicon behavior, electrical faults, or a defect-population distribution.
